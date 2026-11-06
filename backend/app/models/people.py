from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.models.base import Base, PASSENGER_STATE, pg_enum
from app.models.network import scen_fk


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    size: Mapped[int] = mapped_column(Integer)


class Passenger(Base):
    __tablename__ = "passengers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)  # stored lower-case
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    ticket_id: Mapped[str] = mapped_column(String)
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo_persona: Mapped[bool] = mapped_column(Boolean, default=False)
    persona_title: Mapped[str | None] = mapped_column(String, nullable=True)
    persona_emoji: Mapped[str | None] = mapped_column(String, nullable=True)
    persona_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    persona_claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    hub_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    destination_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    ticket_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    wheelchair: Mapped[bool] = mapped_column(Boolean, default=False)
    elderly: Mapped[bool] = mapped_column(Boolean, default=False)
    with_children: Mapped[bool] = mapped_column(Boolean, default=False)
    medical: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_deadline_at: Mapped[datetime | None] = mapped_column(nullable=True)
    allow_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    state: Mapped[str] = mapped_column(pg_enum("passenger_state", *PASSENGER_STATE), default="BOOKED")
    affected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    registered_at: Mapped[datetime] = mapped_column(default=utcnow)
    seed_plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        UniqueConstraint("scenario_id", "ticket_id"),
        Index("uq_passengers_scenario_email", "scenario_id", text("lower(email)"), unique=True,
              postgresql_where=text("email IS NOT NULL")),
        Index("ix_passengers_state", "scenario_id", "state"),
        Index("ix_passengers_ticket_service", "ticket_service_id"),
    )


class LoginToken(Base):
    __tablename__ = "login_tokens"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
