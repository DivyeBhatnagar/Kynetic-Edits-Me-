"""
Integration tests — Marketplace Service listings.
Covers all 5 listing endpoints + availability index + security (owner-only).
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.marketplace_service.main import app
from services.marketplace_service.schemas import ListingCreate


# ── Test fixtures ──────────────────────────────────────────────────────────

HOST_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())
LISTING_ID = str(uuid.uuid4())

MOCK_HOST_VERIFIED = {
    "id": HOST_ID,
    "owner_user_id": USER_ID,
    "status": "verified",
    "latest_benchmarks": {"llm_tokens_per_second": 85.3, "image_gen_steps_per_second": 42.1},
    "gpu_model": "NVIDIA RTX 4090",
    "cpu_cores": 32,
    "ram_gb": 64,
}

MOCK_HOST_UNVERIFIED = {
    "id": HOST_ID,
    "owner_user_id": USER_ID,
    "status": "pending_verification",
    "latest_benchmarks": None,
}

VALID_JWT_PAYLOAD = {"sub": USER_ID, "role": "host"}
OTHER_JWT_PAYLOAD = {"sub": OTHER_USER_ID, "role": "developer"}


@pytest.fixture
def client():
    return TestClient(app)


def _listing_body(
    resource_type: str = "gpu",
    price_per_hour_usd: float = 2.50,
) -> dict:
    return {
        "host_id": HOST_ID,
        "resource_type": resource_type,
        "gpu_model": "NVIDIA RTX 4090",
        "gpu_count": 1,
        "gpu_vram_gb": 24,
        "cpu_cores": 32,
        "ram_gb": 64,
        "storage_gb": 512,
        "storage_type": "nvme",
        "price_per_hour_usd": price_per_hour_usd,
        "region": "us-east-1",
        "title": "RTX 4090 Node — 24GB VRAM",
    }


# ── POST /listings ─────────────────────────────────────────────────────────

class TestCreateListing:
    @patch("services.marketplace_service.routes.require_auth", return_value=VALID_JWT_PAYLOAD)
    @patch("services.marketplace_service.routes._assert_host_verified", new_callable=AsyncMock)
    @patch("services.marketplace_service.routes.avail.mark_available", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.create", new_callable=AsyncMock)
    def test_create_listing_verified_host(
        self, mock_create, mock_avail, mock_host_check, mock_auth, client
    ):
        """Verified host owner can create a listing."""
        mock_host_check.return_value = MOCK_HOST_VERIFIED
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.host_id = uuid.UUID(HOST_ID)
        mock_listing.owner_user_id = uuid.UUID(USER_ID)
        mock_listing.resource_type = "gpu"
        mock_listing.gpu_model = "NVIDIA RTX 4090"
        mock_listing.gpu_count = 1
        mock_listing.gpu_vram_gb = Decimal("24")
        mock_listing.cpu_cores = 32
        mock_listing.ram_gb = Decimal("64")
        mock_listing.storage_gb = Decimal("512")
        mock_listing.storage_type = "nvme"
        mock_listing.price_per_hour_usd = Decimal("2.500000")
        mock_listing.price_per_hour_inr = Decimal("210.000000")
        mock_listing.price_per_second_usd = Decimal("0.0006944444")
        mock_listing.price_per_second_inr = Decimal("0.0583333333")
        mock_listing.region = "us-east-1"
        mock_listing.benchmark_scores = None
        mock_listing.status = "active"
        mock_listing.title = "RTX 4090 Node"
        mock_listing.description = None
        mock_listing.created_at = "2024-01-01T00:00:00Z"
        mock_listing.updated_at = "2024-01-01T00:00:00Z"
        mock_create.return_value = mock_listing

        resp = client.post("/listings", json=_listing_body())
        assert resp.status_code == 201
        data = resp.json()
        assert data["host_id"] == HOST_ID
        assert data["resource_type"] == "gpu"
        mock_avail.assert_called_once()

    @patch("services.marketplace_service.routes.require_auth", return_value=VALID_JWT_PAYLOAD)
    @patch("services.marketplace_service.routes._assert_host_verified", new_callable=AsyncMock)
    def test_create_listing_unverified_host_rejected(
        self, mock_host_check, mock_auth, client
    ):
        """Unverified host cannot create a listing — 403."""
        from fastapi import HTTPException
        mock_host_check.side_effect = HTTPException(
            status_code=403,
            detail="Host is not verified (current status: pending_verification).",
        )
        resp = client.post("/listings", json=_listing_body())
        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"]

    def test_create_listing_requires_auth(self, client):
        """Create listing without token → 403."""
        resp = client.post("/listings", json=_listing_body())
        # Without JWT, require_auth dependency should block
        assert resp.status_code in (401, 403)

    @patch("services.marketplace_service.routes.require_auth", return_value=VALID_JWT_PAYLOAD)
    @patch("services.marketplace_service.routes._assert_host_verified", new_callable=AsyncMock)
    def test_create_listing_missing_price(self, mock_host_check, mock_auth, client):
        """Listing without any price → 422 validation error."""
        mock_host_check.return_value = MOCK_HOST_VERIFIED
        body = _listing_body()
        del body["price_per_hour_usd"]  # Remove price
        resp = client.post("/listings", json=body)
        assert resp.status_code == 422


# ── GET /listings (browse) ────────────────────────────────────────────────

class TestBrowseListings:
    @patch("services.marketplace_service.routes.avail.get_available_ids", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.search", new_callable=AsyncMock)
    def test_browse_returns_paginated_results(self, mock_search, mock_avail, client):
        """Browse returns items + pagination meta."""
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.resource_type = "gpu"
        mock_listing.gpu_model = "NVIDIA RTX 4090"
        mock_listing.cpu_cores = 32
        mock_listing.ram_gb = Decimal("64")
        mock_listing.price_per_hour_usd = Decimal("2.5")
        mock_listing.price_per_hour_inr = Decimal("210")
        mock_listing.region = "us-east-1"
        mock_listing.status = "active"
        mock_listing.title = "RTX 4090 Node"

        mock_search.return_value = ([mock_listing], 1)
        mock_avail.return_value = {LISTING_ID}

        resp = client.get("/listings")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["items"][0]["is_available"] is True

    @patch("services.marketplace_service.routes.avail.get_available_ids", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.search", new_callable=AsyncMock)
    def test_browse_filter_by_gpu_model(self, mock_search, mock_avail, client):
        """Filter by gpu_model passes correct params to repository."""
        mock_search.return_value = ([], 0)
        mock_avail.return_value = set()

        resp = client.get("/listings?gpu_model=RTX+4090&resource_type=gpu")
        assert resp.status_code == 200
        # Verify search was called (params inspection)
        mock_search.assert_called_once()
        search_params = mock_search.call_args[0][0]
        assert search_params.gpu_model == "RTX 4090"
        assert str(search_params.resource_type) == "gpu"

    @patch("services.marketplace_service.routes.avail.get_available_ids", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.search", new_callable=AsyncMock)
    def test_browse_filter_by_price_range(self, mock_search, mock_avail, client):
        """Price range filter passes min/max correctly."""
        mock_search.return_value = ([], 0)
        mock_avail.return_value = set()

        resp = client.get("/listings?min_price_usd=1.0&max_price_usd=5.0")
        assert resp.status_code == 200
        params = mock_search.call_args[0][0]
        assert params.min_price_usd == Decimal("1.0")
        assert params.max_price_usd == Decimal("5.0")


# ── GET /listings/{id} ────────────────────────────────────────────────────

class TestGetListing:
    @patch("services.marketplace_service.routes.avail.is_available", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.get_by_id", new_callable=AsyncMock)
    def test_get_listing_found(self, mock_get, mock_avail, client):
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.host_id = uuid.UUID(HOST_ID)
        mock_listing.owner_user_id = uuid.UUID(USER_ID)
        mock_listing.resource_type = "gpu"
        mock_listing.gpu_model = "NVIDIA RTX 4090"
        mock_listing.gpu_count = 1
        mock_listing.gpu_vram_gb = Decimal("24")
        mock_listing.cpu_cores = 32
        mock_listing.ram_gb = Decimal("64")
        mock_listing.storage_gb = Decimal("512")
        mock_listing.storage_type = "nvme"
        mock_listing.price_per_hour_usd = Decimal("2.5")
        mock_listing.price_per_hour_inr = Decimal("210")
        mock_listing.price_per_second_usd = Decimal("0.0006944")
        mock_listing.price_per_second_inr = Decimal("0.0583333")
        mock_listing.region = "us-east-1"
        mock_listing.benchmark_scores = {"llm_tokens_per_second": 85.3}
        mock_listing.status = "active"
        mock_listing.title = "RTX 4090 Node"
        mock_listing.description = None
        mock_listing.created_at = "2024-01-01T00:00:00Z"
        mock_listing.updated_at = "2024-01-01T00:00:00Z"

        mock_get.return_value = mock_listing
        mock_avail.return_value = True

        resp = client.get(f"/listings/{LISTING_ID}")
        assert resp.status_code == 200
        assert resp.json()["is_available"] is True
        assert resp.json()["benchmark_scores"]["llm_tokens_per_second"] == 85.3

    @patch("services.marketplace_service.repository.ListingRepository.get_by_id", new_callable=AsyncMock)
    def test_get_listing_not_found(self, mock_get, client):
        mock_get.return_value = None
        resp = client.get(f"/listings/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── PATCH /listings/{id} ──────────────────────────────────────────────────

class TestUpdateListing:
    @patch("services.marketplace_service.routes.require_auth", return_value=VALID_JWT_PAYLOAD)
    @patch("services.marketplace_service.routes.avail.mark_available", new_callable=AsyncMock)
    @patch("services.marketplace_service.routes.avail.mark_unavailable", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.update", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.get_by_id", new_callable=AsyncMock)
    def test_update_price_owner(
        self, mock_get, mock_update, mock_unavail, mock_avail, mock_auth, client
    ):
        """Owner can update listing price."""
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.owner_user_id = uuid.UUID(USER_ID)
        mock_listing.status = "active"
        mock_get.return_value = mock_listing
        mock_update.return_value = mock_listing

        resp = client.patch(
            f"/listings/{LISTING_ID}", json={"price_per_hour_usd": 3.0}
        )
        assert resp.status_code == 200

    @patch("services.marketplace_service.routes.require_auth", return_value=OTHER_JWT_PAYLOAD)
    @patch("services.marketplace_service.repository.ListingRepository.get_by_id", new_callable=AsyncMock)
    def test_update_non_owner_forbidden(self, mock_get, mock_auth, client):
        """Non-owner cannot update listing → 403."""
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.owner_user_id = uuid.UUID(USER_ID)  # Different from OTHER_USER_ID
        mock_get.return_value = mock_listing

        resp = client.patch(
            f"/listings/{LISTING_ID}", json={"price_per_hour_usd": 3.0}
        )
        assert resp.status_code == 403


# ── DELETE /listings/{id} ─────────────────────────────────────────────────

class TestDeleteListing:
    @patch("services.marketplace_service.routes.require_auth", return_value=VALID_JWT_PAYLOAD)
    @patch("services.marketplace_service.routes.avail.mark_unavailable", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.delist", new_callable=AsyncMock)
    @patch("services.marketplace_service.repository.ListingRepository.get_by_id", new_callable=AsyncMock)
    def test_delist_owner(self, mock_get, mock_delist, mock_unavail, mock_auth, client):
        """Owner can delist their listing."""
        mock_listing = MagicMock()
        mock_listing.id = uuid.UUID(LISTING_ID)
        mock_listing.owner_user_id = uuid.UUID(USER_ID)
        mock_get.return_value = mock_listing

        resp = client.delete(f"/listings/{LISTING_ID}")
        assert resp.status_code == 204
        mock_unavail.assert_called_once()
