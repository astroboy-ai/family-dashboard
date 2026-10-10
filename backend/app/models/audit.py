import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (Index("ix_agent_tool_calls_household_created", "household_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    result_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None]
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_household_created", "household_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())