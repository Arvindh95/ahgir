"""Tier configuration for user-level billing."""

from typing import Dict, Any, Optional

TIER_CONFIG: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Free",
        "max_events": 1,
        "max_photos_per_event": 50,
        "price_cents": 0,
        "currency": "myr",
    },
    "premium": {
        "name": "Premium",
        "max_events": 3,
        "max_photos_per_event": 300,
        "price_cents": 5000,  # RM 50
        "currency": "myr",
    },
    "premium_plus": {
        "name": "Premium+",
        "max_events": 10,
        "max_photos_per_event": 500,
        "price_cents": 10000,  # RM 100
        "currency": "myr",
    },
}

# Ordered list for upgrade path
TIER_ORDER = ["free", "premium", "premium_plus"]


def get_tier_config(tier_name: str) -> Dict[str, Any]:
    """Return config for a known tier."""
    if tier_name not in TIER_CONFIG:
        raise ValueError(f"Unknown tier: {tier_name}")
    return TIER_CONFIG[tier_name]


def get_upgrade_price(current_tier: str, target_tier: str) -> int:
    """Return the price in cents for upgrading between tiers."""
    if current_tier not in TIER_ORDER or target_tier not in TIER_ORDER:
        raise ValueError("Invalid tier for upgrade calculation")
    current_idx = TIER_ORDER.index(current_tier)
    target_idx = TIER_ORDER.index(target_tier)
    if target_idx <= current_idx:
        raise ValueError("Target tier must be higher than current tier")
    current_price = TIER_CONFIG[current_tier]["price_cents"]
    target_price = TIER_CONFIG[target_tier]["price_cents"]
    return target_price - current_price
