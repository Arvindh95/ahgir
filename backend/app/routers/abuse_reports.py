"""Abuse reporting endpoints.

Public:
* POST /report — anonymous file-a-report against an image.

Superadmin:
* GET /admin/abuse-reports — list + filter + sort + paginate.
* GET /admin/abuse-reports/pending-count — nav-badge count.
* POST /admin/abuse-reports/{id}/reveal — mint 5-min review URL + audit.
* POST /admin/abuse-reports/{id}/quarantine — hide from guests.
* POST /admin/abuse-reports/{id}/delete-photo — permanent removal.
* POST /admin/abuse-reports/{id}/dismiss — close as not-abuse.

See ABUSE_REPORTING_PLAN.md for the full design rationale, including the
threat model around the reporting mechanism itself (multi-keyed rate
limits, anti-enumeration, soft-ban) — most of that is Phase 2.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.audit import log_action
from app.cache import cache_delete_pattern
from app.config import settings
from app.database import get_db
from app.models import AbuseReport, AuditLog, Event, Face, Image, User
from app.rate_limiter import (
    abuse_report_rate_limiter,
    abuse_report_subnet_rate_limiter,
    abuse_report_image_dedupe_limiter,
    abuse_report_event_rate_limiter,
    abuse_report_email_rate_limiter,
    redis_client,
)
from app.routers.admin import get_superadmin_user
from app.storage import generate_signed_abuse_review_url
from app.utils.storage_cleanup import safe_delete_compreface_subject, safe_delete_image_photo
from app.utils.time import to_utc_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["abuse-reports"])

# Anti-enumeration: a real image_id and a fake one should be
# indistinguishable from the outside. Pad every /report response to take
# at least this much wall time so a probe can't measure DB-lookup latency
# differences. Tuned to ~50ms which is well above DB jitter on the VPS.
_REPORT_MIN_DURATION_SECONDS = 0.05

_VALID_CATEGORIES = {"csam", "nudity", "harassment", "copyright", "violence", "other"}

_FIXED_THANKS_BODY = {"message": "Thank you. We will review this report shortly."}

# Redis keys for the reputation soft-ban / permaban state. Stored in Redis
# rather than a new table — soft-ban has a TTL (rolls off naturally) and
# permaban is a single-key flag the operator can DEL via /clear-ban.
_PERMABAN_KEY = "abuse:permaban:{ip}"
_SOFTBAN_KEY = "abuse:softban:{ip}"
_SOFTBAN_TTL_SECONDS = 7 * 24 * 3600


def _subnet_key(ip: str) -> str:
    """Derive a /24 (IPv4) or /64 (IPv6) network key for subnet rate limiting.

    Falls back to the raw string on parse failure so a malformed
    reporter_ip still gets bucketed (one bucket per raw value).
    """
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
        else:
            net = ipaddress.ip_network(f"{ip}/64", strict=False)
        return str(net)
    except (ValueError, TypeError):
        return ip


def _check_reputation_ban(db: Session, reporter_ip: str) -> Optional[str]:
    """Return 'permaban' | 'softban' | None for the given reporter IP.

    Permaban is a Redis flag set on threshold trip — never expires until
    an operator clears it. Soft-ban is a 7-day TTL flag. The rolling
    30-day dismiss-rate is recomputed each call (no view, no cache) so
    a re-evaluation only happens when the limiter waves a request
    through, i.e. at most ~5 reports/hour per IP.
    """
    try:
        if redis_client.exists(_PERMABAN_KEY.format(ip=reporter_ip)):
            return "permaban"
        if redis_client.exists(_SOFTBAN_KEY.format(ip=reporter_ip)):
            return "softban"
    except Exception:
        # Redis hiccup — fall through to DB-only eval rather than failing
        # closed (which would let a queue-flood through).
        pass

    window_start = datetime.now(timezone.utc) - timedelta(
        days=settings.abuse_report_reputation_window_days
    )
    counts = (
        db.query(AbuseReport.status, func.count(AbuseReport.id))
        .filter(AbuseReport.reporter_ip == reporter_ip)
        .filter(AbuseReport.created_at >= window_start)
        .group_by(AbuseReport.status)
        .all()
    )
    counts_by_status = {s: n for s, n in counts}
    total = sum(counts_by_status.values())
    dismissed = counts_by_status.get("dismissed", 0)
    if total < settings.abuse_report_softban_min_reports:
        return None
    rate = dismissed / total

    if (
        total >= settings.abuse_report_permaban_min_reports
        and rate >= settings.abuse_report_permaban_dismiss_rate
    ):
        try:
            redis_client.set(_PERMABAN_KEY.format(ip=reporter_ip), "1")
        except Exception:
            pass
        return "permaban"

    if rate >= settings.abuse_report_softban_dismiss_rate:
        try:
            redis_client.setex(
                _SOFTBAN_KEY.format(ip=reporter_ip), _SOFTBAN_TTL_SECONDS, "1"
            )
        except Exception:
            pass
        return "softban"

    return None


# ─── Pydantic models ─────────────────────────────────────────────────


class ReportCreateRequest(BaseModel):
    image_id: str
    category: str = Field(..., max_length=32)
    description: Optional[str] = Field(default=None, max_length=2000)
    reporter_email: Optional[EmailStr] = None
    # Honeypot field — frontend NEVER renders this; bots filling every
    # field will populate it and we silently drop the row.
    website: Optional[str] = Field(default=None, max_length=255)
    # Cloudflare Turnstile token from the front-end widget. Required when
    # cloudflare_turnstile_secret_key is configured; backend POSTs to
    # /siteverify before processing. Skipped in dev when the secret is
    # unset.
    turnstile_token: Optional[str] = Field(default=None, max_length=4096)


class ReportRow(BaseModel):
    id: str
    image_id: str
    event_id: str
    event_name: Optional[str] = None
    event_slug: Optional[str] = None
    filename: Optional[str] = None
    uploaded_at: Optional[str] = None
    category: str
    description: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_ip: Optional[str] = None
    status: str
    action_taken: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None
    reviewed_by_email: Optional[str] = None
    # Count of additional pending/reviewing reports on the same image in
    # the dedup window — surfaces the silent-deduplicated reports so
    # operators see "+N duplicate" without N extra rows.
    duplicate_count: int = 0
    # Always False for now — the self-report heuristic requires storing
    # the actor IP on every admin audit row to be useful, which is a
    # standalone migration + log_action refactor. Kept on the schema so
    # the frontend type stays stable when the feature lands; meanwhile
    # the badge has been removed from the queue UI to avoid leaking a
    # misleading signal (the previous query compared owner activity
    # timestamps only, no IP equality, producing routine false-positives).
    is_possible_self_report: bool = False
    # Echoes redis-resident ban state for this reporter_ip.
    reporter_ban_state: Optional[str] = None
    # Live status of the underlying image — distinct from report.status.
    # Lets the review screen render the Restore button when the image
    # is currently quarantined regardless of what the report itself says.
    image_status: Optional[str] = None


class ReportListResponse(BaseModel):
    items: list[ReportRow]
    total: int
    limit: int
    offset: int


class PendingCountResponse(BaseModel):
    pending: int


class RevealResponse(BaseModel):
    review_url: str
    expires_in: int
    status: str
    reviewed_at: Optional[str] = None
    reviewed_by_email: Optional[str] = None


class ActionResponse(BaseModel):
    message: str
    status: str


# ─── Public endpoint ─────────────────────────────────────────────────


@router.post("/report", response_model=dict)
async def file_abuse_report(
    payload: ReportCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """File an anonymous abuse report against a single image.

    Anti-abuse layers (Phase 1 subset):
    * Per-IP rate limit (5/hour).
    * Honeypot field (silent 200 if populated).
    * Pydantic enforces category enum + length caps + email format.
    * Anti-enumeration: real image_id and fake UUID both return the
      same fixed 200 body, and the handler runs for at least 50ms
      regardless of whether the image exists.
    """
    started = time.monotonic()
    reporter_ip = request.client.host if request.client else "unknown"
    reporter_email = (
        payload.reporter_email.lower() if payload.reporter_email else None
    )

    # Honeypot — bots fill every field; legit clients never see this one.
    # Silent 200 + no rate-limit consumption.
    if payload.website:
        logger.info("abuse-report honeypot hit ip=%s", reporter_ip)
        await _pad_duration(started)
        return _FIXED_THANKS_BODY

    # Pydantic max_length=32 already caps the category string. Reject
    # values outside the enum here so the DB CHECK never sees garbage.
    category = (payload.category or "").lower()
    if category not in _VALID_CATEGORIES:
        # 422 — client bug, not a routine submission.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )

    # Per-IP rate limit FIRST — cheapest check, runs before Turnstile so
    # invalid-token floods can't tie up async workers on the upstream
    # siteverify call. 429 — distinct from silent honeypot drop.
    allowed, retry_after = abuse_report_rate_limiter.check_rate_limit(
        reporter_ip, action="abuse_report"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reports from your address. Please try again later.",
            headers={"Retry-After": str(retry_after or 3600)},
        )

    # Subnet limit — defeats trivial IP rotation in the same /24 (IPv4)
    # or /64 (IPv6) range. Same 429 wire shape.
    subnet = _subnet_key(reporter_ip)
    allowed, retry_after = abuse_report_subnet_rate_limiter.check_rate_limit(
        subnet, action="abuse_report_subnet"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reports from your network. Please try again later.",
            headers={"Retry-After": str(retry_after or 3600)},
        )

    # Cloudflare Turnstile verification — runs AFTER cheap rate limits so
    # an attacker can't burn async-worker capacity on siteverify calls.
    # Fails closed: a missing or invalid token returns 403. Network
    # failure to Cloudflare logs a warning and falls open (per-IP/subnet
    # limits above still cap the abuse rate).
    if settings.cloudflare_turnstile_secret_key:
        if not payload.turnstile_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Captcha verification required.",
            )
        if not await _verify_turnstile(payload.turnstile_token, reporter_ip):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Captcha verification failed.",
            )

    # Reputation ban check (Redis-cached, falls back to 30d dismiss-rate
    # query). Silent-drop returns the same fixed body so a banned actor
    # can't tell they're banned. Audit row records the drop for ops.
    ban_state = _check_reputation_ban(db, reporter_ip)
    if ban_state in ("permaban", "softban"):
        log_action(
            db=db, event_id=None, actor_type="system", actor_id=None,
            action="abuse_report_softban_drop",
            metadata={"reporter_ip": reporter_ip, "ban_state": ban_state},
        )
        await _pad_duration(started)
        return _FIXED_THANKS_BODY

    # Per-email limit (soft signal — email is unverified).
    if reporter_email:
        allowed, retry_after = abuse_report_email_rate_limiter.check_rate_limit(
            reporter_email, action="abuse_report_email"
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many reports from this email. Please try again later.",
                headers={"Retry-After": str(retry_after or 3600)},
            )

    # Parse image_id. Bad UUIDs get the same fixed 200 — leaking "this
    # was malformed" would let a probe enumerate the UUID space by
    # error-message shape.
    try:
        image_uuid = uuid.UUID(payload.image_id)
    except (ValueError, TypeError):
        await _pad_duration(started)
        return _FIXED_THANKS_BODY

    image = db.query(Image).filter(Image.id == image_uuid).first()
    if not image:
        # Anti-enumeration: same response as a successful submission.
        await _pad_duration(started)
        return _FIXED_THANKS_BODY

    # Per-event_id limit — catches mass-targeting a single photographer.
    allowed, retry_after = abuse_report_event_rate_limiter.check_rate_limit(
        str(image.event_id), action="abuse_report_event"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reports for this event right now. Please try again later.",
            headers={"Retry-After": str(retry_after or 3600)},
        )

    # Per-image_id dedup. 4th+ report on the same image_id is silent-
    # dropped (still returns 200 — operator sees duplicate_count on the
    # queue row instead of N separate rows).
    allowed, _retry = abuse_report_image_dedupe_limiter.check_rate_limit(
        str(image.id), action="abuse_report_image_dedupe"
    )
    if not allowed:
        logger.info(
            "abuse-report dedup silent-drop image_id=%s reporter_ip=%s",
            image.id, reporter_ip,
        )
        await _pad_duration(started)
        return _FIXED_THANKS_BODY

    report = AbuseReport(
        image_id=image.id,
        event_id=image.event_id,
        category=category,
        description=(payload.description or "").strip() or None,
        reporter_email=reporter_email,
        reporter_ip=reporter_ip,
        status="pending",
    )
    db.add(report)
    db.commit()

    logger.info(
        "abuse-report filed id=%s image_id=%s category=%s reporter_ip=%s",
        report.id, image.id, category, reporter_ip,
    )
    _pad_duration(started)
    return _FIXED_THANKS_BODY


async def _pad_duration(started: float) -> None:
    """Hold the request open until at least _REPORT_MIN_DURATION_SECONDS.

    asyncio.sleep so the event loop can serve other requests while we
    pad — time.sleep would block the worker thread.
    """
    elapsed = time.monotonic() - started
    remaining = _REPORT_MIN_DURATION_SECONDS - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)


_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def _verify_turnstile(token: str, remote_ip: str) -> bool:
    """POST the token to Cloudflare /siteverify. Returns True if success=true.

    Async httpx so the event loop stays free during the upstream call.
    Network failure → True (fail-open). The per-IP / per-subnet rate
    limits in the caller still cap the abuse rate, so a Cloudflare
    outage degrades bot-defence without locking out legit users.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client_:
            resp = await client_.post(
                _TURNSTILE_VERIFY_URL,
                data={
                    "secret": settings.cloudflare_turnstile_secret_key,
                    "response": token,
                    "remoteip": remote_ip,
                },
            )
        if resp.status_code != 200:
            logger.warning("Turnstile siteverify HTTP %s", resp.status_code)
            return True  # fail-open
        body = resp.json()
        if body.get("success"):
            return True
        logger.info(
            "Turnstile token rejected ip=%s codes=%s", remote_ip, body.get("error-codes"),
        )
        return False
    except Exception as e:
        logger.warning("Turnstile siteverify failed (fail-open): %s", e)
        return True


# ─── Superadmin endpoints ────────────────────────────────────────────


@router.get(
    "/admin/abuse-reports/pending-count",
    response_model=PendingCountResponse,
)
async def get_pending_count(
    _superadmin: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Count of reports in 'pending' status. Powers the nav-badge."""
    n = db.query(AbuseReport).filter(AbuseReport.status == "pending").count()
    return PendingCountResponse(pending=n)


@router.get("/admin/abuse-reports", response_model=ReportListResponse)
async def list_abuse_reports(
    status_filter: Optional[str] = Query(default="pending", alias="status"),
    category: Optional[str] = Query(default=None),
    sort: str = Query(default="newest"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _superadmin: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List reports with filters + pagination. Metadata only — photo bytes
    and signed URLs are never returned by this endpoint, preserving the
    'no photo viewer for staff' contract until /reveal is invoked."""
    q = db.query(AbuseReport)
    if status_filter:
        if status_filter not in ("pending", "reviewing", "dismissed", "quarantined", "removed"):
            raise HTTPException(status_code=422, detail="invalid status filter")
        q = q.filter(AbuseReport.status == status_filter)
    if category:
        if category not in _VALID_CATEGORIES:
            raise HTTPException(status_code=422, detail="invalid category filter")
        q = q.filter(AbuseReport.category == category)

    total = q.count()

    if sort == "oldest":
        q = q.order_by(AbuseReport.created_at.asc())
    else:
        q = q.order_by(AbuseReport.created_at.desc())

    rows = q.limit(limit).offset(offset).all()

    # Bulk-join the metadata we render alongside each row.
    image_ids = [r.image_id for r in rows]
    event_ids = [r.event_id for r in rows]
    reviewer_ids = [r.reviewed_by for r in rows if r.reviewed_by]

    images = {
        i.id: i for i in db.query(Image).filter(Image.id.in_(image_ids)).all()
    } if image_ids else {}
    events = {
        e.id: e for e in db.query(Event).filter(Event.id.in_(event_ids)).all()
    } if event_ids else {}
    reviewers = {
        u.id: u for u in db.query(User).filter(User.id.in_(reviewer_ids)).all()
    } if reviewer_ids else {}

    # Duplicate counts: how many OTHER pending/reviewing reports point at
    # each image_id in the active dedup window. -1 (subtract self) so a
    # solo report shows 0, not 1.
    dup_window = datetime.now(timezone.utc) - timedelta(
        hours=settings.abuse_report_image_dedupe_window_hours
    )
    dup_counts = {}
    if image_ids:
        dup_rows = (
            db.query(AbuseReport.image_id, func.count(AbuseReport.id))
            .filter(AbuseReport.image_id.in_(image_ids))
            .filter(AbuseReport.status.in_(("pending", "reviewing")))
            .filter(AbuseReport.created_at >= dup_window)
            .group_by(AbuseReport.image_id)
            .all()
        )
        dup_counts = {iid: max(0, n - 1) for iid, n in dup_rows}

    # Self-report flag intentionally disabled — see ReportRow comment.
    # The previous heuristic compared owner-activity timestamps only,
    # with no IP equality, so any recently-active owner caused unrelated
    # reports to flag. Re-enable only after AuditLog gains a reporter-IP
    # column the query can join on.

    items: list[ReportRow] = []
    for r in rows:
        ev = events.get(r.event_id)
        img = images.get(r.image_id)
        reviewer = reviewers.get(r.reviewed_by) if r.reviewed_by else None

        sr_flag = False  # disabled — see ReportRow.is_possible_self_report

        ban_state = None
        if r.reporter_ip:
            try:
                if redis_client.exists(_PERMABAN_KEY.format(ip=r.reporter_ip)):
                    ban_state = "permaban"
                elif redis_client.exists(_SOFTBAN_KEY.format(ip=r.reporter_ip)):
                    ban_state = "softban"
            except Exception:
                pass

        items.append(ReportRow(
            id=str(r.id),
            image_id=str(r.image_id),
            event_id=str(r.event_id),
            event_name=ev.name if ev else None,
            event_slug=ev.slug if ev else None,
            filename=img.filename if img else None,
            uploaded_at=to_utc_iso(img.uploaded_at) if img and img.uploaded_at else None,
            category=r.category,
            description=r.description,
            reporter_email=r.reporter_email,
            reporter_ip=r.reporter_ip,
            status=r.status,
            action_taken=r.action_taken,
            notes=r.notes,
            created_at=to_utc_iso(r.created_at),
            reviewed_at=to_utc_iso(r.reviewed_at) if r.reviewed_at else None,
            reviewed_by_email=reviewer.email if reviewer else None,
            duplicate_count=dup_counts.get(r.image_id, 0),
            is_possible_self_report=sr_flag,
            reporter_ban_state=ban_state,
            image_status=img.status if img else None,
        ))

    return ReportListResponse(items=items, total=total, limit=limit, offset=offset)


def _load_report_or_404(report_id: str, db: Session) -> AbuseReport:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid report id")
    report = db.query(AbuseReport).filter(AbuseReport.id == rid).first()
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.get("/admin/abuse-reports/{report_id}", response_model=ReportRow)
async def get_abuse_report(
    report_id: str,
    _superadmin: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Single-report fetch with the same enrichment shape as the list rows.

    The review screen reads this AFTER calling /reveal (which flips the
    report to 'reviewing'), so the list endpoint's default status='pending'
    filter would silently exclude the row. Fetch by primary key instead.
    """
    report = _load_report_or_404(report_id, db)
    image = db.query(Image).filter(Image.id == report.image_id).first()
    event = db.query(Event).filter(Event.id == report.event_id).first()
    reviewer = None
    if report.reviewed_by:
        reviewer = db.query(User).filter(User.id == report.reviewed_by).first()

    dup_window = datetime.now(timezone.utc) - timedelta(
        hours=settings.abuse_report_image_dedupe_window_hours
    )
    duplicate_count = (
        db.query(func.count(AbuseReport.id))
        .filter(AbuseReport.image_id == report.image_id)
        .filter(AbuseReport.status.in_(("pending", "reviewing")))
        .filter(AbuseReport.created_at >= dup_window)
        .scalar() or 0
    )
    duplicate_count = max(0, duplicate_count - 1)

    sr_flag = False  # disabled — see ReportRow.is_possible_self_report

    ban_state = None
    if report.reporter_ip:
        try:
            if redis_client.exists(_PERMABAN_KEY.format(ip=report.reporter_ip)):
                ban_state = "permaban"
            elif redis_client.exists(_SOFTBAN_KEY.format(ip=report.reporter_ip)):
                ban_state = "softban"
        except Exception:
            pass

    return ReportRow(
        id=str(report.id),
        image_id=str(report.image_id),
        event_id=str(report.event_id),
        event_name=event.name if event else None,
        event_slug=event.slug if event else None,
        filename=image.filename if image else None,
        uploaded_at=to_utc_iso(image.uploaded_at) if image and image.uploaded_at else None,
        category=report.category,
        description=report.description,
        reporter_email=report.reporter_email,
        reporter_ip=report.reporter_ip,
        status=report.status,
        action_taken=report.action_taken,
        notes=report.notes,
        created_at=to_utc_iso(report.created_at),
        reviewed_at=to_utc_iso(report.reviewed_at) if report.reviewed_at else None,
        reviewed_by_email=reviewer.email if reviewer else None,
        duplicate_count=duplicate_count,
        is_possible_self_report=sr_flag,
        reporter_ban_state=ban_state,
        image_status=image.status if image else None,
    )


@router.post(
    "/admin/abuse-reports/{report_id}/reveal",
    response_model=RevealResponse,
)
async def reveal_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Mint a 5-minute signed abuse_review URL and record the access.

    First reveal flips status to 'reviewing' and stamps reviewed_at /
    reviewed_by. Subsequent reveals do NOT clobber those fields
    (first-reviewer wins) but DO write a fresh abuse_review_view audit
    row every time — re-opening a closed report is also traceable.
    """
    report = _load_report_or_404(report_id, db)

    first_review = report.status == "pending"
    if first_review:
        report.status = "reviewing"
        report.reviewed_at = datetime.now(timezone.utc)
        report.reviewed_by = current_user.id
    db.commit()
    db.refresh(report)

    review_url = generate_signed_abuse_review_url(
        event_id=report.event_id,
        image_id=report.image_id,
        expires_minutes=5,
    )

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_view",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
            "first_review": first_review,
        },
    )

    reviewer_email = (
        db.query(User.email).filter(User.id == report.reviewed_by).scalar()
        if report.reviewed_by else None
    )
    return RevealResponse(
        review_url=review_url,
        expires_in=5 * 60,
        status=report.status,
        reviewed_at=to_utc_iso(report.reviewed_at) if report.reviewed_at else None,
        reviewed_by_email=reviewer_email,
    )


def _ensure_actionable(report: AbuseReport) -> None:
    """Block actions on reports in genuinely terminal status.

    Kept for callers that don't have a specific target (still used by
    the legacy /quarantine path which can't be re-applied to an already
    -quarantined report). Most action endpoints now use the explicit
    transition map below instead.
    """
    if report.status in ("dismissed", "removed"):
        raise HTTPException(
            status_code=409,
            detail=f"Report already actioned (status={report.status}).",
        )


# Explicit valid transitions: keys are report.status, values are statuses
# the report can transition INTO. 'dismissed' and 'removed' are terminal
# in both directions — once closed, the row stays closed. 'quarantined'
# is special: the report is closed-ish (image is hidden from guests),
# but the operator can still:
#   * dismiss it (close without un-quarantining; image stays hidden)
#   * delete the underlying image (escalate to permanent removal)
#   * call the /restore action (un-quarantines the image; the report
#     row's own status is NOT mutated by /restore — that's an image-
#     state action, not a report-state transition).
_VALID_REPORT_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"reviewing", "dismissed", "quarantined", "removed"},
    "reviewing": {"dismissed", "quarantined", "removed"},
    "quarantined": {"dismissed", "removed"},
    "dismissed": set(),
    "removed": set(),
}


def _ensure_transition_allowed(report: AbuseReport, target: str) -> None:
    """Raise 409 if the report can't transition from its current status
    to ``target``. Used by the dismiss/quarantine/delete action endpoints
    so quarantine→quarantine, dismissed→dismissed, etc. are blocked
    consistently (and tests can pin the rules)."""
    allowed = _VALID_REPORT_TRANSITIONS.get(report.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition report from status='{report.status}' "
                f"to '{target}'."
            ),
        )


@router.post(
    "/admin/abuse-reports/{report_id}/quarantine",
    response_model=ActionResponse,
)
async def quarantine_image(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Hide the image from guests by flipping Image.status='quarantined'.

    Photo bytes stay in MinIO, the DB row stays, but every guest endpoint
    filters to status IN ('indexed', 'no_faces') so the image is no
    longer served. /admin/abuse-reports/{id}/reveal still mints an
    abuse_review URL since the photo route bypasses the status check
    for that photo_type.
    """
    report = _load_report_or_404(report_id, db)
    _ensure_transition_allowed(report, "quarantined")

    image = db.query(Image).filter(Image.id == report.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="image no longer exists")

    image.status = "quarantined"
    report.status = "quarantined"
    report.action_taken = "quarantine"
    db.commit()

    cache_delete_pattern(f"gallery:{report.event_id}:*")
    cache_delete_pattern(f"share:{report.event_id}:{report.image_id}")

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_quarantine",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
        },
    )
    return ActionResponse(message="Image quarantined.", status=report.status)


@router.post(
    "/admin/abuse-reports/{report_id}/restore",
    response_model=ActionResponse,
)
async def restore_image(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Un-quarantine the image attached to a report.

    Operator quarantined and later decided the photo is fine — flip
    Image.status back. We derive the post-restore status from face_count
    so an image with detected faces returns to 'indexed' and a face-less
    one returns to 'no_faces'. The report row itself is NOT mutated by
    this action; the operator may still dismiss it separately if they
    want to close the report. Writes an abuse_review_restore audit row.
    """
    report = _load_report_or_404(report_id, db)
    image = db.query(Image).filter(Image.id == report.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="image no longer exists")
    if image.status != "quarantined":
        raise HTTPException(
            status_code=409,
            detail=f"Image is not quarantined (status={image.status}).",
        )

    restored_status = "indexed" if (image.face_count or 0) > 0 else "no_faces"
    image.status = restored_status
    db.commit()

    cache_delete_pattern(f"gallery:{report.event_id}:*")
    cache_delete_pattern(f"share:{report.event_id}:{report.image_id}")

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_restore",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "restored_status": restored_status,
            "category": report.category,
        },
    )
    return ActionResponse(
        message="Image restored.",
        status=restored_status,
    )


@router.post(
    "/admin/abuse-reports/{report_id}/delete-photo",
    response_model=ActionResponse,
)
async def delete_photo_for_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Permanently remove the image (MinIO + CompreFace + DB row).

    Reuses the tombstone helpers from storage_cleanup so a transient
    MinIO / CompreFace outage records a retryable cleanup task instead
    of orphaning storage.
    """
    report = _load_report_or_404(report_id, db)
    _ensure_transition_allowed(report, "removed")

    image = db.query(Image).filter(Image.id == report.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="image no longer exists")

    # Snapshot every field we'll read post-commit. FK on abuse_reports
    # .image_id is now ON DELETE SET NULL so the report row survives the
    # image delete with image_id=NULL — but we still want the audit
    # metadata to carry the original image_id, so snapshot first.
    snap_report_id = str(report.id)
    snap_image_id = str(report.image_id)
    snap_category = report.category
    snap_event_id = report.event_id
    snap_filename = image.filename

    # CompreFace subjects per face — tombstone on failure.
    faces = db.query(Face).filter(Face.image_id == image.id).all()
    for face in faces:
        if face.compreface_subject_id:
            safe_delete_compreface_subject(db, face.compreface_subject_id, commit=False)

    # MinIO original + thumb — tombstone on failure.
    safe_delete_image_photo(db, snap_event_id, image.id, commit=False)

    # Mark the report removed BEFORE the image delete. The FK is now
    # ON DELETE SET NULL so the report row survives; image_id flips to
    # NULL automatically as part of the same transaction. Face rows
    # cascade-delete with the image normally.
    report.status = "removed"
    report.action_taken = "remove"
    db.delete(image)
    db.commit()

    cache_delete_pattern(f"gallery:{snap_event_id}:*")
    cache_delete_pattern(f"share:{snap_event_id}:{snap_image_id}")

    log_action(
        db=db,
        event_id=snap_event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_delete",
        metadata={
            "report_id": snap_report_id,
            "image_id": snap_image_id,
            "original_filename": snap_filename,
            "category": snap_category,
        },
    )
    return ActionResponse(message="Photo permanently removed.", status="removed")


class DismissBySourceRequest(BaseModel):
    reporter_ip: Optional[str] = None
    reporter_email: Optional[str] = None


class DismissBySourceResponse(BaseModel):
    dismissed: int


@router.post(
    "/admin/abuse-reports/dismiss-by-source",
    response_model=DismissBySourceResponse,
)
async def dismiss_by_source(
    req: DismissBySourceRequest,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Bulk-dismiss every pending/reviewing report from a single source.

    Takes either reporter_ip or reporter_email (or both). Each dismissed
    row gets its own abuse_review_dismiss audit row so the per-event
    timeline still surfaces each closure individually.
    """
    if not req.reporter_ip and not req.reporter_email:
        raise HTTPException(status_code=400, detail="reporter_ip or reporter_email required")

    q = db.query(AbuseReport).filter(
        AbuseReport.status.in_(("pending", "reviewing"))
    )
    if req.reporter_ip:
        q = q.filter(AbuseReport.reporter_ip == req.reporter_ip)
    if req.reporter_email:
        q = q.filter(AbuseReport.reporter_email == req.reporter_email.lower())

    targets = q.all()
    for r in targets:
        r.status = "dismissed"
        r.action_taken = "dismiss"
    db.commit()

    for r in targets:
        log_action(
            db=db, event_id=r.event_id, actor_type="admin",
            actor_id=current_user.id, action="abuse_review_dismiss",
            metadata={
                "report_id": str(r.id),
                "image_id": str(r.image_id),
                "category": r.category,
                "bulk_source_ip": req.reporter_ip,
                "bulk_source_email": req.reporter_email,
            },
        )

    return DismissBySourceResponse(dismissed=len(targets))


class ClearBanRequest(BaseModel):
    reporter_ip: str


@router.post("/admin/abuse-reports/clear-ban", response_model=ActionResponse)
async def clear_reporter_ban(
    req: ClearBanRequest,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Drop the soft/permaban Redis flags for a reporter IP.

    Operators clear a ban after confirming the reports were legitimate
    misjudgments (e.g. real CSAM reports that got actioned as dismiss
    because the reporter described the wrong category). Removes both
    flags so the reporter can submit again immediately.
    """
    try:
        redis_client.delete(_PERMABAN_KEY.format(ip=req.reporter_ip))
        redis_client.delete(_SOFTBAN_KEY.format(ip=req.reporter_ip))
    except Exception as e:
        logger.error("Failed to clear reporter ban ip=%s: %s", req.reporter_ip, e)
        raise HTTPException(status_code=503, detail="Could not reach Redis to clear ban")

    log_action(
        db=db, event_id=None, actor_type="admin", actor_id=current_user.id,
        action="abuse_report_ban_cleared",
        metadata={"reporter_ip": req.reporter_ip},
    )
    return ActionResponse(message="Ban cleared.", status="cleared")


@router.post(
    "/admin/abuse-reports/{report_id}/dismiss",
    response_model=ActionResponse,
)
async def dismiss_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Close as not-abuse. Image is untouched (including if it's still
    quarantined — use POST /restore separately to un-quarantine)."""
    report = _load_report_or_404(report_id, db)
    _ensure_transition_allowed(report, "dismissed")

    report.status = "dismissed"
    report.action_taken = "dismiss"
    db.commit()

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_dismiss",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
        },
    )
    return ActionResponse(message="Report dismissed.", status="dismissed")
