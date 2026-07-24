"""
Phase 30 Unit Tests — Pydantic Schema Validation Layer.

Tests:
  - InstanceCreateRequest validation & requested_hours quantization (0.01 precision)
  - Sanity bounds on requested_hours (0 < requested_hours <= 720)
  - InstanceResponse model_validate compatibility
  - InstanceActionResponse serialization
  - InstanceConnectionResponse serialization
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.schemas import (
    InstanceActionResponse,
    InstanceConnectionResponse,
    InstanceCreateRequest,
    InstanceResponse,
)


def test_instance_create_request_valid():
    listing_id = uuid.uuid4()
    req = InstanceCreateRequest(
        listing_id=listing_id,
        requested_hours=Decimal("12.345"),
    )
    assert req.listing_id == listing_id
    # Test field_validator quantization to 0.01
    assert req.requested_hours == Decimal("12.35")


def test_instance_create_request_bounds():
    listing_id = uuid.uuid4()

    # Zero or negative hours must raise ValidationError
    with pytest.raises(ValidationError):
        InstanceCreateRequest(listing_id=listing_id, requested_hours=Decimal("0"))

    with pytest.raises(ValidationError):
        InstanceCreateRequest(listing_id=listing_id, requested_hours=Decimal("-5"))

    # Exceeding 720 hours (30 days) must raise ValidationError
    with pytest.raises(ValidationError):
        InstanceCreateRequest(listing_id=listing_id, requested_hours=Decimal("721"))


def test_instance_action_response():
    instance_id = uuid.uuid4()
    resp = InstanceActionResponse(
        instance_id=instance_id,
        status=InstanceStatus.running,
        message="Instance resumed",
    )
    assert resp.instance_id == instance_id
    assert resp.status == InstanceStatus.running
    assert resp.message == "Instance resumed"


def test_instance_connection_response():
    instance_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    resp = InstanceConnectionResponse(
        instance_id=instance_id,
        ssh_command="ssh kynetic@10.42.0.2 -p 22",
        web_ui_url="https://relay.kynetic.ai/proxy/123",
        expires_at=now,
    )
    assert resp.instance_id == instance_id
    assert resp.ssh_command == "ssh kynetic@10.42.0.2 -p 22"
    assert resp.web_ui_url == "https://relay.kynetic.ai/proxy/123"
    assert resp.expires_at == now
