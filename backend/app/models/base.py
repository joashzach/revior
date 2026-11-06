from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {datetime: DateTime(timezone=True), int: BigInteger}


def pg_enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name)


NODE_KIND = ("rail_station", "bus_stop", "hub_only")
EDGE_MODE = ("rail", "road", "walk")
SERVICE_MODE = ("local_train", "bus", "charter_bus", "shuttle")
SERVICE_STATUS = ("scheduled", "delayed", "cancelled", "running", "completed", "rerouted")
PASSENGER_STATE = (
    "REGISTERED", "BOOKED", "AFFECTED", "REQUESTED", "HELD", "CONFIRMED",
    "WAITLISTED", "UNRESOLVED", "RESOLVED_ALT", "REOFFER",
)
ALLOC_STATUS = ("held", "swap_held", "confirmed", "declined", "expired", "released")
CHOICE_RANK = ("1", "2", "auto", "cascade", "claim", "swap")
