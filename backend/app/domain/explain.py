"""Templated, human-readable explanations (PRD F8.6) and status headlines."""
from __future__ import annotations

from typing import Any

ORD = {"1": "1st", "2": "2nd"}


def _scores(takers: list[dict[str, Any]]) -> str:
    return ", ".join(f"{t['score']:g}" for t in takers)


def full_reason(label: str, rank_name: str, takers: list[dict[str, Any]], own_score: float,
                reason: str = "full") -> str:
    """"Choice 1 Bus-3 full: last seats went to scores 91, 88, 85 (yours 72)"."""
    if reason == "infeasible":
        return f"Choice {rank_name} {label} is no longer available to you."
    if not takers:
        return f"Choice {rank_name} {label} has no free seats for your party."
    note = ""
    if any(t["score"] < own_score and t.get("wheelchair") for t in takers):
        note = " (accessible seats are reserved for wheelchair passengers first)"
    return (f"Choice {rank_name} {label} full: last seats went to scores {_scores(takers[-3:])} "
            f"(yours {own_score:g}){note}.")


def placed(rank: str, label: str, seats: list[str], earlier: list[str], score_text: str, rule_version: int,
           any_fastest: bool, eta: str | None) -> str:
    seat_txt = f" Seats: {', '.join(seats)}."
    prefix = " ".join(earlier)
    if rank == "1":
        base = f"Placed on your choice 1: {label}.{seat_txt}"
    elif rank == "2":
        base = f"{prefix} Placed on choice 2: {label}.{seat_txt}"
    elif any_fastest:
        base = f"Any, fastest: {label} is the earliest arrival{f' (ETA {eta})' if eta else ''}.{seat_txt}"
    else:
        base = f"{prefix} Placed on {label} (best available by arrival time).{seat_txt}"
    return f"{base} {score_text}; rules v{rule_version}."


def waitlisted(reasons: list[str], waits: list[tuple[str, int]], score_text: str, rule_version: int) -> str:
    where = "; ".join(f"#{pos} for {label}" for label, pos in waits)
    return f"{' '.join(reasons)} You're waitlisted: {where}. {score_text}; rules v{rule_version}.".strip()


def unresolved(reasons: list[str], score_text: str, rule_version: int) -> str:
    return (f"{' '.join(reasons)} No seat could be found right now - see your alternatives "
            f"(later services, multi-leg, shared cab, nearby hub). {score_text}; rules v{rule_version}.").strip()


def headline(state: str, *, rank: str | None = None, label: str | None = None, position: int | None = None,
             wait_label: str | None = None, alt_title: str | None = None, status: str | None = None) -> str:
    if state == "HELD":
        return {"1": "Placed on your 1st choice ✓", "2": "Placed on your 2nd choice ✓",
                "cascade": "A seat opened up for you!", "claim": "Seat claimed - accept to keep it",
                "swap": "Switch ready - accept to keep it"}.get(rank or "", f"Moved to {label} - see why")
    if state == "CONFIRMED":
        return f"You're confirmed ✓ - {label}" if label else "You're confirmed ✓"
    if state == "REQUESTED":
        return "Request received - we'll allocate when the window closes"
    if state == "WAITLISTED":
        return f"Waitlisted #{position} for {wait_label}" if position else "You're on the waitlist"
    if state == "UNRESOLVED":
        return "No seat yet - see your alternatives"
    if state == "RESOLVED_ALT":
        return f"Alternative chosen: {alt_title}" if alt_title else "Alternative chosen"
    if state == "AFFECTED":
        return "Your trip was disrupted - choose an alternative"
    if state == "REOFFER":
        return "Your bus was re-routed - please choose again (you keep your seat until then)"
    return "On time - we'll alert you if anything changes."
