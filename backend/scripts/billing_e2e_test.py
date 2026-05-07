"""End-to-end subscription test (test mode only).

Creates a throwaway User + Stripe Customer, subscribes to Starter monthly,
verifies the upgrade webhook flipped the tier, cancels, verifies downgrade,
cleans everything up.

Run inside the picur-backend container:
    docker exec picur-backend python scripts/billing_e2e_test.py
"""

import os
import sys
import time
from datetime import datetime

import stripe

from app.database import SessionLocal
from app.models import User, UserTier
from app.tiers import TIER_CONFIG, get_stripe_price_id
from app.auth import hash_password


def main() -> int:
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    if not stripe.api_key.startswith("sk_test_"):
        print("ABORT: STRIPE_SECRET_KEY is not a test-mode key. This test only runs in test mode.")
        return 2

    TEST_EMAIL = "billing-test@picur.my"
    db = SessionLocal()
    print("=== END-TO-END SUBSCRIPTION TEST ===")

    # 1. Throwaway user
    existing = db.query(User).filter(User.email == TEST_EMAIL).first()
    if existing:
        db.delete(existing)
        db.commit()
    user = User(email=TEST_EMAIL, password_hash=hash_password("TestPass123!"), is_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"[1] Created test user: id={user.id}")

    # 2. Free UserTier + Stripe Customer
    cfg = TIER_CONFIG["free"]
    ut = UserTier(
        user_id=user.id, tier_name="free",
        max_events=cfg["max_events"], max_photos_per_event=cfg["max_photos_per_event"],
        retention_days=cfg["retention_days"], price_cents=0,
        is_active=True, activated_at=datetime.utcnow(),
    )
    db.add(ut)
    db.commit()
    customer = stripe.Customer.create(email=TEST_EMAIL, metadata={"user_id": str(user.id)})
    ut.stripe_customer_id = customer.id
    db.commit()
    print(f"[2] Free tier + Stripe customer: {customer.id}")

    # 3. Attach test card
    pm = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"})
    stripe.PaymentMethod.attach(pm.id, customer=customer.id)
    stripe.Customer.modify(customer.id, invoice_settings={"default_payment_method": pm.id})
    print(f"[3] Attached test card pm={pm.id}")

    # 4. Create subscription (Starter monthly)
    price_id = get_stripe_price_id("starter", "month")
    sub = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price": price_id}],
        metadata={"user_id": str(user.id), "tier_name": "starter", "interval": "month"},
    )
    print(f"[4] Subscription created: {sub.id} status={sub.status}")

    # 5. Wait for upgrade webhook
    print("[5] Waiting 8s for upgrade webhook...")
    time.sleep(8)
    db.expire_all()
    ut = db.query(UserTier).filter(UserTier.user_id == user.id).first()
    print(f"    tier_name={ut.tier_name} (expect: starter)")
    print(f"    subscription_status={ut.subscription_status} (expect: active)")
    print(f"    billing_interval={ut.billing_interval} (expect: month)")
    print(f"    max_events={ut.max_events} (expect: 5)")
    print(f"    current_period_end={ut.current_period_end}")
    print(f"    cancel_at_period_end={ut.cancel_at_period_end}")
    upgrade_pass = (ut.tier_name == "starter" and ut.subscription_status == "active" and ut.max_events == 5)
    print(f"    UPGRADE: {'PASS' if upgrade_pass else 'FAIL'}")

    # 6. Soft cancel (cancel at period end)
    stripe.Subscription.modify(sub.id, cancel_at_period_end=True)
    time.sleep(5)
    db.expire_all()
    ut = db.query(UserTier).filter(UserTier.user_id == user.id).first()
    print(f"[6] After cancel_at_period_end=True:")
    print(f"    cancel_at_period_end={ut.cancel_at_period_end} (expect: True)")
    print(f"    tier_name={ut.tier_name} (expect: starter, still active)")
    soft_pass = (ut.cancel_at_period_end is True and ut.tier_name == "starter")
    print(f"    SOFT CANCEL: {'PASS' if soft_pass else 'FAIL'}")

    # 7. Hard cancel (immediate delete)
    stripe.Subscription.delete(sub.id)
    time.sleep(6)
    db.expire_all()
    ut = db.query(UserTier).filter(UserTier.user_id == user.id).first()
    print(f"[7] After Subscription.delete:")
    print(f"    tier_name={ut.tier_name} (expect: free)")
    print(f"    subscription_status={ut.subscription_status} (expect: None)")
    print(f"    max_events={ut.max_events} (expect: 1)")
    downgrade_pass = (ut.tier_name == "free" and ut.subscription_status is None and ut.max_events == 1)
    print(f"    HARD CANCEL: {'PASS' if downgrade_pass else 'FAIL'}")

    # 8. Cleanup
    try:
        stripe.Customer.delete(customer.id)
    except Exception as e:
        print(f"    cleanup warning: {e}")
    user_to_delete = db.query(User).filter(User.id == user.id).first()
    if user_to_delete:
        db.delete(user_to_delete)
        db.commit()
    print("[8] Cleaned up Stripe customer + DB user")

    overall = upgrade_pass and soft_pass and downgrade_pass
    print(f"\n=== RESULT: {'ALL PASS' if overall else 'FAILURES — review above'} ===")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
