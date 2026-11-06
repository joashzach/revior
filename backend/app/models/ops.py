from datetime import datetime
from typing import Any

from sqlalchemy import (BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.models.base import ALLOC_STATUS, CHOICE_RANK, Base, pg_enum
from app.models.network import scen_fk


class Disruption(Base):
    __tablename__ = "disruptions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    type: Mapped[str] = mapped_column(pg_enum("disruption_type", "cancellation", "delay", "closure"))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=True)
    edge_id: Mapped[int | None] = mapped_column(ForeignKey("edges.id", ondelete="CASCADE"), nullable=True)
    delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PassengerDisruption(Base):
    __tablename__ = "passenger_disruptions"
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), primary_key=True)
    disruption_id: Mapped[int] = mapped_column(ForeignKey("disruptions.id", ondelete="CASCADE"), primary_key=True)
    affected_at: Mapped[datetime] = mapped_column(default=utcnow)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    status: Mapped[str] = mapped_column(pg_enum("batch_status", "open", "closed", "allocated"), default="open")
    opens_at: Mapped[datetime] = mapped_column(default=utcnow)
    closes_at: Mapped[datetime] = mapped_column()
    trigger: Mapped[str] = mapped_column(
        pg_enum("batch_trigger", "disruption", "late_request", "capacity_add", "reoffer", "manual"),
        default="disruption")
    __table_args__ = (Index("one_open_batch", "scenario_id", unique=True, postgresql_where=text("status = 'open'")),)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), index=True)
    choice1_service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    choice2_service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    any_fastest: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(pg_enum("request_status", "queued", "processed", "superseded"), default="queued")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("batch_id", "passenger_id"),)


class AllocationRun(Base):
    __tablename__ = "allocation_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id", ondelete="SET NULL"), nullable=True)
    rule_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mode: Mapped[str] = mapped_column(pg_enum("run_mode", "greedy", "ortools", "preview"), default="greedy")
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Allocation(Base):
    __tablename__ = "allocations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    run_id: Mapped[int | None] = mapped_column(ForeignKey("allocation_runs.id", ondelete="SET NULL"), nullable=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    seat_count: Mapped[int] = mapped_column(Integer, default=1)
    choice_rank: Mapped[str] = mapped_column(pg_enum("choice_rank", *CHOICE_RANK))
    status: Mapped[str] = mapped_column(pg_enum("allocation_status", *ALLOC_STATUS))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    hold_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expiring_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    __table_args__ = (
        Index("one_primary_active", "passenger_id", unique=True,
              postgresql_where=text("is_primary AND status IN ('held','confirmed')")),
        Index("one_swap_active", "passenger_id", unique=True, postgresql_where=text("status = 'swap_held'")),
        Index("ix_alloc_status", "scenario_id", "status"),
    )


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), index=True)
    is_swap: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(pg_enum("waitlist_status", "active", "offered", "removed"), default="active")
    last_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("service_id", "passenger_id"),)


class Pod(Base):
    __tablename__ = "pods"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    origin_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    destination_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    mode: Mapped[str] = mapped_column(pg_enum("pod_mode", "cab", "auto"))
    capacity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(pg_enum("pod_status", "forming", "full", "confirmed", "departed", "cancelled"),
                                        default="forming")
    route_km: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    fare_total: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PodMember(Base):
    __tablename__ = "pod_members"
    pod_id: Mapped[int] = mapped_column(ForeignKey("pods.id", ondelete="CASCADE"), primary_key=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), primary_key=True)
    seat_count: Mapped[int] = mapped_column(Integer, default=1)
    joined_at: Mapped[datetime] = mapped_column(default=utcnow)


class PriorityRule(Base):
    __tablename__ = "priority_rules"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    version: Mapped[int] = mapped_column(Integer)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (Index("one_active_rule", "scenario_id", unique=True, postgresql_where=text("is_active")),)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    actor: Mapped[str] = mapped_column(pg_enum("audit_actor", "system", "operator", "passenger"))
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    passenger_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(pg_enum("notification_channel", "push", "email_sim", "sms_sim", "sms"),
                                         default="email_sim")
    template: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(pg_enum("notification_status", "queued", "sent", "failed"), default="sent")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
