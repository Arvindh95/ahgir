"""Payment and billing router for Stripe subscription integration."""

import stripe
import logging
import uuid
from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from pydantic import BaseModel

from app.auth import get_current_user
from app.cache import cache_delete_pattern
from app.database import get_db
from app.models import User, Event, UserTier, Payment
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

    _rebalance_event_status(user_tier.user_id, cfg["max_events"], db)


def _rebalance_event_status(user_id: uuid.UUID, max_active: int, db: Session) -> None:
    """Reconcile event status with active-event quota.

    - If active count > max: freeze oldest excess (preserve newest)
    - If active count < max and frozen events exist: unfreeze newest frozen up to max
    Expired events untouched (retention scheduler owns them).
    """
    active_events = (
        db.query(Event)
        .filter(Event.owner_user_id == user_id, Event.status == 'active')
        .order_by(asc(Event.created_at))
        .all()
    )
    active_count = len(active_events)

    if active_count > max_active:
        excess = active_count - max_active
        flipped = active_events[:excess]
        for ev in flipped:
            ev.status = 'frozen'
        _invalidate_event_public_caches(flipped)
        logger.info(f"Froze {excess} oldest events for user {user_id} (cap dropped to {max_active})")
        return

    slots_available = max_active - active_count
    if slots_available <= 0:
        return

    frozen_events = (
        db.query(Event)
        .filter(Event.owner_user_id == user_id, Event.status == 'frozen')
        .order_by(desc(Event.created_at))
        .limit(slots_available)
        .all()
    )
    for ev in frozen_events:
        ev.status = 'active'
    if frozen_events:
        _invalidate_event_public_caches(frozen_events)
        logger.info(f"Unfroze {len(frozen_events)} events for user {user_id} (cap raised to {max_active})")


def _invalidate_event_public_caches(events) -> None:
    """Drop guest-facing caches for events whose status just changed.

    Without this, /e/{slug} keeps serving the cached event_info payload (and
    /share/{event_id}/{image_id} keeps serving cached signed URLs) for up to
    five minutes after a freeze/unfreeze, which is long enough for guests to
    keep browsing or downloading from a frozen event.
    """
    for ev in events:
        if ev.slug:
            cache_delete_pattern(f"event_info:{ev.slug}")
        cache_delete_pattern(f"share:{ev.id}:*")
        cache_delete_pattern(f"gallery:{ev.id}:*")


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

    customer_id = _get_or_create_stripe_customer(current_user, user_tier)
    db.flush()

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

    handlers_with_ts = {
        "customer.subscription.created": _handle_subscription_upsert,
        "customer.subscription.updated": _handle_subscription_upsert,
        "customer.subscription.deleted": _handle_subscription_deleted,
    }
    handlers_no_ts = {
        "checkout.session.completed": _handle_checkout_completed,
        "invoice.paid": _handle_invoice_paid,
        "invoice.payment_failed": _handle_invoice_payment_failed,
    }
    handler_with_ts = handlers_with_ts.get(etype)
    handler_no_ts = handlers_no_ts.get(etype)
    if handler_with_ts:
        try:
            handler_with_ts(obj, db, event_created)
        except Exception as e:
            logger.exception(f"Webhook handler {etype} failed: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Webhook handler failed")
    elif handler_no_ts:
        try:
            handler_no_ts(obj, db)
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


def _is_event_stale(user_tier: UserTier, event_created: Optional[int]) -> bool:
    """True if `event_created` is older than the last subscription event we
    already applied for this user_tier. Stripe webhook delivery is not
    ordered, so a delayed `customer.subscription.updated` arriving after a
    `customer.subscription.deleted` would otherwise reapply the paid tier.
    """
    if event_created is None or user_tier.last_subscription_event_at is None:
        return False
    return datetime.utcfromtimestamp(int(event_created)) < user_tier.last_subscription_event_at


def _handle_subscription_upsert(subscription: dict, db: Session, event_created: Optional[int] = None) -> None:
    """Sync UserTier with Stripe subscription state. Source of truth for tier flips."""
    sub_id = subscription["id"]
    customer_id = subscription["customer"]
    sub_status = subscription["status"]
    cancel_at_period_end = bool(_g(subscription, "cancel_at_period_end", False))

    # Stripe API 2024+ moved current_period_end onto SubscriptionItem.
    items_obj = _g(subscription, "items") or {}
    items = _g(items_obj, "data") or []
    current_period_end = None
    if items:
        current_period_end = _g(items[0], "current_period_end")
    if current_period_end is None:
        current_period_end = _g(subscription, "current_period_end")

    tier_name, interval = _resolve_tier_from_subscription(subscription)
    if not tier_name:
        logger.warning(f"Cannot resolve tier_name for subscription {sub_id}")
        return

    user_tier = (
        db.query(UserTier)
        .filter(UserTier.stripe_customer_id == customer_id)
        .with_for_update()
        .first()
    )
    if not user_tier:
        logger.warning(f"No UserTier for stripe customer {customer_id}")
        return

    # Reject out-of-order deliveries (e.g., stale subscription.updated arriving
    # after subscription.deleted has already cleared this user's tier).
    if _is_event_stale(user_tier, event_created):
        logger.info(
            f"Skipping stale subscription event for {sub_id}: "
            f"event ts={event_created} < last_applied={user_tier.last_subscription_event_at}"
        )
        return

    # Active or trialing → grant tier; anything else (incomplete, past_due) holds current state
    if sub_status in ("active", "trialing"):
        _apply_tier_limits(user_tier, tier_name, interval, db)
    elif sub_status in ("canceled", "incomplete_expired", "unpaid"):
        _downgrade_to_free(user_tier, db)
    # 'past_due' / 'incomplete' → leave tier in place; grace handled by cron

    user_tier.stripe_subscription_id = sub_id
    user_tier.subscription_status = sub_status
    user_tier.cancel_at_period_end = cancel_at_period_end
    user_tier.current_period_end = (
        datetime.utcfromtimestamp(current_period_end) if current_period_end else None
    )
    user_tier.activated_at = datetime.utcnow()
    if event_created is not None:
        user_tier.last_subscription_event_at = datetime.utcfromtimestamp(int(event_created))
    db.commit()
    logger.info(f"Subscription {sub_id} synced: tier={tier_name} status={sub_status} user={user_tier.user_id}")


def _handle_subscription_deleted(subscription: dict, db: Session, event_created: Optional[int] = None) -> None:
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
    if _is_event_stale(user_tier, event_created):
        logger.info(f"Skipping stale subscription.deleted for {sub_id}")
        return
    _downgrade_to_free(user_tier, db)
    if event_created is not None:
        user_tier.last_subscription_event_at = datetime.utcfromtimestamp(int(event_created))
    db.commit()
    logger.info(f"User {user_tier.user_id} downgraded to free (subscription deleted)")


def _handle_invoice_paid(invoice: dict, db: Session) -> None:
    """Record successful subscription invoice as a Payment row."""
    invoice_id = invoice["id"]
    sub_id = _g(invoice, "subscription")
    if not sub_id:
        return  # one-off invoice (not a subscription) — ignore

    existing = db.query(Payment).filter(Payment.stripe_invoice_id == invoice_id).first()
    if existing:
        return  # idempotent

    customer_id = invoice["customer"]
    user_tier = db.query(UserTier).filter(UserTier.stripe_customer_id == customer_id).first()
    if not user_tier:
        logger.warning(f"invoice.paid for unknown customer {customer_id}")
        return

    payment = Payment(
        user_id=user_tier.user_id,
        tier_name=user_tier.tier_name,
        billing_interval=user_tier.billing_interval,
        stripe_invoice_id=invoice_id,
        stripe_subscription_id=sub_id,
        amount_cents=_g(invoice, "amount_paid", 0),
        currency=_g(invoice, "currency", "myr"),
        status="completed",
        metadata_={"invoice_number": _g(invoice, "number")},
    )
    db.add(payment)
    db.commit()


def _handle_invoice_payment_failed(invoice: dict, db: Session) -> None:
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
    user_tier.subscription_status = "past_due"
    db.commit()
    logger.warning(f"Subscription {sub_id} payment failed - user {user_tier.user_id} marked past_due")
