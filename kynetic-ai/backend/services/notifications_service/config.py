"""Notifications Service — Configuration."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class NotificationsSettings(BaseServiceSettings):
    service_name: str = "notifications_service"
    port: int = 8010

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Email (SendGrid or SMTP)
    # Set EMAIL_MOCK_MODE=false in production
    email_mock_mode: bool = True
    sendgrid_api_key: str = "SG.REPLACE_WITH_REAL_KEY"
    email_from_address: str = "noreply@kynetic.ai"
    email_from_name: str = "Kynetic"

    # Low balance notification threshold (USD)
    default_low_balance_threshold_usd: str = "5.00"


@lru_cache
def get_settings() -> NotificationsSettings:
    return NotificationsSettings()
