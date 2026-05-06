"""Payment and billing router for Stripe integration (user-level tiers)."""

import stripe
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Event, UserTier, Payment
from app.config import settings
from app.tiers import TIER_CONFIG, TIER_ORDER, get_upgrade_price, get_effective_limits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = settings.stripe_secret_key


class CreateCheckoutRequest(BaseModel):
    tier_name: str  # "premium" or "premium_plus"


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class MyTierResponse(BaseModel):
    tier_name: str
    max_events: int
    max_photos_per_event: int
    events_used: int
    is_active: bool
    activated_at: Optional[str] = None


@router.get("/config")
async def get_payment_config():
    """Return publishable key and tier pricing for frontend."""
    return {
        "publishable_key": settings.stripe_publishable_key,
        "tiers": {
            k: {
                "name": v["name"],
                "max_events": v["max_events"],
                "max_photos_per_event": v["max_photos_per_event"],
                "price_cents": v["price_cents"],
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
    """Get current user's tier and usage stats."""
    user_tier = db.query(UserTier).filter(UserTier.user_id == current_user.id).first()

    if not user_tier:
        # Auto-create free tier
        user_tier = UserTier(
            user_id=current_user.id,
            tier_name="free",
            max_events=1,
            max_photos_per_event=50,
            price_cents=0,
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(user_tier)
        db.commit()
        db.refresh(user_tier)

    events_used = db.query(func.count(Event.id)).filter(
        Event.owner_user_id == current_user.id
    ).scalar() or 0

    limits = get_effective_limits(user_tier)
    return MyTierResponse(
        tier_name=limits["tier_name"],
        max_events=limits["max_events"],
        max_photos_per_event=limits["max_photos_per_event"],
        events_used=events_used,
        is_active=user_tier.is_active,
        activated_at=user_tier.activated_at.isoformat() if user_tier.activated_at else None,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    req: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session to upgrade user tier."""
    # Validate tier
    if req.tier_name not in TIER_CONFIG or req.tier_name == "free":
        raise HTTPException(status_code=400, detail="Invalid tier for purchase")

    if req.tier_name not in TIER_ORDER:
        raise HTTPException(status_code=400, detail="Cannot purchase custom tier")

    # Get current user tier
    user_tier = db.query(UserTier).filter(UserTier.user_id == current_user.id).first()
    current_tier_name = user_tier.tier_name if user_tier else "free"

    # Validate upgrade path
    if current_tier_name not in TIER_ORDER:
        raise HTTPException(status_code=400, detail="Cannot upgrade from custom tier via checkout")

    current_idx = TIER_ORDER.index(current_tier_name)
    target_idx = TIER_ORDER.index(req.tier_name)

    if target_idx <= current_idx:
        raise HTTPException(status_code=400, detail="Target tier must be higher than current tier")

    # Calculate price (upgrade difference)
    price_cents = get_upgrade_price(current_tier_name, req.tier_name)
    tier_config = TIER_CONFIG[req.tier_name]

    # Create Stripe Checkout Session
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": tier_config["currency"],
                        "product_data": {
                            "name": f"PicUr {tier_config['name']}",
                            "description": f"Up to {tier_config['max_events']} events, {tier_config['max_photos_per_event']} photos per event",
                        },
                        "unit_amount": price_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{settings.frontend_url}/admin/events?payment=success",
            cancel_url=f"{settings.frontend_url}/admin/events?payment=cancelled",
            metadata={
                "tier_name": req.tier_name,
                "user_id": str(current_user.id),
                "previous_tier": current_tier_name,
            },
            customer_email=current_user.email,
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

    # Create pending payment record
    payment = Payment(
        user_id=current_user.id,
        tier_name=req.tier_name,
        stripe_checkout_session_id=session.id,
        amount_cents=price_cents,
        currency=tier_config["currency"],
        status="pending",
        metadata_={"tier_name": req.tier_name, "previous_tier": current_tier_name},
    )
    db.add(payment)
    db.commit()

    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events. No JWT auth — verified by Stripe signature."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session, db)
    elif event["type"] == "checkout.session.expired":
        session = event["data"]["object"]
        _handle_checkout_expired(session, db)

    return {"status": "ok"}


def _handle_checkout_completed(session: dict, db: Session):
    """Activate/upgrade user tier after successful payment.

    Idempotency: lock the Payment row before checking status so two concurrent webhook
    deliveries from Stripe (it retries on timeout) cannot both pass the "pending" check
    and double-apply the tier upgrade.
    """
    checkout_session_id = session["id"]

    payment = (
        db.query(Payment)
        .filter(Payment.stripe_checkout_session_id == checkout_session_id)
        .with_for_update()
        .first()
    )

    if not payment:
        logger.warning(f"Payment record not found for session {checkout_session_id}")
        return

    if payment.status != "pending":
        logger.info(f"Payment {checkout_session_id} status={payment.status}, skip (idempotent)")
        return

    metadata = session.get("metadata", {})
    user_id = uuid.UUID(metadata["user_id"])
    tier_name = metadata["tier_name"]
    tier_config = TIER_CONFIG[tier_name]

    # Lock UserTier row too — same row may be racing with admin tier override
    user_tier = (
        db.query(UserTier)
        .filter(UserTier.user_id == user_id)
        .with_for_update()
        .first()
    )
    if user_tier:
        user_tier.tier_name = tier_name
        user_tier.max_events = tier_config["max_events"]
        user_tier.max_photos_per_event = tier_config["max_photos_per_event"]
        user_tier.price_cents = tier_config["price_cents"]
        user_tier.is_active = True
        user_tier.activated_at = datetime.utcnow()
    else:
        user_tier = UserTier(
            user_id=user_id,
            tier_name=tier_name,
            max_events=tier_config["max_events"],
            max_photos_per_event=tier_config["max_photos_per_event"],
            price_cents=tier_config["price_cents"],
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(user_tier)

    payment.status = "completed"
    payment.stripe_payment_intent_id = session.get("payment_intent")

    db.commit()
    logger.info(f"User {user_id} upgraded to {tier_name} tier")


def _handle_checkout_expired(session: dict, db: Session):
    """Mark payment as failed when checkout session expires (locked for safety)."""
    payment = (
        db.query(Payment)
        .filter(Payment.stripe_checkout_session_id == session["id"])
        .with_for_update()
        .first()
    )
    if payment and payment.status == "pending":
        payment.status = "failed"
        db.commit()
