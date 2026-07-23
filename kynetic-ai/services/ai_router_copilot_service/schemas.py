"""
AI Router & Copilot Service — Pydantic Schemas.

Request/response models for:
  - POST /router/recommend
  - POST /copilot/chat  (WebSocket + REST fallback)
  - GET  /copilot/sessions/{id}/history
"""

import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Router Schemas
# ─────────────────────────────────────────────────────────────────────────────

class BudgetFilter(BaseModel):
    """Developer specifies a hard budget ceiling."""
    amount: Decimal = Field(..., gt=0, description="Maximum budget amount")
    currency: Literal["usd", "inr"] = "usd"


class RecommendRequest(BaseModel):
    """
    POST /router/recommend body.

    Exactly one of `budget` or `goal` must be provided.
    Optionally scoped to a template (restricts to listings that satisfy
    the template's hardware requirements).
    """
    budget: BudgetFilter | None = None
    goal: Literal["fastest", "cheapest", "balanced"] | None = None
    template_id: uuid.UUID | None = None

    # Optional filter hints (not required but improve recommendation quality)
    min_gpu_vram_gb: float | None = None
    region: str | None = None

    @field_validator("goal")
    @classmethod
    def validate_budget_or_goal(cls, v, info):
        if v is None and info.data.get("budget") is None:
            raise ValueError("Provide either 'budget' or 'goal'.")
        return v


class ScoredListing(BaseModel):
    """A single listing in the ranked recommendation result."""
    listing_id: uuid.UUID
    host_id: uuid.UUID
    title: str | None
    gpu_model: str | None
    gpu_count: int | None
    gpu_vram_gb: float | None
    cpu_cores: int | None
    ram_gb: float | None
    region: str | None
    price_per_hour_usd: Decimal
    price_per_hour_inr: Decimal

    # Estimated cost and time for a reference workload
    estimated_cost_usd: Decimal | None
    estimated_cost_inr: Decimal | None
    estimated_hours: float | None

    # Router scores (0.0–1.0 each; composite is the weighted sum)
    score_price: float
    score_benchmark: float
    score_availability: float
    score_composite: float

    # Raw benchmark score from host_benchmarks (for transparency)
    benchmark_score: float | None
    benchmark_type: str | None

    # Reputation stub — neutral 0.5 until Phase 8 wires real scores
    reputation_score: float = 0.5


class RecommendResponse(BaseModel):
    """Response from POST /router/recommend."""
    recommendation_id: uuid.UUID
    request: dict[str, Any]
    results: list[ScoredListing]
    total_candidates_evaluated: int


# ─────────────────────────────────────────────────────────────────────────────
# Copilot Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CopilotChatRequest(BaseModel):
    """
    POST /copilot/chat body.

    `session_id` is optional on the first call — the service creates a new
    session and returns the ID in the response.
    """
    session_id: uuid.UUID | None = None
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language message from the developer.",
    )

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """
        Basic input sanitization gate before the text reaches the LLM.

        Strips leading/trailing whitespace and collapses excessive repeated
        whitespace (guards against prompt-injection via whitespace flooding).
        Full prompt-injection defence is handled in the system prompt.
        """
        import re
        v = v.strip()
        v = re.sub(r"\s{10,}", " ", v)   # collapse runs of ≥10 spaces
        return v


class CopilotChatResponse(BaseModel):
    """Response from POST /copilot/chat."""
    session_id: uuid.UUID
    message_id: uuid.UUID
    role: Literal["assistant"] = "assistant"
    content: str
    # If the copilot called the Router, embed the grounded recommendation
    recommendation: RecommendResponse | None = None


class CopilotMessageOut(BaseModel):
    """A single message in session history."""
    id: uuid.UUID
    role: str
    content: str
    router_recommendation_id: uuid.UUID | None
    created_at: str  # ISO-8601


class CopilotSessionHistory(BaseModel):
    """Response from GET /copilot/sessions/{id}/history."""
    session_id: uuid.UUID
    developer_id: uuid.UUID | None
    created_at: str
    messages: list[CopilotMessageOut]


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket message envelope (used over the WS connection)
# ─────────────────────────────────────────────────────────────────────────────

class WSInbound(BaseModel):
    """Message sent by the frontend over the WebSocket."""
    type: Literal["chat"] = "chat"
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=2000)


class WSOutbound(BaseModel):
    """Message sent by the service to the frontend."""
    type: Literal["chat_response", "error", "ping"] = "chat_response"
    session_id: str | None = None
    message_id: str | None = None
    content: str = ""
    recommendation: dict[str, Any] | None = None
    error: str | None = None
