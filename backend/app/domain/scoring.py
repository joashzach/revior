"""Transparent priority score (PRD F7). Pure functions — ticket price/class is NEVER an input."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

FEATURES = ("medical", "wheelchair", "elderly", "with_children", "deadline_urgency", "wait_time")
DEFAULT_WEIGHTS = {"medical": 30.0, "wheelchair": 30.0, "elderly": 15.0, "with_children": 10.0,
                   "deadline_urgency": 20.0, "wait_time": 20.0}
DEADLINE_HORIZON_MIN = 180.0
WAIT_HORIZON_MIN = 120.0
_FAR_FUTURE = datetime.max.replace(tzinfo=None)


@dataclass(frozen=True)
class ScoreInput:
    wheelchair: bool
    elderly: bool
    with_children: bool
    medical: bool
    connection_deadline_at: datetime | None
    affected_at: datetime | None

    @classmethod
    def of(cls, p) -> "ScoreInput":
        return cls(p.wheelchair, p.elderly, p.with_children, p.medical, p.connection_deadline_at, p.affected_at)


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def features(inp: ScoreInput, now: datetime) -> dict[str, float]:
    """Each feature normalised to [0, 1]."""
    if inp.connection_deadline_at is not None:
        mins = (inp.connection_deadline_at - now).total_seconds() / 60
        urgency = 1.0 - _clamp(mins / DEADLINE_HORIZON_MIN)
    else:
        urgency = 0.0
    waited = (now - inp.affected_at).total_seconds() / 60 if inp.affected_at is not None else 0.0
    return {"medical": 1.0 if inp.medical else 0.0, "wheelchair": 1.0 if inp.wheelchair else 0.0,
            "elderly": 1.0 if inp.elderly else 0.0, "with_children": 1.0 if inp.with_children else 0.0,
            "deadline_urgency": urgency, "wait_time": _clamp(waited / WAIT_HORIZON_MIN)}


def _n(x: float) -> str:
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def explain_score(total: float, points: dict[str, float], inp: ScoreInput, now: datetime) -> str:
    """e.g. "Priority 82 = medical +30, waited 2h +20, connection in 50 min +14.4, elderly +15, children +2.6"."""
    parts = []
    for k, pts in sorted(points.items(), key=lambda kv: -kv[1]):
        if pts <= 0:
            continue
        if k == "wait_time":
            mins = max(0.0, (now - inp.affected_at).total_seconds() / 60) if inp.affected_at else 0.0
            label = f"waited {_n(mins / 60)}h" if mins >= 60 else f"waited {int(round(mins))} min"
        elif k == "deadline_urgency":
            mins = (inp.connection_deadline_at - now).total_seconds() / 60 if inp.connection_deadline_at else 0.0
            label = f"connection in {max(0, int(round(mins)))} min"
        elif k == "with_children":
            label = "children"
        else:
            label = k
        parts.append(f"{label} +{_n(pts)}")
    body = ", ".join(parts) if parts else "no priority factors"
    return f"Priority {_n(total)} = {body}"


def score(inp: ScoreInput, weights: dict[str, Any], now: datetime) -> tuple[float, dict[str, float], str]:
    f = features(inp, now)
    points = {k: round(float(weights.get(k, 0)) * f[k], 2) for k in FEATURES}
    total = round(sum(points.values()), 2)
    return total, points, explain_score(total, points, inp, now)


def sort_key(score_: float, affected_at: datetime | None, registered_at: datetime, pid: int):
    """Tie-breaks (F7.3): higher score, earlier affected_at, earlier registration/ticket, lower id."""
    aff = affected_at.replace(tzinfo=None) if affected_at else _FAR_FUTURE
    return (-round(score_, 2), aff, registered_at.replace(tzinfo=None), pid)
