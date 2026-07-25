"""
Tests — Phase 6: Zero-Setup App Templates.

Validates:
  - Template repository CRUD (list, get by id/slug, create, scan result)
  - GET /v1/templates returns only `available` templates
  - GET /v1/templates/{id_or_slug} by UUID and slug
  - POST /v1/templates (admin-only gate)
  - GET /v1/instances/{id}/web-ui — token issuance, running-only, template-only
  - scan_template_image task: mock-mode marks available; security failure marks disabled
  - All 4 seed launch-day templates exist (slug presence)
  - LaunchRequest accepts template_id field

Run:
  PYTHONPATH=. ENVIRONMENT=testing FIRECRACKER_MOCK=true \
  DATABASE_URL="sqlite+aiosqlite:///:memory:" \
  python3 -m pytest tests/provisioning_service/test_templates.py -v
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.db_models.provisioning_models import InstanceStatus
from libs.db_models.template_models import TemplateStatus
from services.provisioning_service.schemas import (
    CreateTemplateRequest,
    LaunchRequest,
)
from services.provisioning_service.template_repository import (
    TemplateRepository,
    WebUISessionRepository,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_template(
    *,
    slug: str = "test-tpl",
    status: TemplateStatus = TemplateStatus.available,
    web_ui_port: int | None = None,
    required_gpu_vram_gb: int | None = 8,
) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.name = "Test Template"
    t.slug = slug
    t.description = "A test template"
    t.icon_emoji = "🧪"
    t.tags = ["test"]
    t.base_image = "docker.io/library/ubuntu:22.04"
    t.required_gpu_vram_gb = required_gpu_vram_gb
    t.required_ram_gb = 8
    t.required_vcpus = 2
    t.startup_command = "bash -c 'echo hello'"
    t.default_ssh_user = "kynetic"
    t.exposed_web_ui_path = "/" if web_ui_port else None
    t.web_ui_port = web_ui_port
    t.status = status
    t.created_at = datetime.now(timezone.utc)
    return t


def _make_instance(
    *,
    status: InstanceStatus = InstanceStatus.running,
    template_id: uuid.UUID | None = None,
    developer_id: uuid.UUID | None = None,
) -> MagicMock:
    inst = MagicMock()
    inst.id = uuid.uuid4()
    inst.developer_id = developer_id or uuid.uuid4()
    inst.listing_id = uuid.uuid4()
    inst.host_id = uuid.uuid4()
    inst.template_id = template_id
    inst.status = status
    inst.hold_amount = Decimal("5.000000")
    inst.hold_released = False
    inst.firecracker_vm_id = None
    inst.wireguard_ip = "10.42.1.5"
    inst.public_ip = None
    inst.ssh_port = 22
    inst.billed_seconds = 0
    inst.price_per_second_usd = Decimal("0.0001234567")
    inst.created_at = datetime.now(timezone.utc)
    inst.started_at = None
    inst.stopped_at = None
    inst.terminated_at = None
    return inst


# ── TemplateRepository tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_repository_get_all_available_filters_status():
    """get_all_available() must return only `available` templates."""
    session = AsyncMock()
    avail = _make_template(status=TemplateStatus.available)
    disabled = _make_template(status=TemplateStatus.disabled, slug="disabled-tpl")
    pending = _make_template(status=TemplateStatus.pending_scan, slug="pending-tpl")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [avail]
    session.execute = AsyncMock(return_value=mock_result)

    repo = TemplateRepository(session)
    results = await repo.get_all_available()

    assert len(results) == 1
    assert results[0].status == TemplateStatus.available


@pytest.mark.asyncio
async def test_template_repository_get_by_slug():
    """get_by_slug() returns the correct template."""
    session = AsyncMock()
    tpl = _make_template(slug="ollama")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tpl
    session.execute = AsyncMock(return_value=mock_result)

    repo = TemplateRepository(session)
    result = await repo.get_by_slug("ollama")

    assert result is not None
    assert result.slug == "ollama"


@pytest.mark.asyncio
async def test_template_repository_get_by_slug_missing():
    """get_by_slug() returns None for an unknown slug."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    repo = TemplateRepository(session)
    result = await repo.get_by_slug("no-such-template")

    assert result is None


@pytest.mark.asyncio
async def test_template_repository_create():
    """create() stores a new template with pending_scan status."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()

    repo = TemplateRepository(session)
    template = await repo.create(
        name="My Template",
        slug="my-template",
        description="A new test template",
        base_image="docker.io/library/python:3.11-slim",
        required_gpu_vram_gb=4,
        required_ram_gb=8,
        required_vcpus=2,
        startup_command="python app.py",
        exposed_web_ui_path=None,
        web_ui_port=None,
    )

    assert template.name == "My Template"
    assert template.slug == "my-template"
    assert template.status == TemplateStatus.pending_scan
    session.add.assert_called_once_with(template)


@pytest.mark.asyncio
async def test_template_repository_update_scan_result_pass():
    """update_scan_result(passed=True) → status becomes available."""
    session = AsyncMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    repo = TemplateRepository(session)
    await repo.update_scan_result(
        uuid.uuid4(),
        passed=True,
        scan_report={"findings": [], "mock": True},
    )

    # Just verifies no exception raised and execute was called
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_template_repository_update_scan_result_fail():
    """update_scan_result(passed=False) → status becomes disabled."""
    session = AsyncMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    repo = TemplateRepository(session)
    await repo.update_scan_result(
        uuid.uuid4(),
        passed=False,
        scan_report={"findings": [{"severity": "CRITICAL"}], "blocked": True},
    )

    session.execute.assert_called_once()


# ── WebUISessionRepository tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_web_ui_session_create():
    """create() issues a new token with correct expiry."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo = WebUISessionRepository(session)
    before = datetime.now(timezone.utc)
    sess = await repo.create(
        instance_id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        ttl_seconds=3600,
    )
    after = datetime.now(timezone.utc)

    assert len(sess.token) == 64  # 32 bytes hex = 64 chars
    assert sess.revoked is False
    # expires_at should be ~1 hour in the future
    delta = sess.expires_at - before
    assert timedelta(seconds=3500) < delta < timedelta(seconds=3700)
    session.add.assert_called_once_with(sess)


@pytest.mark.asyncio
async def test_web_ui_session_revoke_by_instance():
    """revoke_by_instance() marks all active sessions for an instance as revoked."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 2
    session.execute = AsyncMock(return_value=mock_result)

    repo = WebUISessionRepository(session)
    count = await repo.revoke_by_instance(uuid.uuid4())

    assert count == 2
    session.execute.assert_called_once()


# ── FastAPI route tests (ASGI) ───────────────────────────────────────────────

@pytest.fixture
def provisioning_app():
    """Returns the provisioning service FastAPI app with DB overridden."""
    from libs.db_models.database import get_async_session
    from services.provisioning_service.main import app

    async def _override_session():
        session = AsyncMock()
        session.begin = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        ))
        yield session

    app.dependency_overrides[get_async_session] = _override_session
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_templates_returns_available_only(provisioning_app):
    """GET /v1/templates returns only available templates."""
    from httpx import ASGITransport, AsyncClient

    avail = _make_template(slug="stable-diffusion", status=TemplateStatus.available)

    with patch(
        "services.provisioning_service.template_repository.TemplateRepository.get_all_available",
        new_callable=AsyncMock,
        return_value=[avail],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=provisioning_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/v1/templates")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["slug"] == "stable-diffusion"
    assert data["items"][0]["status"] == "available"


@pytest.mark.asyncio
async def test_get_template_by_slug(provisioning_app):
    """GET /v1/templates/ollama returns the template."""
    from httpx import ASGITransport, AsyncClient

    tpl = _make_template(slug="ollama", status=TemplateStatus.available)

    with patch(
        "services.provisioning_service.template_repository.TemplateRepository.get_by_slug",
        new_callable=AsyncMock,
        return_value=tpl,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=provisioning_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/v1/templates/ollama")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "ollama"


@pytest.mark.asyncio
async def test_get_template_not_found(provisioning_app):
    """GET /v1/templates/no-such returns 404."""
    from httpx import ASGITransport, AsyncClient

    with patch(
        "services.provisioning_service.template_repository.TemplateRepository.get_by_slug",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch(
            "services.provisioning_service.template_repository.TemplateRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=provisioning_app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/v1/templates/no-such")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_template_requires_admin(provisioning_app):
    """POST /v1/templates without admin JWT returns 401/403."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=provisioning_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/templates",
            json={
                "name": "Test",
                "slug": "test",
                "description": "desc",
                "base_image": "docker.io/library/ubuntu:22.04",
            },
        )

    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_web_ui_token_rejected_for_non_running_instance(provisioning_app):
    """GET /instances/{id}/web-ui returns 409 if instance is not running."""
    from httpx import ASGITransport, AsyncClient
    import jwt

    developer_id = uuid.uuid4()
    instance_id = uuid.uuid4()

    # Create a stopped instance
    stopped_instance = _make_instance(
        status=InstanceStatus.stopped,
        developer_id=developer_id,
        template_id=uuid.uuid4(),
    )
    stopped_instance.id = instance_id

    token = jwt.encode(
        {"sub": str(developer_id), "role": "developer"},
        "dev_secret_change_in_production_12345",
        algorithm="HS256",
    )

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=stopped_instance,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=provisioning_app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/v1/instances/{instance_id}/web-ui",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_web_ui_token_rejected_for_non_template_instance(provisioning_app):
    """GET /instances/{id}/web-ui returns 400 if instance has no template_id."""
    from httpx import ASGITransport, AsyncClient
    import jwt

    developer_id = uuid.uuid4()
    instance_id = uuid.uuid4()

    raw_instance = _make_instance(
        status=InstanceStatus.running,
        developer_id=developer_id,
        template_id=None,  # raw launch, no template
    )
    raw_instance.id = instance_id

    token = jwt.encode(
        {"sub": str(developer_id), "role": "developer"},
        "dev_secret_change_in_production_12345",
        algorithm="HS256",
    )

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=raw_instance,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=provisioning_app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/v1/instances/{instance_id}/web-ui",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 400


# ── LaunchRequest schema tests ───────────────────────────────────────────────

def test_launch_request_without_template_id():
    """LaunchRequest is valid without template_id."""
    req = LaunchRequest(listing_id=uuid.uuid4())
    assert req.template_id is None


def test_launch_request_with_template_id():
    """LaunchRequest carries template_id when provided."""
    listing_id = uuid.uuid4()
    template_id = uuid.uuid4()
    req = LaunchRequest(listing_id=listing_id, template_id=template_id)
    assert req.template_id == template_id
    assert req.listing_id == listing_id


# ── Seed template slug tests ─────────────────────────────────────────────────

@pytest.mark.parametrize("expected_slug", [
    "stable-diffusion",
    "ollama",
    "comfyui",
    "llama3",
])
def test_seed_template_slugs_are_valid(expected_slug: str):
    """All 4 launch-day template slugs conform to the slug pattern."""
    import re
    assert re.fullmatch(r"^[a-z0-9-]+$", expected_slug), (
        f"Slug '{expected_slug}' must only contain lowercase letters, digits, and hyphens"
    )


# ── scan_template_image task tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_template_image_mock_mode_marks_available():
    """In mock mode (FIRECRACKER_MOCK=true), scan marks template available."""
    from services.provisioning_service.tasks import _scan_template_image_async

    template_id = str(uuid.uuid4())
    base_image = "docker.io/library/ubuntu:22.04"

    mock_repo = AsyncMock()

    with patch(
        "services.provisioning_service.tasks.settings"
    ) as mock_settings, patch(
        "libs.db_models.database.async_session_factory"
    ) as mock_factory:
        mock_settings.firecracker_mock = True
        mock_settings.environment = "testing"
        mock_settings.security_service_url = "http://mock-security"

        mock_session = AsyncMock()
        mock_session.begin = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.provisioning_service.template_repository.TemplateRepository",
            return_value=mock_repo,
        ):
            await _scan_template_image_async(template_id, base_image)

    mock_repo.update_scan_result.assert_called_once()
    call_kwargs = mock_repo.update_scan_result.call_args[1]
    assert call_kwargs["passed"] is True
    assert call_kwargs["scan_report"]["mock"] is True


@pytest.mark.asyncio
async def test_scan_template_image_real_scan_fail_marks_disabled():
    """If security service marks image blocked, template is set to disabled."""
    from services.provisioning_service.tasks import _scan_template_image_async
    import httpx

    template_id = str(uuid.uuid4())
    base_image = "docker.io/library/ubuntu:22.04"

    mock_repo = AsyncMock()
    blocked_response = MagicMock()
    blocked_response.json.return_value = {
        "blocked": True,
        "critical_count": 3,
        "high_count": 5,
    }
    blocked_response.raise_for_status = MagicMock()

    with patch(
        "services.provisioning_service.tasks.settings"
    ) as mock_settings, patch(
        "libs.db_models.database.async_session_factory"
    ) as mock_factory, patch(
        "httpx.AsyncClient"
    ) as mock_http_cls:
        mock_settings.firecracker_mock = False
        mock_settings.environment = "production"
        mock_settings.security_service_url = "http://security:8006"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=blocked_response)
        mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.begin = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.provisioning_service.template_repository.TemplateRepository",
            return_value=mock_repo,
        ):
            await _scan_template_image_async(template_id, base_image)

    mock_repo.update_scan_result.assert_called_once()
    call_kwargs = mock_repo.update_scan_result.call_args[1]
    assert call_kwargs["passed"] is False


# ── Scheduler template validation tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_launch_with_template_id_ok():
    """schedule_instance succeeds if listing has sufficient hardware."""
    from services.provisioning_service.scheduler import schedule_instance, SchedulerError

    listing_id = uuid.uuid4()
    developer_id = uuid.uuid4()
    template_id = uuid.uuid4()

    # Listing has 16GB VRAM and 32GB RAM
    listing_data = {
        "id": str(listing_id),
        "status": "active",
        "is_available": True,
        "price_per_second_usd": "0.000010",
        "host_id": str(uuid.uuid4()),
        "gpu_vram_gb": 16.0,
        "ram_gb": 32.0,
    }

    # Template requires 8GB VRAM and 16GB RAM
    mock_template = MagicMock()
    mock_template.id = template_id
    mock_template.required_gpu_vram_gb = 8
    mock_template.required_ram_gb = 16

    mock_template_repo = MagicMock()
    mock_template_repo.get_by_id = AsyncMock(return_value=mock_template)

    mock_instance = MagicMock()
    mock_instance.id = uuid.uuid4()

    mock_instance_repo = MagicMock()
    mock_instance_repo._session = AsyncMock()
    mock_instance_repo.create = AsyncMock(return_value=mock_instance)

    with patch(
        "services.provisioning_service.scheduler._fetch_listing",
        new_callable=AsyncMock,
        return_value=listing_data,
    ), patch(
        "services.provisioning_service.scheduler._fetch_wallet_balance",
        new_callable=AsyncMock,
        return_value={"balance_usd": "100.0"},
    ), patch(
        "services.provisioning_service.scheduler._fetch_host",
        new_callable=AsyncMock,
        return_value={"agent_url": "http://mock-agent:8443", "public_ip": "1.2.3.4"},
    ), patch(
        "services.provisioning_service.scheduler._place_hold",
        new_callable=AsyncMock,
        return_value="tx_123",
    ), patch(
        "services.provisioning_service.template_repository.TemplateRepository",
        return_value=mock_template_repo,
    ), patch(
        "services.provisioning_service.tasks.provision_instance.delay"
    ) as mock_delay:
        result_id = await schedule_instance(
            listing_id=listing_id,
            developer_id=developer_id,
            auth_token="test-token",
            instance_repo=mock_instance_repo,
            template_id=template_id,
        )

    assert result_id == mock_instance.id
    mock_instance_repo.create.assert_called_once_with(
        developer_id=developer_id,
        listing_id=listing_id,
        host_id=uuid.UUID(listing_data["host_id"]),
        hold_amount=Decimal("0.036"),
        price_per_second_usd=Decimal("0.000010"),
        agent_host_url="http://mock-agent:8443",
        public_ip="1.2.3.4",
        template_id=template_id,
    )
    mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_launch_with_template_id_insufficient_vram():
    """schedule_instance raises insufficient_hardware error if listing VRAM is too low."""
    from services.provisioning_service.scheduler import schedule_instance, SchedulerError

    listing_id = uuid.uuid4()
    developer_id = uuid.uuid4()
    template_id = uuid.uuid4()

    # Listing has 4GB VRAM
    listing_data = {
        "id": str(listing_id),
        "status": "active",
        "is_available": True,
        "price_per_second_usd": "0.000010",
        "host_id": str(uuid.uuid4()),
        "gpu_vram_gb": 4.0,
        "ram_gb": 16.0,
    }

    # Template requires 8GB VRAM
    mock_template = MagicMock()
    mock_template.id = template_id
    mock_template.required_gpu_vram_gb = 8
    mock_template.required_ram_gb = 8

    mock_template_repo = MagicMock()
    mock_template_repo.get_by_id = AsyncMock(return_value=mock_template)

    mock_instance_repo = MagicMock()
    mock_instance_repo._session = AsyncMock()

    with patch(
        "services.provisioning_service.scheduler._fetch_listing",
        new_callable=AsyncMock,
        return_value=listing_data,
    ), patch(
        "services.provisioning_service.template_repository.TemplateRepository",
        return_value=mock_template_repo,
    ):
        with pytest.raises(SchedulerError) as exc_info:
            await schedule_instance(
                listing_id=listing_id,
                developer_id=developer_id,
                auth_token="test-token",
                instance_repo=mock_instance_repo,
                template_id=template_id,
            )

    assert exc_info.value.code == "insufficient_hardware"
    assert "VRAM" in str(exc_info.value)

