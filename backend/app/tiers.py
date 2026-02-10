"""Tier configuration for event billing."""

from typing import Dict, Any, Optional

TIER_CONFIG: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Free",
        "photo_limit": 25,
        "price_cents": 0,
        "currency": "myr",
    },
    "standard": {
        "name": "Standard",
        "photo_limit": 1000,
        "price_cents": 50000,  # RM 500
        "currency": "myr",
    },
    "premium": {
        "name": "Premium",
        "photo_limit": 2000,
        "price_cents": 80000,  # RM 800
        "currency": "myr",
    },
}


def get_tier_config(tier_name: str) -> Dict[str, Any]:
    """Return config for a known tier."""
    if tier_name not in TIER_CONFIG:
        raise ValueError(f"Unknown tier: {tier_name}")
    return TIER_CONFIG[tier_name]


def get_photo_limit(tier_name: str, custom_limit: Optional[int] = None) -> int:
    """Return the photo limit for a tier. For custom tiers, custom_limit is required."""
    if tier_name == "custom":
        if custom_limit is None:
            raise ValueError("custom_limit required for custom tier")
        return custom_limit
    return TIER_CONFIG[tier_name]["photo_limit"]
