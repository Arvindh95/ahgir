"""Regression tests for billing/auth/guest security fixes."""

from datetime import datetime, timedelta
import asyncio
import uuid

import pytest
from fastapi import HTTPException

from app.models import Payment, User, UserTier
from app.routers import auth, guest, payments


def _user(db_session):
    user = User(
        email=f"user_{uuid.uuid4().hex}@example.com",
        password_hash="hash",
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_mismatched_open_checkout_is_expired(db_session, monkeypatch):
    user = _user(db_session)
    payment = Payment(
        user_id=user.id,
        tier_name="starter",
        billing_interval="month",
        stripe_checkout_session_id="cs_old",
        amount_cents=900,
        currency="usd",
        status="pending",
        created_at=datetime.utcnow(),
    )
    db_session.add(payment)
    db_session.flush()

    monkeypatch.setattr(
        payments.stripe.checkout.Session,
        "retrieve",
        staticmethod(lambda session_id: {"status": "open", "url": "https://checkout/old"}),
    )
    expired = []
    monkeypatch.setattr(
        payments.stripe.checkout.Session,
        "expire",
        staticmethod(lambda session_id: expired.append(session_id)),
    )

    reusable = payments._get_reusable_checkout_session(user, db_session, "pro", "year")

    assert reusable is None
    assert expired == ["cs_old"]
    assert payment.status == "failed"


def test_completed_checkout_blocks_until_subscription_syncs(db_session, monkeypatch):
    user = _user(db_session)
    payment = Payment(
        user_id=user.id,
        tier_name="starter",
        billing_interval="month",
        stripe_checkout_session_id="cs_done",
        amount_cents=900,
        currency="usd",
        status="completed",
        created_at=datetime.utcnow(),
    )
    db_session.add(payment)
    db_session.flush()

    monkeypatch.setattr(
        payments.stripe.checkout.Session,
        "retrieve",
        staticmethod(lambda session_id: {"status": "complete"}),
    )

    with pytest.raises(HTTPException) as exc:
        payments._get_reusable_checkout_session(user, db_session, "starter", "month")

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CHECKOUT_PROCESSING"


def test_invoice_paid_recovers_past_due_subscription(db_session, monkeypatch):
    user = _user(db_session)
    user_tier = UserTier(
        user_id=user.id,
        tier_name="starter",
        max_events=5,
        max_photos_per_event=500,
        price_cents=900,
        is_active=True,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        subscription_status="past_due",
        billing_interval="month",
        current_period_end=datetime.utcnow() - timedelta(days=4),
        activated_at=datetime.utcnow(),
    )
    db_session.add(user_tier)
    db_session.flush()

    monkeypatch.setitem(payments.TIER_CONFIG["pro"], "stripe_price_monthly", "price_pro_monthly")
    monkeypatch.setattr(
        payments.stripe.Subscription,
        "retrieve",
        staticmethod(lambda sub_id: {
            "id": sub_id,
            "customer": "cus_123",
            "status": "active",
            "cancel_at_period_end": False,
            "items": {
                "data": [{
                    "current_period_end": int((datetime.utcnow() + timedelta(days=30)).timestamp()),
                    "price": {"id": "price_pro_monthly"},
                }]
            },
        }),
    )

    payments._handle_invoice_paid(
        {"id": "in_123", "subscription": "sub_123", "customer": "cus_123", "amount_paid": 2900, "currency": "usd"},
        db_session,
        event_created=1_700_000_000,
        event_id="evt_paid",
        event_type="invoice.paid",
    )

    assert user_tier.subscription_status == "active"
    assert user_tier.tier_name == "pro"
    assert user_tier.billing_interval == "month"


def test_manual_override_ignores_subscription_upsert(db_session, monkeypatch):
    user = _user(db_session)
    user_tier = UserTier(
        user_id=user.id,
        tier_name="custom",
        max_events=2,
        max_photos_per_event=25,
        price_cents=0,
        is_active=True,
        stripe_customer_id="cus_123",
        stripe_subscription_id=None,
        subscription_status=None,
        last_subscription_event_type="manual_override",
        activated_at=datetime.utcnow(),
    )
    db_session.add(user_tier)
    db_session.flush()

    monkeypatch.setitem(payments.TIER_CONFIG["pro"], "stripe_price_monthly", "price_pro_monthly")

    payments._handle_subscription_upsert(
        {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        },
        db_session,
        event_created=1_700_000_001,
        event_id="evt_sub",
        event_type="customer.subscription.updated",
    )

    assert user_tier.tier_name == "custom"
    assert user_tier.max_events == 2
    assert user_tier.stripe_subscription_id is None


def test_disabled_downloads_do_not_sign_original_guest_urls(monkeypatch):
    calls = []

    def fake_generate_url(event_id, image_id, photo_type, expires_minutes=15):
        calls.append(photo_type)
        return f"https://signed/{photo_type}/{image_id}"

    monkeypatch.setattr(guest.storage_service, "generate_url", fake_generate_url)

    thumb, original, download = guest._guest_photo_urls(uuid.uuid4(), uuid.uuid4(), allow_downloads=False)

    assert calls == ["thumb"]
    assert original == thumb
    assert download is None


def test_forgot_password_rate_limits_by_ip_and_email(db_session, monkeypatch):
    user = _user(db_session)
    user.email = "victim@example.com"
    db_session.flush()

    calls = []
    monkeypatch.setattr(
        auth.auth_rate_limiter,
        "enforce_rate_limit",
        lambda key, action: calls.append((key, action)),
    )
    monkeypatch.setattr(auth, "enqueue_password_reset_email", lambda *_args, **_kwargs: "job-id")

    class Request:
        class Client:
            host = "203.0.113.10"
        client = Client()

    asyncio.run(
        auth.forgot_password(
            auth.ForgotPasswordRequest(email="Victim@Example.com"),
            Request(),
            db_session,
        )
    )

    assert ("203.0.113.10", "forgot_password_ip") in calls
    assert ("victim@example.com", "forgot_password_email") in calls
