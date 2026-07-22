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


@lru_cache
def get_settings() -> WalletBillingSettings:
    return WalletBillingSettings()
