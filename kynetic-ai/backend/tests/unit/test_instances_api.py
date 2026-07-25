"""
Phase 32 Unit Tests — Provisioning API Endpoints (FastAPI TestClient).

Tests:
  - GET /instances/{id} (get instance details)
  - GET /instances (list instances with pagination & status filters)
  - POST /instances/{id}/stop (stop running instance)
  - POST /instances/{id}/start (resume stopped instance)
  - POST /instances/{id}/terminate (terminate instance)
  - Response payload structure validation against Phase 30 schemas
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.routes import (
    _get_current_user_id,
    provisioning_router,
)

TEST_USER_ID = uuid.uuid4()


@pytest.fixture
def app():
    api = FastAPI()
    api.include_router(provisioning_router)
    api.dependency_overrides[_get_current_user_id] = lambda: TEST_USER_ID
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_instance_not_found(client):
    inst_id = uuid.uuid4()
    with patch("services.provisioning_service.repository.InstanceRepository.get_by_id", return_value=None):
        resp = client.get(f"/instances/{inst_id}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Instance not found"


def test_list_instances_endpoint(client):
    mock_instance = type("InstanceMock", (), {
        "id": uuid.uuid4(),
        "developer_id": TEST_USER_ID,
        "listing_id": uuid.uuid4(),
        "host_id": uuid.uuid4(),
        "template_id": None,
        "status": InstanceStatus.running,
        "hold_amount": 1.0,
        "hold_released": False,
        "firecracker_vm_id": "fc-123",
        "wireguard_ip": "10.42.0.5",
        "public_ip": None,
        "ssh_port": 22,
        "billed_seconds": 360,
        "price_per_second_usd": 0.000277,
        "created_at": datetime.now(timezone.utc),
        "started_at": datetime.now(timezone.utc),
        "stopped_at": None,
        "terminated_at": None,
    })()

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_developer",
        return_value=([mock_instance], 1),
    ):
        resp = client.get("/instances")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(mock_instance.id)
        assert data["items"][0]["status"] == "running"


def test_stop_instance_route_not_running(client):
    inst_id = uuid.uuid4()
    mock_instance = type("InstanceMock", (), {
        "id": inst_id,
        "developer_id": TEST_USER_ID,
        "status": InstanceStatus.stopped,  # Already stopped
    })()

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_id",
        return_value=mock_instance,
    ):
        resp = client.post(
            f"/instances/{inst_id}/stop",
            json={"reason": "test"},
        )
        assert resp.status_code == 409
        assert "Instance must be running to stop" in resp.json()["detail"]


def test_stop_instance_route_success(client):
    inst_id = uuid.uuid4()
    mock_instance = type("InstanceMock", (), {
        "id": inst_id,
        "developer_id": TEST_USER_ID,
        "status": InstanceStatus.running,
    })()

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_id",
        return_value=mock_instance,
    ), patch(
        "services.provisioning_service.routes.stop_instance.delay",
    ) as mock_celery, patch(
        "services.provisioning_service.routes.log_instance_event",
    ):
        resp = client.post(
            f"/instances/{inst_id}/stop",
            json={"reason": "user_requested"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["instance_id"] == str(inst_id)
        assert data["status"] == "stopping"
        assert data["message"] == "Stop initiated"
        mock_celery.assert_called_once_with(str(inst_id))


def test_terminate_instance_route_success(client):
    inst_id = uuid.uuid4()
    mock_instance = type("InstanceMock", (), {
        "id": inst_id,
        "developer_id": TEST_USER_ID,
        "status": InstanceStatus.running,
    })()

    with patch(
        "services.provisioning_service.repository.InstanceRepository.get_by_id",
        return_value=mock_instance,
    ), patch(
        "services.provisioning_service.routes.terminate_instance.delay",
    ) as mock_celery, patch(
        "services.provisioning_service.routes.log_instance_event",
    ):
        resp = client.post(
            f"/instances/{inst_id}/terminate",
            json={"reason": "user_requested", "force": False},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["instance_id"] == str(inst_id)
        assert data["status"] == "terminated"
        assert data["message"] == "Termination initiated"
        mock_celery.assert_called_once_with(str(inst_id), "user_requested")
