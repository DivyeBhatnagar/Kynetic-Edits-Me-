"""
Integration tests for POST /router/recommend.

Uses SQLite in-memory DB (same pattern as other service tests).
The ranking function is unit-tested separately; here we test the
full request → DB → ranking → response cycle.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from services.ai_router_copilot_service.main import app
from services.ai_router_copilot_service.schemas import RecommendResponse


# ── Sample listings returned by mock fetch_active_listings ─────────────────────

def _sample_listings():
    return [
        {
            "id": uuid.uuid4(),
            "host_id": uuid.uuid4(),
            "title": "4090 Budget Beast",
            "gpu_model": "NVIDIA RTX 4090",
            "gpu_count": 1,
            "gpu_vram_gb": 24.0,
            "cpu_cores": 16,
            "ram_gb": 64.0,
            "region": "us-east-1",
            "price_per_hour_usd": 1.20,
            "price_per_hour_inr": 99.0,
            "benchmark_score": 80.0,
            "benchmark_type": "llm_inference",
            "is_available": True,
        },
        {
            "id": uuid.uuid4(),
            "host_id": uuid.uuid4(),
            "title": "A100 Fast Train",
            "gpu_model": "NVIDIA A100",
            "gpu_count": 1,
            "gpu_vram_gb": 80.0,
            "cpu_cores": 32,
            "ram_gb": 128.0,
            "region": "eu-west-1",
            "price_per_hour_usd": 3.50,
            "price_per_hour_inr": 290.0,
            "benchmark_score": 200.0,
            "benchmark_type": "llm_inference",
            "is_available": True,
        },
        {
            "id": uuid.uuid4(),
            "host_id": uuid.uuid4(),
            "title": "3060 Entry GPU",
            "gpu_model": "NVIDIA RTX 3060",
            "gpu_count": 1,
            "gpu_vram_gb": 12.0,
            "cpu_cores": 8,
            "ram_gb": 32.0,
            "region": "ap-south-1",
            "price_per_hour_usd": 0.40,
            "price_per_hour_inr": 33.0,
            "benchmark_score": 30.0,
            "benchmark_type": "llm_inference",
            "is_available": True,
        },
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_db_session(listings):
    """Return a mock get_async_session that provides a mock DB session."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock the repository functions
    return mock_session


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestRouterRecommend:

    @pytest.mark.asyncio
    async def test_goal_based_request_returns_results(self):
        """POST /router/recommend with goal=fastest returns ranked listings."""
        listings = _sample_listings()

        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=listings),
            ),
            patch(
                "services.ai_router_copilot_service.router_routes.save_recommendation",
                new=AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(commit=AsyncMock())),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"goal": "fastest"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) > 0
        assert "recommendation_id" in data

    @pytest.mark.asyncio
    async def test_budget_based_request_filters_correctly(self):
        """POST /router/recommend with budget=0.50 USD excludes expensive listings."""
        listings = _sample_listings()
        # Only the 3060 at $0.40/hr should survive the budget filter

        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=listings),
            ),
            patch(
                "services.ai_router_copilot_service.router_routes.save_recommendation",
                new=AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(commit=AsyncMock())),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"budget": {"amount": "0.50", "currency": "usd"}},
                )

        assert resp.status_code == 200
        results = resp.json()["results"]
        for r in results:
            assert float(r["price_per_hour_usd"]) <= 0.50

    @pytest.mark.asyncio
    async def test_no_matching_budget_returns_404(self):
        """When all listings exceed budget, return 404."""
        listings = _sample_listings()

        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=listings),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock()),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"budget": {"amount": "0.01", "currency": "usd"}},
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_marketplace_returns_404(self):
        """When no active listings exist, return 404."""
        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock()),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"goal": "cheapest"},
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_budget_and_goal_returns_422(self):
        """Request without budget or goal is rejected by Pydantic."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/router/recommend",
                json={"min_gpu_vram_gb": 24},  # no budget, no goal
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_results_include_cost_and_time_estimates(self):
        """Each result must include estimated_cost_usd and estimated_hours."""
        listings = _sample_listings()

        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=listings),
            ),
            patch(
                "services.ai_router_copilot_service.router_routes.save_recommendation",
                new=AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(commit=AsyncMock())),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"goal": "balanced"},
                )

        assert resp.status_code == 200
        for result in resp.json()["results"]:
            assert result["estimated_cost_usd"] is not None
            assert result["estimated_hours"] is not None
            assert result["score_composite"] is not None

    @pytest.mark.asyncio
    async def test_reputation_score_is_neutral_stub(self):
        """Reputation score should be 0.5 until Phase 8 wires real scores."""
        listings = _sample_listings()

        with (
            patch(
                "services.ai_router_copilot_service.router_routes.fetch_active_listings",
                new=AsyncMock(return_value=listings),
            ),
            patch(
                "services.ai_router_copilot_service.router_routes.save_recommendation",
                new=AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
            ),
            patch(
                "libs.db_models.database.get_async_session",
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(commit=AsyncMock())),
                                       __aexit__=AsyncMock(return_value=None)),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/router/recommend",
                    json={"goal": "fastest"},
                )

        for result in resp.json()["results"]:
            assert result["reputation_score"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "ai_router_copilot_service"
