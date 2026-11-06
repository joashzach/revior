"""Data adapter interface (PRD F22). Business logic depends only on this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NetworkData:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    road_polylines: dict[str, list] = field(default_factory=dict)  # "FROM-TO" -> [[lng, lat], ...]


@dataclass
class ServiceCatalog:
    scenario: dict[str, Any]
    dwell_minutes: float
    services: list[dict[str, Any]]


class TransportDataAdapter(ABC):
    @abstractmethod
    def load_network(self) -> NetworkData: ...

    @abstractmethod
    def load_services(self) -> ServiceCatalog: ...

    @abstractmethod
    def stream_service_updates(self) -> AsyncIterator[dict[str, Any]]:
        """Live feed of service updates (delays/cancellations). Mock adapter yields nothing."""
