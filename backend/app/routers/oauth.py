"""Google OAuth 2.0 (server-side Authorization Code flow).

Why server-side and not the Google Identity Services JS button:
- No third-party script on picur.my, so the existing strict CSP needs no
  `accounts.google.com` allowance.
- The browser only ever talks to picur.my; the client secret and the
  code→token exchange stay on the backend.

Flow:
  GET /auth/google/login     -> set state cookie (Lax), 302 to Google consent
  GET /auth/google/callback  -> verify state, exchange code, verify id_token,
                                find-or-create user, set picur_session, 302 home

Both endpoints are GET, so the CsrfMiddleware exempts them; the `state`
parameter is the CSRF defense for the OAuth leg itself.
"""
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    OAUTH_STATE_COOKIE,
    clear_oauth_state_cookie,
    create_access_token,
    set_oauth_state_cookie,
    set_session_cookie,
)
from app.config import settings
from app.database import get_db
from app.models import User, UserTier
from app.rate_limiter import auth_rate_limiter
from app.tiers import TIER_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["authentication"])

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "openid email profile"

# Where the user lands after a successful sign-in. Fixed (not caller-supplied)
# to avoid an open-redirect via a forged `next` parameter.
POST_LOGIN_PATH = "/admin/events"


def _login_url(error: str | None = None) -> str:
    """Frontend login page, optionally with an ?error= the page can surface."""
    base = f"{settings.frontend_url.rstrip('/')}/admin/login"
    return f"{base}?error={error}" if error else base


def _redirect_to_login_error(code: str) -> RedirectResponse:
    """Bounce back to the login page with a machine-readable error code, and
    clear any dangling state cookie so a retry starts clean."""
    resp = RedirectResponse(url=_login_url(error=code), status_code=status.HTTP_302_FOUND)
    clear_oauth_state_cookie(resp)
    return resp


@router.get("/login")
async def google_login(request: Request):
    """Kick off the OAuth handshake: stash a random `state`, redirect to Google."""
    if not settings.google_oauth_enabled:
        # Feature off (dev, or prod before credentials are set). The frontend
        # gates the button, but guard the route too.
        return _redirect_to_login_error("oauth_unavailable")

    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.enforce_rate_limit(client_ip, action="oauth_login_ip")

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.effective_google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        # Force the account chooser so a user logged into multiple Google
        # accounts can pick; avoids silently reusing the wrong one.
        "prompt": "select_account",
        # We only need identity, not offline API access — no refresh token.
        "access_type": "online",
    }
    resp = RedirectResponse(
        url=f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )
    set_oauth_state_cookie(resp, state)
    return resp


@router.get("/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle Google's redirect back: verify state, exchange code, sign the user in."""
    if not settings.google_oauth_enabled:
        return _redirect_to_login_error("oauth_unavailable")

    # User declined consent, or Google returned an error.
    if error:
        logger.info(f"Google OAuth returned error={error!r}")
        return _redirect_to_login_error("oauth_cancelled" if error == "access_denied" else "oauth_failed")

    # CSRF defense for the handshake: the state echoed back by Google must match
    # the one we stored in the (Lax) cookie before redirecting out.
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        logger.warning("Google OAuth state/code validation failed")
        return _redirect_to_login_error("oauth_state")

    # Exchange the authorization code for tokens.
    try:
        token_resp = httpx.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.effective_google_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        token_resp.raise_for_status()
        id_token_str = token_resp.json().get("id_token")
        if not id_token_str:
            raise ValueError("token response missing id_token")
    except Exception as e:
        logger.error(f"Google token exchange failed: {e}")
        return _redirect_to_login_error("oauth_failed")

    # Verify the ID token's signature, issuer, audience, and expiry. google-auth
    # fetches and caches Google's signing certs internally.
    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            audience=settings.google_client_id,
        )
    except Exception as e:
        logger.error(f"Google id_token verification failed: {e}")
        return _redirect_to_login_error("oauth_failed")

    google_sub = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    email_verified = claims.get("email_verified", False)

    if not google_sub or not email:
        logger.error("Google id_token missing sub/email")
        return _redirect_to_login_error("oauth_failed")

    # We rely on a Google-verified email for both account creation AND auto-link
    # to an existing password account. An unverified Google email would let an
    # attacker who controls a Google account with someone else's address claim
    # the matching PicUr account — refuse it.
    if not email_verified:
        logger.warning(f"Google email not verified for {email}")
        return _redirect_to_login_error("oauth_unverified_email")

    try:
        user = _find_or_create_oauth_user(db, google_sub=google_sub, email=email)
    except _OAuthAccountConflict:
        return _redirect_to_login_error("oauth_conflict")

    if user.is_disabled:
        logger.info(f"Disabled account attempted Google sign-in: {email}")
        return _redirect_to_login_error("account_disabled")

    # Issue the same session JWT/cookie the password login uses, then send the
    # user into the app. The picur_session cookie is Strict; the redirect to a
    # same-site picur.my path still carries it on the follow-up /auth/me call.
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=settings.jwt_expiration_hours),
    )
    resp = RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}{POST_LOGIN_PATH}",
        status_code=status.HTTP_302_FOUND,
    )
    set_session_cookie(resp, access_token)
    clear_oauth_state_cookie(resp)
    return resp


class _OAuthAccountConflict(Exception):
    """Existing account's email matches but it's already linked to a *different*
    Google identity — refuse rather than silently relinking."""


def _find_or_create_oauth_user(db: Session, *, google_sub: str, email: str) -> User:
    """Resolve the Google identity to a User, with auto-link.

    Order matters:
      1. Match on google_sub  -> returning Google user.
      2. Match on email       -> existing password account; link it (Google has
                                  verified the email, so this is safe) and mark
                                  verified.
      3. Neither              -> brand-new Google-only account (no password).
    """
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user:
        return user

    user = db.query(User).filter(User.email == email).first()
    if user:
        if user.google_sub and user.google_sub != google_sub:
            raise _OAuthAccountConflict()
        # Auto-link to the existing account.
        user.google_sub = google_sub
        # A Google-verified email proves ownership, so a previously-unverified
        # password signup is now safe to treat as verified.
        if not user.is_verified:
            user.is_verified = True
        db.commit()
        db.refresh(user)
        return user

    # Brand-new account. No password (OAuth-only); email already Google-verified.
    new_user = User(
        email=email,
        password_hash=None,
        google_sub=google_sub,
        is_verified=True,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent first-login for the same identity.
        # Re-resolve the row the winner committed.
        db.rollback()
        user = (
            db.query(User)
            .filter((User.google_sub == google_sub) | (User.email == email))
            .first()
        )
        if user is None:
            raise
        return user
    db.refresh(new_user)

    # Mirror /auth/register: eagerly create the free tier row so the first-event
    # flow doesn't race to INSERT it. Idempotent on the off chance it exists.
    free_cfg = TIER_CONFIG["free"]
    tier_row = UserTier(
        user_id=new_user.id,
        tier_name="free",
        max_events=free_cfg["max_events"],
        max_photos_per_event=free_cfg["max_photos_per_event"],
        price_cents=0,
        is_active=True,
        activated_at=datetime.utcnow(),
    )
    db.add(tier_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    return new_user
