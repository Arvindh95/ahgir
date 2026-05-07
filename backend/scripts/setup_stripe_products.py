"""Bootstrap Stripe Products + Prices for PicUr subscription tiers.

Creates Products and Prices for Starter and Pro tiers (monthly + yearly),
idempotent: re-running matches by Product name and reuses existing Prices
when the unit_amount + interval already exist.

Run once per Stripe environment (test mode + live mode separately):

    docker exec -e STRIPE_SECRET_KEY=sk_test_... picur-backend python scripts/setup_stripe_products.py

Outputs the Price IDs to stdout. Copy them into .env.production:

    STRIPE_PRICE_STARTER_MONTHLY=price_...
    STRIPE_PRICE_STARTER_YEARLY=price_...
    STRIPE_PRICE_PRO_MONTHLY=price_...
    STRIPE_PRICE_PRO_YEARLY=price_...
"""

import os
import sys
import stripe

# Tier definitions inline so this script can run without importing the rest of the app.
TIER_PRICES = {
    "starter": {
        "name": "PicUr Starter",
        "description": "5 active events, 500 photos per event, 6-month retention.",
        "monthly_cents": 3900,
        "yearly_cents": 39000,
        "currency": "myr",
    },
    "pro": {
        "name": "PicUr Pro",
        "description": "20 active events, 2000 photos per event, 1-year retention.",
        "monthly_cents": 9900,
        "yearly_cents": 99000,
        "currency": "myr",
    },
}


def find_or_create_product(name: str, description: str) -> stripe.Product:
    """Look up product by name (paged), create if absent."""
    starting_after = None
    while True:
        kwargs = {"limit": 100, "active": True}
        if starting_after:
            kwargs["starting_after"] = starting_after
        page = stripe.Product.list(**kwargs)
        for p in page.data:
            if p.name == name:
                return p
        if not page.has_more:
            break
        starting_after = page.data[-1].id

    return stripe.Product.create(name=name, description=description)


def find_or_create_price(product_id: str, unit_amount: int, currency: str, interval: str) -> stripe.Price:
    """Find an active recurring Price matching unit_amount + interval, else create."""
    starting_after = None
    while True:
        kwargs = {"product": product_id, "limit": 100, "active": True}
        if starting_after:
            kwargs["starting_after"] = starting_after
        page = stripe.Price.list(**kwargs)
        for pr in page.data:
            recurring = getattr(pr, "recurring", None)
            r_interval = getattr(recurring, "interval", None) if recurring else None
            if (
                pr.unit_amount == unit_amount
                and pr.currency == currency.lower()
                and r_interval == interval
            ):
                return pr
        if not page.has_more:
            break
        starting_after = page.data[-1].id

    return stripe.Price.create(
        product=product_id,
        unit_amount=unit_amount,
        currency=currency,
        recurring={"interval": interval},
    )


def main() -> int:
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        print("ERROR: STRIPE_SECRET_KEY not set in env", file=sys.stderr)
        return 1
    stripe.api_key = api_key

    env_lines: list[str] = []
    for tier_key, cfg in TIER_PRICES.items():
        product = find_or_create_product(cfg["name"], cfg["description"])
        print(f"[{tier_key}] product: {product.id}  ({product.name})")

        monthly = find_or_create_price(product.id, cfg["monthly_cents"], cfg["currency"], "month")
        yearly = find_or_create_price(product.id, cfg["yearly_cents"], cfg["currency"], "year")
        print(f"  monthly price: {monthly.id}  ({cfg['monthly_cents']} {cfg['currency'].upper()}/mo)")
        print(f"  yearly  price: {yearly.id}  ({cfg['yearly_cents']} {cfg['currency'].upper()}/yr)")

        env_lines.append(f"STRIPE_PRICE_{tier_key.upper()}_MONTHLY={monthly.id}")
        env_lines.append(f"STRIPE_PRICE_{tier_key.upper()}_YEARLY={yearly.id}")

    print()
    print("=" * 60)
    print("Add to .env.production:")
    print("=" * 60)
    for line in env_lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
