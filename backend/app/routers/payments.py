"""Payment and billing router for Stripe integration."""

import stripe
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Event, EventTier, Payment
from app.config import settings
from app.tiers import TIER_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = settings.stripe_secret_key


class CreateCheckoutRequest(BaseModel):
    event_id: str
    tier_name: str  # "standard" or "premium"


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class EventTierResponse(BaseModel):
    event_id: str
    tier_name: str
    photo_limit: int
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
                "photo_limit": v["photo_limit"],
                "price_cents": v["price_cents"],
                "currency": v["currency"],
            }
            for k, v in TIER_CONFIG.items()
        },
    }


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    req: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session to upgrade an event tier."""
    # Validate event ownership
    try:
        event_uuid = uuid.UUID(req.event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your event")

    # Validate tier
    if req.tier_name not in TIER_CONFIG or req.tier_name == "free":
        raise HTTPException(status_code=400, detail="Invalid tier for purchase")

    tier_config = TIER_CONFIG[req.tier_name]

    # Check if event already has this tier or higher
    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    if event_tier and event_tier.tier_name == req.tier_name and event_tier.is_active:
        raise HTTPException(status_code=400, detail="Event already on this tier")

    # Create Stripe Checkout Session
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": tier_config["currency"],
                        "product_data": {
                            "name": f"PicUr {tier_config['name']} - {event.name}",
                            "description": f"Up to {tier_config['photo_limit']} photos for your event",
                        },
                        "unit_amount": tier_config["price_cents"],
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{settings.frontend_url}/admin/events/{req.event_id}?payment=success",
            cancel_url=f"{settings.frontend_url}/admin/events/{req.event_id}?payment=cancelled",
            metadata={
                "event_id": str(event_uuid),
                "tier_name": req.tier_name,
                "user_id": str(current_user.id),
            },
            customer_email=current_user.email,
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

    # Create pending payment record
    payment = Payment(
        event_tier_id=event_tier.id if event_tier else None,
        user_id=current_user.id,
        stripe_checkout_session_id=session.id,
        amount_cents=tier_config["price_cents"],
        currency=tier_config["currency"],
        status="pending",
        metadata_={"tier_name": req.tier_name, "event_id": str(event_uuid)},
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
    """Activate the event tier after successful payment."""
    checkout_session_id = session["id"]

    # Idempotency: check if already processed
    payment = (
        db.query(Payment)
        .filter(Payment.stripe_checkout_session_id == checkout_session_id)
        .first()
    )

    if not payment:
        logger.warning(f"Payment record not found for session {checkout_session_id}")
        return

    if payment.status == "completed":
        logger.info(f"Payment {checkout_session_id} already processed (idempotent)")
        return

    # Extract metadata
    metadata = session.get("metadata", {})
    event_id = uuid.UUID(metadata["event_id"])
    tier_name = metadata["tier_name"]
    tier_config = TIER_CONFIG[tier_name]

    # Update or create EventTier
    event_tier = db.query(EventTier).filter(EventTier.event_id == event_id).first()
    if event_tier:
        event_tier.tier_name = tier_name
        event_tier.photo_limit = tier_config["photo_limit"]
        event_tier.price_cents = tier_config["price_cents"]
        event_tier.is_active = True
        event_tier.activated_at = datetime.utcnow()
    else:
        event_tier = EventTier(
            event_id=event_id,
            tier_name=tier_name,
            photo_limit=tier_config["photo_limit"],
            price_cents=tier_config["price_cents"],
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(event_tier)
        db.flush()

    # Update payment record
    payment.status = "completed"
    payment.stripe_payment_intent_id = session.get("payment_intent")
    payment.event_tier_id = event_tier.id

    db.commit()
    logger.info(f"Event {event_id} upgraded to {tier_name} tier")


def _handle_checkout_expired(session: dict, db: Session):
    """Mark payment as failed when checkout session expires."""
    payment = (
        db.query(Payment)
        .filter(Payment.stripe_checkout_session_id == session["id"])
        .first()
    )
    if payment and payment.status == "pending":
        payment.status = "failed"
        db.commit()


@router.get("/event/{event_id}/tier", response_model=EventTierResponse)
async def get_event_tier(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current tier info for an event."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your event")

    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    if not event_tier:
        return EventTierResponse(
            event_id=event_id,
            tier_name="free",
            photo_limit=25,
            is_active=True,
            activated_at=None,
        )

    return EventTierResponse(
        event_id=event_id,
        tier_name=event_tier.tier_name,
        photo_limit=event_tier.photo_limit,
        is_active=event_tier.is_active,
        activated_at=event_tier.activated_at.isoformat()
        if event_tier.activated_at
        else None,
    )
