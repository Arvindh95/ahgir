"""Regression tests for billing/auth/guest security fixes."""

from datetime import datetime, timedelta
import asyncio
import uuid

import pytest
from fastapi import HTTPException

from app import config
from app.models import Event, Face, Image, Payment, User, UserTier
from app.routers import auth, events, guest, payments
from app.utils import compreface as compreface_utils


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


def test_same_second_terminal_then_active_update_does_not_reactivate(db_session, monkeypatch):
    """Two same-second subscription.updated events — first terminal, second
    active — must not re-grant the paid tier. The terminal one wins.

    Stripe webhook delivery is unordered and `created` has second-granularity,
    so this race is real: a cancel→active flip and an active→cancel flip can
    arrive in either order with identical timestamps. Pre-fix, the staleness
    guard only protected against same-second .updated arriving after
    .deleted, not after another .updated→canceled.
    """
    user = _user(db_session)
    user_tier = UserTier(
        user_id=user.id,
        tier_name="pro",
        max_events=20,
        max_photos_per_event=500,
        price_cents=2900,
        is_active=True,
        stripe_customer_id="cus_456",
        stripe_subscription_id="sub_456",
        subscription_status="active",
        activated_at=datetime.utcnow(),
    )
    db_session.add(user_tier)
    db_session.flush()

    monkeypatch.setitem(payments.TIER_CONFIG["pro"], "stripe_price_monthly", "price_pro_monthly")

    shared_created = 1_700_000_500
    # 1) .updated → canceled lands first; user should drop to free.
    payments._handle_subscription_upsert(
        {
            "id": "sub_456",
            "customer": "cus_456",
            "status": "canceled",
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        },
        db_session,
        event_created=shared_created,
        event_id="evt_cancel",
        event_type="customer.subscription.updated",
    )
    assert user_tier.tier_name == "free", "first .updated→canceled should downgrade"
    assert user_tier.subscription_status is None
    assert user_tier.last_subscription_event_type == "customer.subscription.updated.terminal"

    # 2) .updated → active arrives in the SAME SECOND. Must be ignored as stale.
    payments._handle_subscription_upsert(
        {
            "id": "sub_456",
            "customer": "cus_456",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        },
        db_session,
        event_created=shared_created,
        event_id="evt_active",
        event_type="customer.subscription.updated",
    )
    assert user_tier.tier_name == "free", "delayed .updated→active must not re-grant pro"
    assert user_tier.subscription_status is None
    assert user_tier.stripe_subscription_id is None


def test_paused_subscription_past_grace_is_downgraded(db_session, monkeypatch):
    """A subscription in `paused` status past the grace period must be
    downgraded to free by the daily scheduler. Mirrors the past_due path.
    Pre-fix the scheduler only looked at past_due, so paused users kept paid
    limits indefinitely.
    """
    from app.workers.retention_policy import process_overdue_subscriptions

    user = _user(db_session)
    user_tier = UserTier(
        user_id=user.id,
        tier_name="pro",
        max_events=20,
        max_photos_per_event=500,
        price_cents=2900,
        is_active=True,
        stripe_customer_id="cus_paused",
        stripe_subscription_id="sub_paused",
        subscription_status="paused",
        # current_period_end well past the grace cutoff so the row matches.
        current_period_end=datetime.utcnow() - timedelta(days=60),
        activated_at=datetime.utcnow() - timedelta(days=60),
    )
    db_session.add(user_tier)
    db_session.flush()

    process_overdue_subscriptions(db=db_session)
    db_session.flush()
    db_session.refresh(user_tier)

    assert user_tier.tier_name == "free", "paused beyond grace should be downgraded"
    assert user_tier.subscription_status is None
    assert user_tier.stripe_subscription_id is None
    assert user_tier.last_subscription_event_type == "grace_period_downgrade"


def test_paused_subscription_within_grace_is_kept(db_session):
    """A `paused` subscription whose period end is still within the grace
    window must keep its paid tier — the scheduler waits."""
    from app.workers.retention_policy import process_overdue_subscriptions

    user = _user(db_session)
    user_tier = UserTier(
        user_id=user.id,
        tier_name="pro",
        max_events=20,
        max_photos_per_event=500,
        price_cents=2900,
        is_active=True,
        stripe_customer_id="cus_fresh_pause",
        stripe_subscription_id="sub_fresh_pause",
        subscription_status="paused",
        # Period ended yesterday — within any sane grace window.
        current_period_end=datetime.utcnow() - timedelta(days=1),
        activated_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(user_tier)
    db_session.flush()

    process_overdue_subscriptions(db=db_session)
    db_session.flush()
    db_session.refresh(user_tier)

    assert user_tier.tier_name == "pro", "paused within grace should not be downgraded"
    assert user_tier.subscription_status == "paused"


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


def test_event_owner_mutations_require_active_event(db_session):
    user = _user(db_session)
    frozen_event = Event(
        owner_user_id=user.id,
        slug=f"frozen-{uuid.uuid4().hex}",
        name="Frozen Event",
        status="frozen",
    )
    db_session.add(frozen_event)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        events.ensure_event_mutable(frozen_event, user)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "EVENT_NOT_ACTIVE"


def test_compreface_event_cleanup_deletes_unique_subjects(db_session, monkeypatch):
    user = _user(db_session)
    event = Event(
        owner_user_id=user.id,
        slug=f"cleanup-{uuid.uuid4().hex}",
        name="Cleanup Event",
    )
    image = Image(
        event=event,
        filename="photo.jpg",
        file_hash="h",
        size_bytes=1,
        status="indexed",
    )
    db_session.add_all([
        event,
        image,
        Face(
            image=image,
            event=event,
            embedding=[0.0] * 512,
            bbox=[0, 0, 10, 10],
            quality_score=0.9,
            compreface_subject_id="subject-1",
        ),
        Face(
            image=image,
            event=event,
            embedding=[0.0] * 512,
            bbox=[0, 0, 10, 10],
            quality_score=0.9,
            compreface_subject_id="subject-1",
        ),
    ])
    db_session.flush()

    calls = []

    class Response:
        status_code = 200
        text = "ok"

    monkeypatch.setattr(compreface_utils.settings, "compreface_api_key", "key")
    monkeypatch.setattr(compreface_utils, "get_compreface_url", lambda: "http://compreface")
    monkeypatch.setattr(
        compreface_utils.httpx,
        "delete",
        lambda url, params, headers, timeout: calls.append(params["subject"]) or Response(),
    )

    deleted, failed = compreface_utils.delete_compreface_subjects_for_event(db_session, event.id)

    assert deleted == 1
    assert failed == 0
    assert calls == ["subject-1"]


def test_production_validation_rejects_placeholder_values(monkeypatch):
    valid_values = {
        "environment": "production",
        "jwt_secret_key": "x" * 32,
        "stripe_secret_key": "sk_live_real",
        "stripe_webhook_secret": "whsec_real",
        "smtp_username": "mailer",
        "smtp_password": "smtp-secret",
        "compreface_api_key": "recognition-key",
        "compreface_detection_api_key": "detection-key",
        "minio_secret_key": "minio-secret",
        "cors_origins": "https://picur.my",
        "frontend_url": "https://picur.my",
    }
    for key, value in valid_values.items():
        monkeypatch.setattr(config.settings, key, value)

    monkeypatch.setattr(config.settings, "stripe_secret_key", "CHANGE_ME_STRIPE")

    with pytest.raises(RuntimeError) as exc:
        config.validate_production_secrets()

    assert "STRIPE_SECRET_KEY" in str(exc.value)
