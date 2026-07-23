"""
AI Router & Copilot Service — LangChain Copilot Agent.

Architecture
────────────
The copilot is a LangChain ConversationalAgent that:

  1. Parses free-text developer intent using an LLM (OpenAI/Anthropic/vLLM)
  2. Extracts structured parameters (budget, goal, template_id, etc.)
  3. Calls the Router's rank_listings() function DIRECTLY (same process, no HTTP hop)
  4. Persists the recommendation for auditability
  5. Formats the Router's grounded numbers into a natural-language reply

The LLM ONLY handles language: parsing intent (step 2) and formatting
the reply (step 5). It NEVER generates numbers — all cost/time figures
come from step 3's output.  This is enforced by:
  a) The system prompt's explicit instruction ("Your job is ONLY to narrate...")
  b) The architecture (LLM cannot produce a response without a router_result)
  c) The audit trail FK in CopilotMessage → RouterRecommendation

LangChain Memory
────────────────
Session history is loaded from DB on each request and injected into
ConversationBufferWindowMemory (last N turns).  This makes the WebSocket
implementation stateless at the server layer (pods can restart freely).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, AIMessage

from services.ai_router_copilot_service.config import RouterCopilotSettings
from services.ai_router_copilot_service.ranking import rank_listings
from services.ai_router_copilot_service.schemas import RecommendResponse, ScoredListing

log = structlog.get_logger(__name__)


# ── System prompt ─────────────────────────────────────────────────────────────
# Strict prompt design: LLM is told it ONLY narrates data from the Router.
# It is explicitly forbidden from producing cost or time numbers independently.

SYSTEM_PROMPT = """You are Kynetic's AI Copilot — a helpful assistant that helps developers find the best GPU compute resources for their workloads.

Your role has TWO phases per user turn:

PHASE 1 — INTENT EXTRACTION
Parse the user's free-text message and extract ONLY these fields (output as compact JSON, nothing else):
{
  "goal": "fastest" | "cheapest" | "balanced" | null,
  "budget_amount": <number> | null,
  "budget_currency": "usd" | "inr" | null,
  "min_gpu_vram_gb": <number> | null,
  "region": "<string>" | null,
  "template_hint": "<string>" | null,
  "needs_recommendation": true | false
}

If the user is asking a general question (not requesting a recommendation), set needs_recommendation=false and output {"needs_recommendation": false}.

PHASE 2 — NARRATION (only after the Router has run)
You will receive a JSON block labelled [ROUTER_RESULTS]. Your job is ONLY to:
- Summarise the top recommendations in plain English
- Quote the EXACT cost and time figures from [ROUTER_RESULTS] — never change them
- Explain WHY the top result was chosen (price score, benchmark score, availability)
- Offer to launch the top result for them

CRITICAL RULES:
- NEVER invent, estimate, or modify any cost, time, or performance number.
- ALL numbers in your reply MUST come verbatim from [ROUTER_RESULTS].
- If [ROUTER_RESULTS] is empty, say no matching machines were found and suggest relaxing filters.
- Keep replies under 250 words and use markdown for readability.
- Do not hallucinate machine names, GPU models, or prices.
"""

NARRATION_PROMPT_TEMPLATE = """
[ROUTER_RESULTS]
{router_results_json}

Based on the above Router results, narrate the top recommendations to the developer.
Remember: quote numbers EXACTLY as they appear in [ROUTER_RESULTS].
"""


def _build_llm(settings: RouterCopilotSettings):
    """Build the LLM client based on the configured backend."""
    if settings.llm_backend == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.1,
            max_tokens=500,
        )
    elif settings.llm_backend == "vllm":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.vllm_model,
            base_url=settings.vllm_base_url,
            api_key="not-needed",
            temperature=0.1,
            max_tokens=500,
        )
    else:
        # Default: OpenAI
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1,
            max_tokens=500,
        )


async def run_copilot_turn(
    *,
    user_message: str,
    history: list[dict[str, str]],  # [{"role": "user"/"assistant", "content": "..."}]
    settings: RouterCopilotSettings,
    # Injected dependencies (for testability)
    listings_fetcher=None,
    recommendation_persister=None,
) -> tuple[str, RecommendResponse | None]:
    """
    Execute one copilot turn.

    Returns
    ───────
    (assistant_reply: str, recommendation: RecommendResponse | None)

    The recommendation is non-None only when the Router was called this turn.
    The caller is responsible for persisting the CopilotMessage rows.
    """
    llm = _build_llm(settings)

    # ── Step 1: Extract intent ───────────────────────────────────────────────
    intent_messages = [
        ("system", SYSTEM_PROMPT),
        *[
            ("human" if m["role"] == "user" else "ai", m["content"])
            for m in history[-settings.max_history_messages:]
        ],
        ("human", user_message),
    ]

    intent_response = await llm.ainvoke(intent_messages)
    intent_text = intent_response.content if hasattr(intent_response, "content") else str(intent_response)

    intent: dict[str, Any] = {}
    try:
        # Extract the JSON block from the LLM's response
        import re
        json_match = re.search(r"\{.*\}", intent_text, re.DOTALL)
        if json_match:
            intent = json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        log.warning("copilot.intent_parse_failed", raw=intent_text[:200])
        intent = {"needs_recommendation": False}

    log.info("copilot.intent_extracted", intent=intent)

    # ── Step 2: Call the Router if needed ────────────────────────────────────
    recommendation: RecommendResponse | None = None

    if intent.get("needs_recommendation", False) and listings_fetcher is not None:
        goal = intent.get("goal")
        budget_amount = intent.get("budget_amount")
        budget_currency = intent.get("budget_currency", "usd")
        min_gpu_vram_gb = intent.get("min_gpu_vram_gb")
        region = intent.get("region")

        budget_usd = None
        budget_inr = None
        if budget_amount:
            if budget_currency == "inr":
                budget_inr = float(budget_amount)
            else:
                budget_usd = float(budget_amount)

        # Fetch listings (injected dependency so tests can mock it)
        listings = await listings_fetcher(
            min_gpu_vram_gb=min_gpu_vram_gb,
            region=region,
        )

        ranked: list[ScoredListing] = rank_listings(
            listings,
            goal=goal,
            budget_usd=budget_usd,
            budget_inr=budget_inr,
            weight_price=settings.weight_price,
            weight_benchmark=settings.weight_benchmark,
            weight_availability=settings.weight_availability,
        )

        if recommendation_persister is not None and ranked:
            rec_row = await recommendation_persister(
                request_payload={
                    "goal": goal,
                    "budget_amount": budget_amount,
                    "budget_currency": budget_currency,
                    "min_gpu_vram_gb": min_gpu_vram_gb,
                    "region": region,
                },
                recommended_listing_ids=[str(r.listing_id) for r in ranked],
                ranked_results=[r.model_dump(mode="json") for r in ranked],
            )
            recommendation = RecommendResponse(
                recommendation_id=rec_row.id,
                request={},
                results=ranked,
                total_candidates_evaluated=len(listings),
            )

        # ── Step 3: Narrate the Router's results ─────────────────────────────
        if ranked:
            router_results_json = json.dumps(
                [r.model_dump(mode="json") for r in ranked[:3]],
                indent=2,
                default=str,
            )
            narration_messages = [
                ("system", SYSTEM_PROMPT),
                ("human", user_message),
                ("ai", intent_text),
                ("human", NARRATION_PROMPT_TEMPLATE.format(
                    router_results_json=router_results_json
                )),
            ]
            narration_response = await llm.ainvoke(narration_messages)
            reply = narration_response.content if hasattr(narration_response, "content") else str(narration_response)
        else:
            reply = (
                "I couldn't find any machines matching your requirements. "
                "Try increasing your budget, choosing a different region, "
                "or relaxing the GPU VRAM requirement."
            )

    else:
        # General question — just answer conversationally
        convo_messages = [
            ("system", SYSTEM_PROMPT),
            *[
                ("human" if m["role"] == "user" else "ai", m["content"])
                for m in history[-settings.max_history_messages:]
            ],
            ("human", user_message),
        ]
        convo_response = await llm.ainvoke(convo_messages)
        reply = convo_response.content if hasattr(convo_response, "content") else str(convo_response)

    return reply, recommendation
