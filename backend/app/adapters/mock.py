"""MockAdapter: reads seed files under ``seed/<key>/`` (PRD §11, F22)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import yaml

from app.adapters.base import NetworkData, ServiceCatalog, TransportDataAdapter

SEED_ROOT = Path(__file__).resolve().parents[2] / "seed"


class MockAdapter(TransportDataAdapter):
    def __init__(self, seed_key: str, root: Path | None = None):
        self.dir = (root or SEED_ROOT) / seed_key

    def _json(self, name: str, default: Any = None) -> Any:
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def load_network(self) -> NetworkData:
        poly = self._json("road_polylines.json", {}) or {}
        return NetworkData(self._json("nodes.json"), self._json("edges.json"), poly.get("edges", poly) if isinstance(poly, dict) else {})

    def polyline_source(self) -> str:
        poly = self._json("road_polylines.json", {}) or {}
        return poly.get("source", "fallback") if isinstance(poly, dict) else "fallback"

    def load_services(self) -> ServiceCatalog:
        raw = yaml.safe_load((self.dir / "services.yaml").read_text(encoding="utf-8"))
        return ServiceCatalog(raw["scenario"], float(raw.get("dwell_minutes", 1)), raw["services"])

    def load_generator_config(self) -> dict[str, Any]:
        return yaml.safe_load((self.dir / "passengers.yaml").read_text(encoding="utf-8"))

    def load_rules(self) -> dict[str, float]:
        return self._json("rules.json")

    async def stream_service_updates(self) -> AsyncIterator[dict[str, Any]]:
        return
        yield  # pragma: no cover  (makes this an async generator)
