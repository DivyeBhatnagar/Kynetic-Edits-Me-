"""
AI Router & Copilot Service — Configuration.

All values read from environment variables (12-factor).
Sensitive defaults are dev-only placeholders — MUST be overridden in production.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RouterCopilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ─────────────────────────────────────────────────────────
    app_name: str = "ai_router_copilot_service"
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8007

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic"

    # ── Redis ───────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── LLM Backend ─────────────────────────────────────────────────────────
    # Set LLM_BACKEND=openai|anthropic|vllm (default: openai)
    llm_backend: str = "openai"
    openai_api_key: str = "REPLACE_WITH_OPENAI_API_KEY"
    anthropic_api_key: str = "REPLACE_WITH_ANTHROPIC_API_KEY"
    # For self-hosted vLLM
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = "mistralai/Mistral-7B-Instruct-v0.2"

    # Model selection (used when llm_backend=openai)
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-haiku-20240307"

    # ── Rate Limits ─────────────────────────────────────────────────────────
    # Per Phase 5/7 spec: router + copilot endpoints require explicit rate limits
    router_rpm: int = 30      # /router/recommend — more expensive (DB query + scoring)
    copilot_rpm: int = 20     # /copilot/chat — most expensive (LLM call)
    rate_limit_burst: int = 5

    # ── Copilot Session ──────────────────────────────────────────────────────
    # Maximum message history kept in LangChain conversation memory
    max_history_messages: int = 20
    # Maximum free-text input length (chars) — input sanitization gate
    max_input_length: int = 2000

    # ── Router Scoring Weights ───────────────────────────────────────────────
    # Weights for the rule-based ranking function (must sum ≤ 1.0, remainder ignored)
    weight_price: float = 0.40
    weight_benchmark: float = 0.35
    weight_availability: float = 0.25

    # ── Auth (shared JWT secret with auth_service) ───────────────────────────
    jwt_secret_key: str = "dev_secret_change_in_production_12345"
    jwt_algorithm: str = "HS256"

    # ── Internal Service URLs ────────────────────────────────────────────────
    marketplace_service_url: str = "http://marketplace_service:8003"


@lru_cache
def get_settings() -> RouterCopilotSettings:
    return RouterCopilotSettings()
