"""
AI Router & Copilot Service — Native Copilot Agent.
# ponytail: native httpx LLM client, removed heavy langchain framework (saved ~180 lines)
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
import structlog

from services.ai_router_copilot_service.config import RouterCopilotSettings
from services.ai_router_copilot_service.ranking import rank_listings
from services.ai_router_copilot_service.schemas import RecommendResponse, ScoredListing

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are Kynetic's AI Copilot — a helpful assistant that helps developers find the best GPU compute resources.
Extract intent as JSON: {"goal": "fastest"|"cheapest"|"balanced", "budget_amount": float, "min_gpu_vram_gb": float, "needs_recommendation": bool}
Narrate router results accurately without hallucinating numbers.
"""

NARRATION_PROMPT_TEMPLATE = """[ROUTER_RESULTS]
{router_results_json}

Narrate top recommendations to the developer verbatim.
"""


async def _call_llm(messages: list[dict[str, str]], settings: RouterCopilotSettings) -> str:
    """Native LLM invocation via httpx — supports OpenAI / vLLM / Anthropic endpoints."""
    if settings.llm_backend == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"}
        payload = {"model": settings.anthropic_model, "messages": messages, "max_tokens": 500}
    else:
        url = f"{settings.vllm_base_url}/chat/completions" if settings.llm_backend == "vllm" else "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        payload = {"model": settings.openai_model if settings.llm_backend != "vllm" else settings.vllm_model, "messages": messages, "max_tokens": 500}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                data = res.json()
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
                elif "content" in data and isinstance(data["content"], list):
                    return data["content"][0].get("text", "")
    except Exception as exc:
        log.error("copilot_llm_failed", error=str(exc))
    return "I am available to help you find the best compute resources for your AI workloads."


async def run_copilot_turn(
    *,
    user_message: str,
    history: list[dict[str, str]],
    settings: RouterCopilotSettings,
    listings_fetcher=None,
    recommendation_persister=None,
) -> tuple[str, RecommendResponse | None]:
    """Execute one copilot turn natively."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history[-settings.max_history_messages:]:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    intent_text = await _call_llm(messages, settings)
    intent: dict[str, Any] = {}
    json_match = re.search(r"\{.*\}", intent_text, re.DOTALL)
    if json_match:
        try:
            intent = json.loads(json_match.group())
        except json.JSONDecodeError:
            intent = {"needs_recommendation": False}

    recommendation: RecommendResponse | None = None
    if intent.get("needs_recommendation", False) and listings_fetcher is not None:
        listings = await listings_fetcher(min_gpu_vram_gb=intent.get("min_gpu_vram_gb"), region=intent.get("region"))
        ranked: list[ScoredListing] = rank_listings(listings, goal=intent.get("goal"))

        if recommendation_persister is not None and ranked:
            rec_row = await recommendation_persister(
                request_payload=intent,
                recommended_listing_ids=[str(r.listing_id) for r in ranked],
                ranked_results=[r.model_dump(mode="json") for r in ranked],
            )
            recommendation = RecommendResponse(
                recommendation_id=rec_row.id,
                request={},
                results=ranked,
                total_candidates_evaluated=len(listings),
            )

        if ranked:
            results_json = json.dumps([r.model_dump(mode="json") for r in ranked[:3]], default=str)
            narrate_msgs = messages + [{"role": "user", "content": NARRATION_PROMPT_TEMPLATE.format(router_results_json=results_json)}]
            reply = await _call_llm(narrate_msgs, settings)
        else:
            reply = "No matching machines were found. Try relaxing your filters."
    else:
        reply = intent_text

    return reply, recommendation
