"""
Template Repository — Phase 6: Zero-Setup App Templates.

All database access for the template registry and web UI sessions.
All methods require an active AsyncSession passed in from the route/task.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.template_models import Template, TemplateStatus, TemplateWebUISession

log = structlog.get_logger(__name__)


# ── Template Repository ────────────────────────────────────────────────────

class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Reads ──────────────────────────────────────────────────────────────

    async def get_all_available(self) -> Sequence[Template]:
        """Public listing — only returns templates that passed image scanning."""
        result = await self._session.execute(
            select(Template)
            .where(Template.status == TemplateStatus.available)
            .order_by(Template.name)
        )
        return result.scalars().all()

    async def get_all(self) -> Sequence[Template]:
        """Admin listing — all templates including pending and disabled."""
        result = await self._session.execute(
            select(Template).order_by(Template.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, template_id: uuid.UUID) -> Template | None:
        result = await self._session.execute(
            select(Template).where(Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Template | None:
        result = await self._session.execute(
            select(Template).where(Template.slug == slug)
        )
        return result.scalar_one_or_none()

    # ── Writes ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        name: str,
        slug: str,
        description: str,
        base_image: str,
        required_gpu_vram_gb: int | None,
        required_ram_gb: int,
        required_vcpus: int,
        startup_command: str | None,
        exposed_web_ui_path: str | None,
        web_ui_port: int | None,
        icon_emoji: str = "🚀",
        tags: list[str] | None = None,
    ) -> Template:
        template = Template(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description=description,
            base_image=base_image,
            required_gpu_vram_gb=required_gpu_vram_gb,
            required_ram_gb=required_ram_gb,
            required_vcpus=required_vcpus,
            startup_command=startup_command,
            exposed_web_ui_path=exposed_web_ui_path,
            web_ui_port=web_ui_port,
            icon_emoji=icon_emoji,
            tags=tags or [],
            status=TemplateStatus.pending_scan,
        )
        self._session.add(template)
        await self._session.flush()
        log.info("template.created", template_id=str(template.id), slug=slug)
        return template

    async def update_scan_result(
        self,
        template_id: uuid.UUID,
        *,
        passed: bool,
        scan_report: dict,
    ) -> None:
        new_status = TemplateStatus.available if passed else TemplateStatus.disabled
        await self._session.execute(
            update(Template)
            .where(Template.id == template_id)
            .values(
                status=new_status,
                last_scanned_at=datetime.now(timezone.utc),
                scan_report=scan_report,
            )
        )
        log.info(
            "template.scan_result",
            template_id=str(template_id),
            passed=passed,
            new_status=new_status.value,
        )

    async def set_status(self, template_id: uuid.UUID, status: TemplateStatus) -> None:
        await self._session.execute(
            update(Template).where(Template.id == template_id).values(status=status)
        )


# ── Web UI Session Repository ──────────────────────────────────────────────

class WebUISessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        instance_id: uuid.UUID,
        template_id: uuid.UUID,
        ttl_seconds: int = 3600,
    ) -> TemplateWebUISession:
        """
        Issues a new short-lived web UI access token for the given instance.
        Token is a cryptographically random hex string (64 chars = 256 bits).
        """
        token = secrets.token_hex(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        session_obj = TemplateWebUISession(
            id=uuid.uuid4(),
            instance_id=instance_id,
            template_id=template_id,
            token=token,
            expires_at=expires_at,
            revoked=False,
        )
        self._session.add(session_obj)
        await self._session.flush()

        log.info(
            "web_ui_session.created",
            instance_id=str(instance_id),
            expires_at=expires_at.isoformat(),
        )
        return session_obj

    async def get_valid_by_token(self, token: str) -> TemplateWebUISession | None:
        """Returns the session only if it exists, is not revoked, and is not expired."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(TemplateWebUISession).where(
                TemplateWebUISession.token == token,
                TemplateWebUISession.revoked == False,        # noqa: E712
                TemplateWebUISession.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def revoke_by_instance(self, instance_id: uuid.UUID) -> int:
        """Revoke all active web UI sessions for an instance (called on termination)."""
        result = await self._session.execute(
            update(TemplateWebUISession)
            .where(
                TemplateWebUISession.instance_id == instance_id,
                TemplateWebUISession.revoked == False,        # noqa: E712
            )
            .values(revoked=True)
        )
        count = result.rowcount
        if count:
            log.info(
                "web_ui_sessions.revoked",
                instance_id=str(instance_id),
                count=count,
            )
        return count
