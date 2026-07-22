"""Tests for Phase 2 Celery background tasks."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_trigger_rebenchmark_publishes_to_redis():
    """trigger_rebenchmark should publish a JSON command to the host's Redis channel."""
    host_id = str(uuid.uuid4())

    with patch("services.host_service.tasks.redis") as mock_redis_mod:
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client

        from services.host_service.tasks import trigger_rebenchmark
        # Call as a regular function (not via Celery) for unit testing
        trigger_rebenchmark.apply(args=[host_id])

        mock_client.publish.assert_called_once()
        channel_arg = mock_client.publish.call_args[0][0]
        message_arg = mock_client.publish.call_args[0][1]
        assert host_id in channel_arg
        assert "rebenchmark" in message_arg


def test_rebenchmark_sweep_enqueues_stale_hosts():
    """rebenchmark_sweep should find stale hosts and enqueue trigger_rebenchmark for each."""
    import uuid as uuid_mod

    host_ids = [uuid_mod.uuid4(), uuid_mod.uuid4()]

    with patch("services.host_service.tasks.SyncSession") as mock_session_cls, \
         patch("services.host_service.tasks.trigger_rebenchmark") as mock_trigger:

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate DB returning 2 stale host IDs
        mock_session.execute.return_value.scalars.return_value.all.return_value = host_ids
        mock_trigger.delay = MagicMock()

        from services.host_service.tasks import rebenchmark_sweep
        result = rebenchmark_sweep.apply()

        assert mock_trigger.delay.call_count == 2


def test_mark_offline_sweep_updates_stale_hosts():
    """mark_offline_sweep should mark hosts offline if they haven't heartbeated recently."""
    import uuid as uuid_mod

    stale_ids = [uuid_mod.uuid4()]

    with patch("services.host_service.tasks.SyncSession") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_session.execute.return_value.scalars.return_value.all.return_value = stale_ids

        from services.host_service.tasks import mark_offline_sweep
        result = mark_offline_sweep.apply()

        # Should have executed an UPDATE
        assert mock_session.execute.call_count >= 1
        mock_session.commit.assert_called_once()
