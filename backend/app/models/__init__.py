from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base. Aggregates are added in Stage 1 (PRD §7)."""
