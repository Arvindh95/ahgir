"""Payment and billing router for Stripe subscription integration."""

import stripe
import logging
from datetime import datetime, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db
from app.event_status import rebalance_event_status
from app.models import User, UserTier, Payment
from app.config import settings
from app.tiers import (
    TIER_CONFIG,
    PURCHASABLE_TIERS,
    get_tier_config,
    get_stripe_price_id,
    get_effective_limits,
    get_active_event_count,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = settings.stripe_secret_key


# ---------- Pydantic models ----------

class CheckoutRequest(BaseModel):
    tier_name: Literal["starter", "pro"]
    interval: Literal["month", "year"]


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalResponse(BaseModel):
    portal_url: str


class TierFeatures(BaseModel):
    name: str
    max_events: int
    max_photos_per_event: int
    retention_days: int
    monthly_cents: int
    yearly_cents: int
    currency: str


class MyTierResponse(BaseModel):
    tier_name: str
    max_events: int
    max_photos_per_event: int
    retention_days: int
    active_events: int
    is_active: bool
    subscription_status: Optional[str] = None
    billing_interval: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    activated_at: Optional[str] = None


def _g(obj, key, default=None):
    """Read a field from a Stripe object or dict.

    Stripe's StripeObject supports `obj[key]` but not `obj.get(key, default)`,
    so this helper unifies access between webhook payloads (StripeObject) and
    plain dict fixtures used in tests.
    """
    try:
        val = obj[key]
    except (KeyError, AttributeError, TypeError):
        return default
    return val if val is not None else default


# ---------- Helpers ----------

def _get_or_create_user_tier(user: User, db: Session) -> UserTier:
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.user_id == user.id)
        .with_for_update()
        .first()
    )
    if user_tier:
        return user_tier
    cfg = TIER_CONFIG["free"]
    user_tier = UserTier(
        user_id=user.id,
        tier_name="free",
        max_events=cfg["max_events"],
        max_photos_per_event=cfg["max_photos_per_event"],
        retention_days=cfg["retention_days"],
        price_cents=0,
        is_active=True,
        activated_at=datetime.utcnow(),
    )
    db.add(user_tier)
    db.flush()
    return user_tier


def _get_or_create_stripe_customer(user: User, user_tier: UserTier) -> str:
    """Create a Stripe Customer if missing, persist the id on UserTier."""
    if user_tier.stripe_customer_id:
        return user_tier.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id)},
    )
    user_tier.stripe_customer_id = customer.id
    return customer.id


def _checkout_matches_request(payment: Payment, tier_name: str, interval: str) -> bool:
    return payment.tier_name == tier_name and payment.billing_interval == interval


def _expire_mismatched_checkout(payment: Payment) -> None:
    """Expire an open Checkout Session that no longer matches the user's choice."""
    try:
        stripe.checkout.Session.expire(payment.stripe_checkout_session_id)
    except stripe.StripeError as e:
        logger.warning("Could not expire mismatched checkout session %s: %s", payment.stripe_checkout_session_id, e)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHECKOUT_PENDING_DIFFERENT_PLAN",
                "message": "A checkout is already pending for another plan. Try again in a moment.",
            },
        )
    payment.status = "failed"


def _get_reusable_checkout_session(
    user: User,
    db: Session,
    tier_name: str,
    interval: str,
) -> Optional[CheckoutResponse]:
    """Return a matching open Checkout Session, or block while a completed one settles."""
    now = datetime.utcnow()
    pending_cutoff = now - timedelta(hours=25)
    processing_cutoff = now - timedelta(hours=1)
    candidates = (
        db.query(Payment)
        .filter(
            Payment.user_id == user.id,
            Payment.stripe_checkout_session_id.isnot(None),
            or_(
                and_(Payment.status == "pending", Payment.created_at >= pending_cutoff),
                and_(Payment.status == "completed", Payment.created_at >= processing_cutoff),
            ),
        )
        .order_by(Payment.created_at.desc())
        .with_for_update()
        .all()
    )

    for payment in candidates:
        try:
            session = stripe.checkout.Session.retrieve(payment.stripe_checkout_session_id)
        except stripe.StripeError as e:
            logger.warning("Could not verify checkout session %s: %s", payment.stripe_checkout_session_id, e)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "STRIPE_UNAVAILABLE",
                    "message": "Stripe is temporarily unavailable. Please try again in a moment.",
                },
            )

        session_status = _g(session, "status")
        session_url = _g(session, "url")
        if session_status == "open" and session_url:
            if _checkout_matches_request(payment, tier_name, interval):
                return CheckoutResponse(checkout_url=session_url, session_id=payment.stripe_checkout_session_id)
            _expire_mismatched_checkout(payment)
            db.flush()
            continue
        # Only block on a *matching* completed session. A completed checkout for
        # a different tier (e.g. user paid for starter, canceled, now wants pro)
        # must not lock them out — the stale Payment row is just history.
        if session_status == "complete" and _checkout_matches_request(payment, tier_name, interval):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CHECKOUT_PROCESSING",
                    "message": "Your checkout completed and the subscription is still processing.",
                },
            )
        if session_status == "expired":
            payment.status = "failed"
            db.flush()

    return None


def _stripe_updates_locked(user_tier: UserTier) -> bool:
    """True when a superadmin manual tier override should ignore Stripe entitlement webhooks."""
    return user_tier.last_subscription_event_type == "manual_override"


def _clear_manual_stripe_override(user_tier: UserTier) -> None:
    """Drop the manual_override marker so future Stripe webhooks process.

    Critically, we keep `last_subscription_event_at` stamped to "now" — any
    delayed webhook for an orphaned old Stripe subscription (created before
    the manual override) will have `event.created < utcnow()` and so fall
    out via the staleness check. New events for a fresh subscription the
    user is about to start will have `created > utcnow()` and pass.
    """
    if not _stripe_updates_locked(user_tier):
        return
    user_tier.last_subscription_event_at = datetime.utcnow()
    user_tier.last_subscription_event_id = None
    user_tier.last_subscription_event_type = None
    user_tier.last_subscription_event_subscription_id = None


def _current_period_end_from_subscription(subscription: dict) -> Optional[int]:
    items_obj = _g(subscription, "items") or {}
    items = _g(items_obj, "data") or []
    if items:
        current_period_end = _g(items[0], "current_period_end")
        if current_period_end is not None:
            return current_period_end
    return _g(subscription, "current_period_end")


def _apply_subscription_state(user_tier: UserTier, subscription: dict, db: Session) -> bool:
    """Apply the current Stripe subscription object to UserTier without committing."""
    sub_id = subscription["id"]
    sub_status = subscription["status"]
    cancel_at_period_end = bool(_g(subscription, "cancel_at_period_end", False))
    current_period_end = _current_period_end_from_subscription(subscription)

    tier_name, interval = _resolve_tier_from_subscription(subscription)
    if not tier_name:
        logger.warning(f"Cannot resolve tier_name for subscription {sub_id}")
        return False

    if sub_status in ("active", "trialing"):
        _apply_tier_limits(user_tier, tier_name, interval, db)
        user_tier.stripe_subscription_id = sub_id
        user_tier.current_period_end = (
            datetime.utcfromtimestamp(current_period_end) if current_period_end else None
        )
        user_tier.subscription_status = sub_status
        user_tier.cancel_at_period_end = cancel_at_period_end
    elif sub_status in ("canceled", "incomplete_expired", "unpaid"):
        # _downgrade_to_free clears stripe_subscription_id, subscription_status,
        # current_period_end and cancel_at_period_end. Don't re-set them —
        # leaving everything cleared keeps the row internally consistent
        # (no live sub → no associated state).
        _downgrade_to_free(user_tier, db)
    else:
        # past_due / incomplete: keep tier limits, just refresh status fields.
        user_tier.subscription_status = sub_status
        user_tier.cancel_at_period_end = cancel_at_period_end

    user_tier.activated_at = datetime.utcnow()
    return True


def _sync_subscription_from_stripe(user_tier: UserTier, subscription_id: str, db: Session) -> bool:
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except stripe.StripeError as e:
        logger.warning("Could not fetch subscription %s after invoice.paid: %s", subscription_id, e)
        raise
    return _apply_subscription_state(user_tier, subscription, db)


def _apply_tier_limits(user_tier: UserTier, tier_name: str, interval: Optional[str], db: Session) -> None:
    """Set tier limits on UserTier and freeze/unfreeze events to match new active-event cap."""
    cfg = TIER_CONFIG.get(tier_name)
    if not cfg:
        logger.error(f"Unknown tier {tier_name} - cannot apply")
        return

    user_tier.tier_name = tier_name
    user_tier.max_events = cfg["max_events"]
    user_tier.max_photos_per_event = cfg["max_photos_per_event"]
    user_tier.retention_days = cfg["retention_days"]
    user_tier.price_cents = cfg["monthly_cents"] if interval == "month" else cfg["yearly_cents"]
    user_tier.billing_interval = interval

    rebalance_event_status(user_tier.user_id, cfg["max_events"], db)


def _downgrade_to_free(user_tier: UserTier, db: Session) -> None:
    """Drop a user back to free tier. Freezes excess events. Keeps stripe_customer_id."""
    _apply_tier_limits(user_tier, "free", None, db)
    user_tier.subscription_status = None
    user_tier.stripe_subscription_id = None
    user_tier.current_period_end = None
    user_tier.cancel_at_period_end = False
    user_tier.activated_at = datetime.utcnow()
    user_tier.is_active = True


# ---------- Routes ----------

@router.get("/config")
async def get_payment_config():
    """Return publishable key and purchasable tier definitions for the frontend."""
    return {
        "publishable_key": settings.stripe_publishable_key,
        "tiers": {
            k: {
                "name": v["name"],
                "max_events": v["max_events"],
                "max_photos_per_event": v["max_photos_per_event"],
                "retention_days": v["retention_days"],
                "monthly_cents": v["monthly_cents"],
                "yearly_cents": v["yearly_cents"],
                "currency": v["currency"],
            }
            for k, v in TIER_CONFIG.items()
        },
    }


@router.get("/my-tier", response_model=MyTierResponse)
async def get_my_tier(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_tier = _get_or_create_user_tier(current_user, db)
    db.commit()
    db.refresh(user_tier)

    limits = get_effective_limits(user_tier)
    active_count = get_active_event_count(db, current_user.id)

    return MyTierResponse(
        tier_name=limits["tier_name"],
        max_events=limits["max_events"],
        max_photos_per_event=limits["max_photos_per_event"],
        retention_days=limits["retention_days"],
        active_events=active_count,
        is_active=user_tier.is_active,
        subscription_status=user_tier.subscription_status,
        billing_interval=user_tier.billing_interval,
        current_period_end=user_tier.current_period_end.isoformat() if user_tier.current_period_end else None,
        cancel_at_period_end=user_tier.cancel_at_period_end,
        activated_at=user_tier.activated_at.isoformat() if user_tier.activated_at else None,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a subscription checkout session.

    For users with an existing active subscription, redirects to the billing
    portal instead — Stripe handles plan changes / proration there.
    """
    if req.tier_name not in PURCHASABLE_TIERS:
        raise HTTPException(status_code=400, detail="Invalid tier for purchase")

    price_id = get_stripe_price_id(req.tier_name, req.interval)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Price for {req.tier_name} ({req.interval}) not configured. Run setup_stripe_products.py.",
        )

    user_tier = _get_or_create_user_tier(current_user, db)

    # Existing active subscription → use portal for upgrade/downgrade (proration)
    if user_tier.stripe_subscription_id and user_tier.subscription_status in ("active", "trialing", "past_due"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ALREADY_SUBSCRIBED",
                "message": "You already have an active subscription. Use the billing portal to change plans.",
            },
        )

    _clear_manual_stripe_override(user_tier)

    reusable_session = _get_reusable_checkout_session(current_user, db, req.tier_name, req.interval)
    if reusable_session:
        db.commit()
        return reusable_session

    customer_id = _get_or_create_stripe_customer(current_user, user_tier)
    # Persist the new stripe_customer_id eagerly. If checkout creation fails
    # below, the customer already exists in Stripe — without the commit we'd
    # rollback the local id, then the next attempt would create a *second*
    # Stripe customer and orphan the first.
    db.commit()
    db.refresh(user_tier)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.frontend_url}/admin/billing?status=success",
            cancel_url=f"{settings.frontend_url}/admin/billing?status=cancelled",
            metadata={
                "user_id": str(current_user.id),
                "tier_name": req.tier_name,
                "interval": req.interval,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "tier_name": req.tier_name,
                    "interval": req.interval,
                }
            },
            allow_promotion_codes=True,
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

    payment = Payment(
        user_id=current_user.id,
        tier_name=req.tier_name,
        billing_interval=req.interval,
        stripe_checkout_session_id=session.id,
        amount_cents=TIER_CONFIG[req.tier_name][f"{'monthly' if req.interval == 'month' else 'yearly'}_cents"],
        currency=TIER_CONFIG[req.tier_name]["currency"],
        status="pending",
        metadata_={"tier_name": req.tier_name, "interval": req.interval},
    )
    db.add(payment)
    db.commit()

    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


@router.post("/portal", response_model=PortalResponse)
async def create_portal_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Open Stripe-hosted Billing Portal for self-serve plan/cancel/payment-method changes."""
    user_tier = _get_or_create_user_tier(current_user, db)
    if not user_tier.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No billing account yet. Subscribe first to access the billing portal.",
        )

    try:
        portal = stripe.billing_portal.Session.create(
            customer=user_tier.stripe_customer_id,
            return_url=f"{settings.frontend_url}/admin/billing",
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to open billing portal")

    db.commit()
    return PortalResponse(portal_url=portal.url)


# ---------- Webhook ----------

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    obj = event["data"]["object"]

    # Stripe Event has its own `created` timestamp distinct from the embedded
    # subscription/invoice object. Pass it to subscription handlers so they
    # can reject out-of-order deliveries.
    event_created = event.get("created")
    event_id = event.get("id")

    handlers_with_event = {
        "customer.subscription.created": _handle_subscription_upsert,
        "customer.subscription.updated": _handle_subscription_upsert,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.paid": _handle_invoice_paid,
        "invoice.payment_failed": _handle_invoice_payment_failed,
    }
    handlers_no_event = {
        "checkout.session.completed": _handle_checkout_completed,
    }
    handler_with_event = handlers_with_event.get(etype)
    handler_no_event = handlers_no_event.get(etype)
    if handler_with_event:
        try:
            handler_with_event(obj, db, event_created, event_id, etype)
        except Exception as e:
            logger.exception(f"Webhook handler {etype} failed: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Webhook handler failed")
    elif handler_no_event:
        try:
            handler_no_event(obj, db)
        except Exception as e:
            logger.exception(f"Webhook handler {etype} failed: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Webhook handler failed")
    else:
        logger.debug(f"Ignoring webhook event type: {etype}")

    return {"status": "ok"}


def _handle_checkout_completed(session: dict, db: Session) -> None:
    """Mark Payment row complete and let subscription.* handlers do the tier flip.

    Subscription handlers fire alongside this and own the UserTier mutation,
    so we just close the Payment loop here.
    """
    session_id = session["id"]
    payment = (
        db.query(Payment)
        .filter(Payment.stripe_checkout_session_id == session_id)
        .with_for_update()
        .first()
    )
    if not payment:
        logger.info(f"No Payment row for checkout session {session_id} (likely portal-initiated)")
        return
    if payment.status == "completed":
        return  # idempotent
    payment.status = "completed"
    payment.stripe_subscription_id = _g(session, "subscription")
    db.commit()


def _resolve_tier_from_invoice(invoice: dict) -> tuple[Optional[str], Optional[str]]:
    """Resolve (tier_name, interval) from a Stripe invoice's line items.

    Lets us record an accurate Payment row even when subscription sync was
    skipped (manual override or stale webhook), instead of falling back to
    whatever stale tier_name happens to be on the user_tier row.
    """
    lines_obj = _g(invoice, "lines") or {}
    lines = _g(lines_obj, "data") or []
    for line in lines:
        price_obj = _g(line, "price") or {}
        price_id = _g(price_obj, "id")
        if not price_id:
            continue
        for tn in PURCHASABLE_TIERS:
            cfg = TIER_CONFIG[tn]
            if price_id == cfg.get("stripe_price_monthly"):
                return tn, "month"
            if price_id == cfg.get("stripe_price_yearly"):
                return tn, "year"
    return None, None


def _resolve_tier_from_subscription(subscription: dict) -> tuple[Optional[str], Optional[str]]:
    """Resolve (tier_name, interval) from a Stripe subscription object.

    Source of truth is the active SubscriptionItem's Price ID — it always
    reflects the current plan, including portal-driven plan changes. The
    `metadata.tier_name` field is only set by our own checkout flow and is
    NOT updated when a customer changes plan via the Billing Portal, so
    relying on metadata first would let a downgrade keep granting the
    higher tier (or vice versa). Use metadata only when the price ID
    can't be matched.
    """
    items_obj = _g(subscription, "items") or {}
    items = _g(items_obj, "data") or []
    if items:
        price_obj = _g(items[0], "price") or {}
        price_id = _g(price_obj, "id")
        for tn in PURCHASABLE_TIERS:
            cfg = TIER_CONFIG[tn]
            if price_id == cfg.get("stripe_price_monthly"):
                return tn, "month"
            if price_id == cfg.get("stripe_price_yearly"):
                return tn, "year"

    # Fallback to metadata when the price doesn't match any known tier
    # (e.g., legacy Stripe products before a price ID rotation).
    metadata = _g(subscription, "metadata") or {}
    tier_name = _g(metadata, "tier_name")
    interval = _g(metadata, "interval")
    return tier_name, interval


def _subscription_event_datetime(event_created: Optional[int]) -> Optional[datetime]:
    if event_created is None:
        return None
    return datetime.utcfromtimestamp(int(event_created))


_DOWNGRADE_EVENT_MARKERS = {
    # Hard delete: Stripe pushed customer.subscription.deleted.
    "customer.subscription.deleted",
    # Soft delete via .updated carrying a terminal status. We mark these so
    # the same staleness logic that protects against same-second reactivation
    # after .deleted also covers .updated → canceled / unpaid / incomplete_expired.
    "customer.subscription.updated.terminal",
    # Manual operator action; should never be undone by a delayed Stripe event.
    "manual_override",
    # Daily scheduler stamped the row after grace period expired.
    "grace_period_downgrade",
}


def _is_event_stale(
    user_tier: UserTier,
    event_created: Optional[int],
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
    subscription_id: Optional[str] = None,
) -> bool:
    """True if `event_created` is older than the last subscription event we
    already applied for this user_tier.

    Stripe webhook delivery is not ordered and `created` is second-granularity.
    Two distinct events for the same subscription can share a created-second
    in either order. Rule: once a "downgrade-applying" event has been recorded
    for a subscription, any same-second non-downgrade event for that
    subscription must be rejected as stale — otherwise a delayed .updated with
    status=active could re-grant the paid tier after .deleted (or
    .updated→canceled) already took it away.
    """
    if event_id and user_tier.last_subscription_event_id == event_id:
        return True

    event_dt = _subscription_event_datetime(event_created)
    if event_dt is None or user_tier.last_subscription_event_at is None:
        return False
    if event_dt < user_tier.last_subscription_event_at:
        return True
    if (
        event_dt == user_tier.last_subscription_event_at
        and user_tier.last_subscription_event_type in _DOWNGRADE_EVENT_MARKERS
        and user_tier.last_subscription_event_subscription_id == subscription_id
    ):
        # If the incoming event is itself a deletion of the same sub, accept
        # it — replaying a delete is harmless and lets the .deleted webhook
        # land after a .updated→canceled. Anything else is a re-activation
        # attempt for an already-downgraded sub: reject.
        if event_type == "customer.subscription.deleted":
            return False
        return True
    return False


def _is_invoice_failure_stale(
    user_tier: UserTier,
    event_created: Optional[int],
    event_id: Optional[str],
    event_type: Optional[str],
    subscription_id: Optional[str],
) -> bool:
    """Reject delayed invoice failures that arrive after a recovery event."""
    if _is_event_stale(user_tier, event_created, event_id, event_type, subscription_id):
        return True

    event_dt = _subscription_event_datetime(event_created)
    if event_dt is None or user_tier.last_subscription_event_at is None:
        return False
    return (
        event_dt == user_tier.last_subscription_event_at
        and user_tier.last_subscription_event_subscription_id == subscription_id
        and user_tier.last_subscription_event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "invoice.paid",
        }
    )


def _mark_subscription_event_applied(
    user_tier: UserTier,
    event_created: Optional[int],
    event_id: Optional[str],
    event_type: Optional[str],
    subscription_id: Optional[str],
) -> None:
    event_dt = _subscription_event_datetime(event_created)
    if event_dt is not None:
        user_tier.last_subscription_event_at = event_dt
    if event_id:
        user_tier.last_subscription_event_id = event_id
    if event_type:
        user_tier.last_subscription_event_type = event_type
    if subscription_id:
        user_tier.last_subscription_event_subscription_id = subscription_id


def _handle_subscription_upsert(
    subscription: dict,
    db: Session,
    event_created: Optional[int] = None,
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> None:
    """Sync UserTier with Stripe subscription state. Source of truth for tier flips."""
    sub_id = subscription["id"]
    customer_id = subscription["customer"]
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.stripe_customer_id == customer_id)
        .with_for_update()
        .first()
    )
    if not user_tier:
        logger.warning(f"No UserTier for stripe customer {customer_id}")
        return
    if _stripe_updates_locked(user_tier):
        logger.info("Skipping subscription event for %s because user %s has a manual tier override", sub_id, user_tier.user_id)
        return

    # Reject out-of-order deliveries (e.g., stale subscription.updated arriving
    # after subscription.deleted has already cleared this user's tier).
    if _is_event_stale(user_tier, event_created, event_id, event_type, sub_id):
        logger.info(
            f"Skipping stale subscription event for {sub_id}: "
            f"event id={event_id} type={event_type} ts={event_created} "
            f"last_applied={user_tier.last_subscription_event_at}"
        )
        return

    if not _apply_subscription_state(user_tier, subscription, db):
        return

    # If a subscription.updated landed us in a terminal state (canceled,
    # unpaid, incomplete_expired), stamp the event with a "terminal" marker
    # so a delayed same-second .updated→active for the same sub gets rejected
    # by the staleness guard. Without this, Stripe could land
    #   t=T  .updated status=canceled  → we downgrade
    #   t=T  .updated status=active    → we wrongly re-grant the paid tier
    # because both events share a created-second.
    marker_type = event_type
    sub_status = subscription.get("status")
    if (
        event_type == "customer.subscription.updated"
        and sub_status in ("canceled", "unpaid", "incomplete_expired")
    ):
        marker_type = "customer.subscription.updated.terminal"

    _mark_subscription_event_applied(user_tier, event_created, event_id, marker_type, sub_id)
    db.commit()
    logger.info(f"Subscription {sub_id} synced: status={sub_status} user={user_tier.user_id}")


def _handle_subscription_deleted(
    subscription: dict,
    db: Session,
    event_created: Optional[int] = None,
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> None:
    """Subscription fully canceled (period_end reached or canceled immediately) → free tier."""
    sub_id = subscription["id"]
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.stripe_subscription_id == sub_id)
        .with_for_update()
        .first()
    )
    if not user_tier:
        logger.info(f"Subscription deleted for unknown sub_id {sub_id}")
        return
    if _stripe_updates_locked(user_tier):
        logger.info("Skipping subscription.deleted for %s because user %s has a manual tier override", sub_id, user_tier.user_id)
        return
    if _is_event_stale(user_tier, event_created, event_id, event_type, sub_id):
        logger.info(f"Skipping stale subscription.deleted for {sub_id}")
        return
    _downgrade_to_free(user_tier, db)
    _mark_subscription_event_applied(user_tier, event_created, event_id, event_type, sub_id)
    db.commit()
    logger.info(f"User {user_tier.user_id} downgraded to free (subscription deleted)")


def _handle_invoice_paid(
    invoice: dict,
    db: Session,
    event_created: Optional[int] = None,
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> None:
    """Record successful subscription invoice as a Payment row."""
    invoice_id = invoice["id"]
    sub_id = _g(invoice, "subscription")
    if not sub_id:
        return  # one-off invoice (not a subscription) — ignore

    existing = db.query(Payment).filter(Payment.stripe_invoice_id == invoice_id).first()
    if existing:
        return  # idempotent

    customer_id = invoice["customer"]
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.stripe_customer_id == customer_id)
        .with_for_update()
        .first()
    )
    if not user_tier:
        logger.warning(f"invoice.paid for unknown customer {customer_id}")
        return

    if not _stripe_updates_locked(user_tier) and not _is_event_stale(user_tier, event_created, event_id, event_type, sub_id):
        # invoice.paid is often the recovery signal after past_due. Reconcile
        # the current Stripe subscription now so a missing/delayed
        # customer.subscription.updated does not leave the user downgradeable.
        # Decoupled from Payment recording: a Stripe API failure here (e.g.,
        # sub deleted from the dashboard between events) shouldn't drop the
        # invoice audit row; Stripe will retry the webhook and we'll catch up.
        try:
            if _sync_subscription_from_stripe(user_tier, sub_id, db):
                _mark_subscription_event_applied(user_tier, event_created, event_id, event_type, sub_id)
        except stripe.StripeError as e:
            logger.warning("invoice.paid sync skipped for sub %s: %s", sub_id, e)

    # Prefer the invoice's own price IDs over user_tier (which may be stale
    # when sync was skipped). user_tier values are the fallback.
    invoice_tier, invoice_interval = _resolve_tier_from_invoice(invoice)
    payment = Payment(
        user_id=user_tier.user_id,
        tier_name=invoice_tier or user_tier.tier_name,
        billing_interval=invoice_interval or user_tier.billing_interval,
        stripe_invoice_id=invoice_id,
        stripe_subscription_id=sub_id,
        amount_cents=_g(invoice, "amount_paid", 0),
        currency=_g(invoice, "currency", "usd"),
        status="completed",
        metadata_={"invoice_number": _g(invoice, "number")},
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Duplicate invoice.paid ignored for invoice %s", invoice_id)


def _handle_invoice_payment_failed(
    invoice: dict,
    db: Session,
    event_created: Optional[int] = None,
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> None:
    """Mark subscription past_due. Cron will downgrade to free after grace_period_days."""
    sub_id = _g(invoice, "subscription")
    if not sub_id:
        return
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.stripe_subscription_id == sub_id)
        .with_for_update()
        .first()
    )
    if not user_tier:
        return
    if _stripe_updates_locked(user_tier):
        logger.info("Skipping invoice.payment_failed for %s because user %s has a manual tier override", sub_id, user_tier.user_id)
        return
    if _is_invoice_failure_stale(user_tier, event_created, event_id, event_type, sub_id):
        logger.info("Skipping stale invoice.payment_failed for subscription %s", sub_id)
        return
    user_tier.subscription_status = "past_due"
    _mark_subscription_event_applied(user_tier, event_created, event_id, event_type, sub_id)
    db.commit()
    logger.warning(f"Subscription {sub_id} payment failed - user {user_tier.user_id} marked past_due")
