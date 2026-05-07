"""Tier configuration for subscription billing.

Subscriptions are billed monthly or yearly. Limits enforce active events
(events still within retention window) rather than total events created.
"""

from typing import Dict, Any, Optional
from app.config import settings


TIER_CONFIG: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Free",
        "max_events": 1,
        "max_photos_per_event": 50,
        "retention_days": 30,
        "monthly_cents": 0,
        "yearly_cents": 0,
        "currency": "usd",
        "stripe_price_monthly": None,
        "stripe_price_yearly": None,
    },
    "starter": {
        "name": "Starter",
        "max_events": 5,
        "max_photos_per_event": 500,
        "retention_days": 180,
        "monthly_cents": 900,    # $9
        "yearly_cents": 9000,    # $90 (2 months free)
        "currency": "usd",
        "stripe_price_monthly": getattr(settings, "stripe_price_starter_monthly", "") or None,
        "stripe_price_yearly": getattr(settings, "stripe_price_starter_yearly", "") or None,
    },
    "pro": {
        "name": "Pro",
        "max_events": 20,
        "max_photos_per_event": 2000,
        "retention_days": 365,
        "monthly_cents": 2900,   # $29
        "yearly_cents": 29000,   # $290 (2 months free)
        "currency": "usd",
        "stripe_price_monthly": getattr(settings, "stripe_price_pro_monthly", "") or None,
        "stripe_price_yearly": getattr(settings, "stripe_price_pro_yearly", "") or None,
    },
}

# Tiers a user can self-purchase (excludes free + custom)
PURCHASABLE_TIERS = ["starter", "pro"]
TIER_ORDER = ["free", "starter", "pro"]


def get_tier_config(tier_name: str) -> Dict[str, Any]:
    if tier_name not in TIER_CONFIG:
        raise ValueError(f"Unknown tier: {tier_name}")
    return TIER_CONFIG[tier_name]


def get_stripe_price_id(tier_name: str, interval: str) -> Optional[str]:
    """Return the Stripe Price ID for a tier+interval combo."""
    if tier_name not in TIER_CONFIG:
        raise ValueError(f"Unknown tier: {tier_name}")
    if interval not in ("month", "year"):
        raise ValueError(f"Invalid interval: {interval}")
    cfg = TIER_CONFIG[tier_name]
    if interval == "month":
        return cfg["stripe_price_monthly"]
    return cfg["stripe_price_yearly"]


def get_effective_limits(user_tier) -> dict:
    """Return live limits for a UserTier row.

    Custom tier honors per-row overrides. Named tiers always read from TIER_CONFIG
    so config changes take effect immediately. None falls back to free.
    """
    if user_tier is None:
        cfg = TIER_CONFIG["free"]
        return {
            "tier_name": "free",
            "max_events": cfg["max_events"],
            "max_photos_per_event": cfg["max_photos_per_event"],
            "retention_days": cfg["retention_days"],
            "price_cents": 0,
        }
    if user_tier.tier_name == "custom":
        return {
            "tier_name": "custom",
            "max_events": user_tier.max_events,
            "max_photos_per_event": user_tier.max_photos_per_event,
            "retention_days": user_tier.retention_days or 365,
            "price_cents": user_tier.price_cents,
        }
    cfg = TIER_CONFIG.get(user_tier.tier_name, TIER_CONFIG["free"])
    return {
        "tier_name": user_tier.tier_name,
        "max_events": cfg["max_events"],
        "max_photos_per_event": cfg["max_photos_per_event"],
        "retention_days": cfg["retention_days"],
        "price_cents": cfg["monthly_cents"],
    }


def get_active_event_count(db, user_id) -> int:
    """Count events that occupy a user's active-event slots.

    Frozen and expired events do NOT count - they're read-only / pending purge,
    so downgrading freezes excess events instead of blocking the downgrade.
    """
    from app.models import Event
    from sqlalchemy import func
    return db.query(func.count(Event.id)).filter(
        Event.owner_user_id == user_id,
        Event.status == 'active',
    ).scalar() or 0


def is_subscription_active(user_tier) -> bool:
    """True when the subscription entitles the user to paid-tier limits.

    Trialing or active = entitled. Past-due tolerated only inside grace period
    (handled by retention/downgrade scheduler). Canceled/unpaid = not entitled.
    """
    if user_tier is None:
        return False
    if user_tier.tier_name in ("free", "custom"):
        return user_tier.is_active
    return user_tier.subscription_status in ("active", "trialing")
