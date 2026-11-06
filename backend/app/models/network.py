from datetime import datetime
from typing import Any

from sqlalchemy import (BigInteger, Boolean, Float, ForeignKey, Index, Integer, Numeric, String,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import utcnow
from app.models.base import Base, EDGE_MODE, NODE_KIND, SERVICE_MODE, SERVICE_STATUS, pg_enum


def scen_fk():
    return mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    seed_key: Mapped[str] = mapped_column(String)  # seed/<seed_key>/ directory
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    t0: Mapped[datetime] = mapped_column(default=utcnow)
    default_hub_node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    featured_service_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    rng_seed: Mapped[int] = mapped_column(Integer, default=42)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(pg_enum("node_kind", *NODE_KIND))
    is_hub: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default_hub: Mapped[bool] = mapped_column(Boolean, default=False)
    coord_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("scenario_id", "code"),)


class Edge(Base):
    __tablename__ = "edges"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    from_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    to_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(pg_enum("edge_mode", *EDGE_MODE))
    distance_km: Mapped[float] = mapped_column(Numeric(8, 3))
    base_minutes: Mapped[float] = mapped_column(Numeric(8, 2))
    road_name: Mapped[str | None] = mapped_column(String, nullable=True)
    polyline: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [[lng,lat],...]
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = scen_fk()
    code: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(pg_enum("service_mode", *SERVICE_MODE))
    status: Mapped[str] = mapped_column(pg_enum("service_status", *SERVICE_STATUS), default="scheduled")
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    has_seat_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    total_seats: Mapped[int] = mapped_column(Integer, default=0)
    accessible_seats: Mapped[int] = mapped_column(Integer, default=0)
    depart_at: Mapped[datetime] = mapped_column()
    arrive_at: Mapped[datetime] = mapped_column()
    polyline: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(pg_enum("service_created_by", "seed", "operator"), default="seed")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("scenario_id", "code"),)


class ServiceStop(Base):
    __tablename__ = "service_stops"
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    arrive_at: Mapped[datetime] = mapped_column()
    depart_at: Mapped[datetime] = mapped_column()
    is_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    is_via: Mapped[bool] = mapped_column(Boolean, default=False)  # pass-through node (no boarding)


class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    seat_no: Mapped[str] = mapped_column(String)
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(pg_enum("seat_status", "free", "held", "confirmed"), default="free")
    allocation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    __table_args__ = (
        UniqueConstraint("service_id", "seat_no"),
        Index("ix_seats_service_status", "service_id", "status"),
        Index("ix_seats_allocation", "allocation_id"),
    )
