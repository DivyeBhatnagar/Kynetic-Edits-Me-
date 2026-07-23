"""Wallet & Billing Service settings."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class WalletBillingSettings(BaseServiceSettings):
    service_name: str = "wallet_billing_service"

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Stripe
    stripe_secret_key: str = "sk_test_REPLACE_WITH_REAL_KEY"
    stripe_webhook_secret: str = "whsec_REPLACE_WITH_REAL_SECRET"
    stripe_publishable_key: str = "pk_test_REPLACE_WITH_REAL_KEY"

    # FX rate (fixed for Phase 3; live FX in Phase 8)
    usd_to_inr_rate: str = "84.0"   # str so Decimal() conversion is explicit

    # Redis pub/sub channel for user.created events (from auth_service)
    user_created_channel: str = "kynetic:events:user_created"

    # ── Razorpay (Phase 10 — India payments) ──────────────────────────────
    # Set RAZORPAY_MOCK_MODE=false in production to use real Razorpay API
    razorpay_key_id: str = "rzp_test_REPLACE_WITH_REAL_KEY_ID"
    razorpay_key_secret: str = "REPLACE_WITH_REAL_KEY_SECRET"
    razorpay_webhook_secret: str = "REPLACE_WITH_REAL_WEBHOOK_SECRET"
    razorpay_mock_mode: bool = True   # True = zero real API calls (dev/CI safe)

    # Notifications service URL (internal, for cross-service event dispatch)
    notifications_service_url: str = "http://notifications_service:8010"


@lru_cache
def get_settings() -> WalletBillingSettings:
    return WalletBillingSettings()
