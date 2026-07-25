"""Auth Service settings — inherits shared base and adds auth-specific fields."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class AuthServiceSettings(BaseServiceSettings):
    service_name: str = "auth_service"

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Phone OTP
    phone_otp_ttl_seconds: int = 600       # 10 minutes
    phone_otp_max_attempts: int = 3

    # CORS — expand per deployment
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Password hashing — bcrypt rounds
    bcrypt_rounds: int = 12


@lru_cache
def get_settings() -> AuthServiceSettings:
    return AuthServiceSettings()
