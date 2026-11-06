"""Write contracts/examples/*.json — one sample payload per contract endpoint / WS event.

Shapes follow stranded-network-frontend-API-contract.md exactly (the frontend mocks from these).
`scripts/capture_examples.py` (Stage 9) can overwrite them with real captured responses.
Usage: python scripts/build_examples.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "contracts" / "examples"
TZ = "+00:00"


def t(hh, mm=0):  # example timestamps (UTC; frontend renders Asia/Kolkata)
    return f"2026-11-05T{hh:02d}:{mm:02d}:00{TZ}"


def node(i, code, name, lat, lng, hub=False, default=False, kind="rail_station"):
    return {"id": i, "code": code, "name": name, "lat": lat, "lng": lng, "kind": kind, "is_hub": hub, "is_default_hub": default}


POT = node(6, "POT", "Potheri", 12.8231, 80.0442, True, True)
TAM = node(11, "TAM", "Tambaram", 12.9249, 80.1177)
GND = node(15, "GND", "Guindy", 13.0067, 80.2206)
CGL = node(1, "CGL", "Chengalpattu", 12.6819, 79.9888)
BCH = node(18, "BCH", "Chennai Beach", 13.095, 80.2907)
KTM = node(5, "KTM", "Kattankulathur", 12.8139, 80.0366, True)
NEEDS = {"wheelchair": False, "elderly": False, "with_children": False, "medical": False, "connection_deadline_at": None}


def svc(i, code, label, mode, status, o, d, dep, arr, acc=False, delay=0):
    return {"id": i, "code": code, "label": label, "mode": mode, "status": status, "delay_minutes": delay,
            "depart_at": dep, "arrive_at": arr, "origin": o, "destination": d, "accessible": acc}


TRAIN = svc(1, "EMU-CGL-BCH-1810", "6:10 PM Chengalpattu → Chennai Beach local", "local_train", "cancelled", CGL, BCH, t(12, 30), t(14, 10))
BUS3 = svc(9, "MTC-570A", "MTC 570A Potheri → Guindy", "bus", "scheduled", POT, GND, t(12, 35), t(13, 40), True)
BUS5 = svc(10, "MTC-570B", "MTC 570B Potheri → Guindy", "bus", "scheduled", POT, GND, t(12, 45), t(13, 50), True)
PAX = {"id": 4021, "name": "Asha Wheeler", "email": "wheelchair-guindy@demo.revior.test", "phone": None, "is_seeded": False,
       "is_demo_persona": True, "hub": POT, "destination": GND, "party_size": 1,
       "needs": {**NEEDS, "wheelchair": True}, "allow_auto": True, "state": "AFFECTED", "ticket_id": "VT-3FA9C2", "affected_at": t(12, 31)}
TICKET = {"ticket_id": "VT-3FA9C2", "service": TRAIN}
BATCH = {"id": 7, "status": "open", "opens_at": t(12, 31), "closes_at": "2026-11-05T12:31:30+00:00"}
ALLOC = {"id": 311, "service": BUS3, "seat_count": 1, "seats": ["W01"], "choice_rank": "1", "status": "held", "is_primary": True,
         "hold_expires_at": t(12, 36), "score": 72.0, "explanation": "Choice 1 MTC 570A had a free accessible seat. Priority 72 = wheelchair +30, waited 1h +10, deadline +32."}
WL = {"service_id": 9, "label": "MTC 570A Potheri → Guindy", "position": 2, "total": 5, "is_swap": False}
LEG = {"service": BUS3, "from": POT, "to": GND, "depart_at": t(12, 35), "arrive_at": t(13, 40), "has_seats": True}
POD = {"id": 12, "origin": POT, "destination": TAM, "mode": "cab", "capacity": 4, "seats_taken": 2, "status": "forming",
       "members": [{"passenger_id": 4021, "name": "Asha Wheeler", "seat_count": 1}, {"passenger_id": 4033, "name": "Priya Iyer", "seat_count": 1}],
       "route_km": 24.6, "fare_total": 542.8, "fare_per_seat": 271.4}
PERSONA = {"id": 4021, "title": "Wheelchair user → Guindy", "emoji": "♿", "summary": "Needs accessible seat · travelling alone",
           "destination": GND, "party_size": 1, "needs": {**NEEDS, "wheelchair": True}, "is_taken": False}
ALT = {"type": "MULTI_LEG", "ref": "MULTI:9+21", "title": "Bus to Tambaram, then local to Chennai Beach",
       "description": "Bus Potheri → Tambaram, change (10 min), local Tambaram → Beach", "eta_at": t(14, 20), "legs": [LEG],
       "pod": None, "requires_allocation": True}
STATUS = {"state": "HELD", "batch": None, "allocation": ALLOC, "swap_offer": None, "waitlist": [], "resolved_alternative": None,
          "headline": "Placed on your 1st choice ✓", "server_time": t(12, 33)}
WHY = {"score": 72.0, "breakdown": {"medical": 0, "wheelchair": 30, "elderly": 0, "with_children": 0, "deadline_urgency": 32, "wait_time": 10},
       "explanation": "Priority 72 = wheelchair +30, connection in 45 min +15, waited 1h +10 …",
       "decision_explanation": "Choice 1 MTC 570A had a free accessible seat.", "rule_version": 1,
       "weights": {"medical": 30, "wheelchair": 30, "elderly": 15, "with_children": 10, "deadline_urgency": 20, "wait_time": 20},
       "waitlist": [WL]}
OPT = {"option_id": "S9", "request_service_id": 9, "label": "MTC 570A Potheri → Guindy", "mode": "bus", "legs": [LEG], "depart_at": t(12, 35),
       "eta_at": t(13, 40), "transfers": 0, "is_multi_leg": False, "seats_left": 3, "accessible_seats_left": 1, "is_full": False,
       "meets_deadline": True, "accessible": True}
STATS = {"units": 340, "placed_choice1": 301, "placed_choice2": 20, "placed_auto": 8, "waitlisted": 7, "unresolved": 4, "duration_ms": 420,
         "fill_rate_by_service": [{"service_id": 9, "label": "MTC 570A Potheri → Guindy", "fill_rate": 1.0}]}
KPI = {"affected": 340, "checked_in": 338, "not_checked_in": 2, "requested": 0, "held": 120, "confirmed": 180, "waitlisted": 7, "unresolved": 4,
       "resolved_alt": 0, "avg_wait_min": 6.4, "median_time_to_placement_min": 1.2, "fill_rate": 0.96, "batch": None}
CAPROW = {"service": BUS3, "total_seats": 45, "held": 10, "confirmed": 32, "free": 3, "accessible_free": 1, "waitlist_len": 2}
POLY = {"type": "LineString", "coordinates": [[80.0442, 12.8231], [80.1177, 12.9249], [80.2206, 13.0067]]}
EDGE = {"id": 40, "from_node_id": 8, "to_node_id": 9, "mode": "road", "road_name": "GST Road", "is_closed": False, "polyline": POLY}
NOTIF = {"id": 55, "template": "placed", "title": "You have a seat", "body": "Placed on MTC 570A (seat W01). Accept within 10 minutes.",
         "created_at": t(12, 32), "read": False}
LOGIN_QR = {"url": "http://localhost:5173/qr-login?t=8Zk3…", "expires_at": "2026-11-06T12:31:00+00:00"}

EXAMPLES = {
    "health": {"status": "ok", "db": "ok", "version": "1.0.0", "server_time": t(12, 31)},
    "scenarios_active": {"slug": "potheri-demo", "name": "Potheri - Chengalpattu to Chennai Beach corridor", "default_hub": POT,
                         "join_url": "http://localhost:5173/demo-join?scenario=potheri-demo", "demo_mode": True},
    "auth_register": {"token": "<jwt>", "passenger": {**PAX, "is_demo_persona": False, "state": "BOOKED"}, "ticket": {**TICKET, "service": {**TRAIN, "status": "scheduled"}}},
    "auth_login": {"token": "<jwt>", "passenger": PAX},
    "auth_qr_login": {"token": "<jwt>", "passenger": PAX},
    "auth_ops_login": {"token": "<jwt>"},
    "demo_personas": {"items": [PERSONA, {**PERSONA, "id": 4022, "title": "Family of 4 → Tambaram", "emoji": "👨‍👩‍👧‍👦", "is_taken": True}]},
    "auth_demo_claim": {"token": "<jwt>", "passenger": PAX, "persona": {**PERSONA, "is_taken": True}},
    "me_demo_switch": {"token": "<jwt>", "passenger": PAX, "persona": {**PERSONA, "is_taken": True}},
    "hubs_nearby": {"hubs": [{"hub": POT, "distance_km": 0.4, "is_default": True}, {"hub": KTM, "distance_km": 3.2, "is_default": False}],
                    "selected_hub_id": 6, "reason": "nearest"},
    "destinations": {"items": [TAM, GND, BCH]},
    "me": PAX,
    "me_patch": PAX,
    "me_trip": {"ticket": TICKET, "disruption": {"id": 3, "type": "cancellation", "reason": "Waterlogging near Guduvanchery", "created_at": t(12, 31)},
                "headline": "Your train is cancelled — waterlogging near Guduvanchery"},
    "me_options": {"items": [OPT], "batch": BATCH},
    "me_request": {"id": 901, "batch": BATCH, "choice1_service_id": 9, "choice2_service_id": 10, "any_fastest": False},
    "me_status": STATUS,
    "me_status_requested": {**STATUS, "state": "REQUESTED", "batch": BATCH, "allocation": None, "headline": "Request received — allocating soon"},
    "me_status_waitlisted": {**STATUS, "state": "WAITLISTED", "allocation": None, "waitlist": [WL], "headline": "Waitlisted #2 for MTC 570A Potheri → Guindy"},
    "me_status_confirmed": {**STATUS, "state": "CONFIRMED", "allocation": {**ALLOC, "status": "confirmed", "hold_expires_at": None}, "headline": "You're confirmed ✓"},
    "me_allocation_accept": {**STATUS, "state": "CONFIRMED", "allocation": {**ALLOC, "status": "confirmed", "hold_expires_at": None}, "headline": "You're confirmed ✓"},
    "me_allocation_decline": {**STATUS, "state": "WAITLISTED", "allocation": None, "waitlist": [WL], "headline": "Seat released — you stay on the waitlist"},
    "me_swap": {**STATUS, "swap_offer": None, "waitlist": [{**WL, "is_swap": True}]},
    "me_claim": STATUS,
    "me_why": WHY,
    "me_alternatives": {"items": [ALT, {"type": "POD", "ref": "POD:12", "title": "Share a cab to Tambaram", "description": "2/4 seats taken · ₹271 each",
                                         "eta_at": t(13, 10), "legs": [], "pod": POD, "requires_allocation": False}]},
    "me_alternatives_accept": {**STATUS, "state": "RESOLVED_ALT", "allocation": None, "resolved_alternative": ALT, "headline": "Alternative chosen"},
    "me_pods_suggested": {"items": [POD]},
    "me_pods_create": POD,
    "pods_join": POD,
    "pods_confirm": {**POD, "status": "confirmed"},
    "me_login_qr": LOGIN_QR,
    "me_notifications": {"items": [NOTIF]},
    "ops_scenarios": {"items": [{"slug": "potheri-demo", "name": "Potheri", "is_active": True}, {"slug": "secondary-demo", "name": "Mumbai CSMT", "is_active": False}]},
    "ops_scenario_activate": {"slug": "potheri-demo"},
    "ops_scenario_reset": {"duration_ms": 950, "counts": {"passengers": 410, "services": 18, "personas": 10}},
    "ops_scenario_config": {"batch_window_seconds": 30, "hold_seconds": 120, "auto_run_on_batch_close": True, "delay_threshold_minutes": 20,
                            "hub_radius_km": 10, "open_booking_enabled": False, "sim_speed": 10, "demo_mode": True, "join_qr_mode": "corner"},
    "ops_network": {"nodes": [POT, TAM, GND], "edges": [EDGE]},
    "ops_services": {"items": [{**BUS3, "total_seats": 45, "held": 10, "confirmed": 32, "free": 3, "accessible_free": 1, "waitlist_len": 2, "polyline": POLY}]},
    "ops_services_create": {**BUS3, "id": 30, "code": "CHR-OPS-1", "label": "Charter Potheri → Egmore", "mode": "charter_bus"},
    "ops_disruptions_preview": {"affected_count": 340, "by_destination": [{"destination": TAM, "count": 85}, {"destination": GND, "count": 70}]},
    "ops_disruptions_create": {"disruption": {"id": 3, "type": "cancellation", "service_id": 1, "edge_id": None, "delay_minutes": None,
                                              "reason": "Waterlogging near Guduvanchery", "created_at": t(12, 31), "resolved_at": None},
                               "affected_count": 340, "batch": BATCH},
    "ops_disruptions": {"items": [{"id": 3, "type": "cancellation", "target_label": TRAIN["label"], "reason": "Waterlogging near Guduvanchery",
                                   "created_at": t(12, 31), "resolved_at": None, "affected_count": 340}]},
    "ops_disruption_resolve": {"id": 3, "resolved_at": t(13, 0)},
    "ops_batches_current": {"batch": BATCH, "request_count": 312},
    "ops_batches_close": {**BATCH, "status": "closed"},
    "ops_allocation_run": {"run_id": 5, "stats": STATS},
    "ops_allocation_run_get": {"id": 5, "mode": "greedy", "started_at": t(12, 32), "finished_at": t(12, 32), "rule_version": 1, "stats": STATS},
    "ops_kpis": KPI,
    "ops_clusters": {"items": [{"id": "11-2026-11-05T12:30:00+00:00-general", "destination": TAM, "time_bucket_start": t(12, 30), "needs_class": "general",
                                "size": 24, "demand_seats": 30, "capacity_seats": 40}]},
    "ops_capacity": {"items": [CAPROW]},
    "ops_allocations": {"items": [{"passenger": {"id": 4021, "name": "Asha Wheeler", "party_size": 1, "needs": {**NEEDS, "wheelchair": True}},
                                   "score": 72.0, "choice_rank": "1", "service_label": BUS3["label"], "status": "held", "hold_expires_at": t(12, 36),
                                   "explanation": ALLOC["explanation"]}], "page": 1, "page_size": 50, "total": 1},
    "ops_unresolved": {"items": [{"passenger": PAX, "waited_min": 12.5, "alternatives": [ALT]}]},
    "ops_fairness": {"by_needs_class": [{"needs_class": "accessible", "placement_rate": 1.0, "wait_p50": 1.0, "wait_p90": 2.0},
                                        {"needs_class": "priority", "placement_rate": 0.98, "wait_p50": 1.0, "wait_p90": 3.0},
                                        {"needs_class": "general", "placement_rate": 0.93, "wait_p50": 2.0, "wait_p90": 6.0}],
                     "by_destination": [{"destination": TAM, "placement_rate": 0.96, "unresolved": 1}], "wait_gini": 0.18},
    "ops_map": {"nodes": [POT, TAM], "edges": [EDGE], "services": [{"id": 9, "label": BUS3["label"], "mode": "bus", "status": "scheduled", "polyline": POLY}],
                "vehicles": [{"service_id": 9, "lat": 12.85, "lng": 80.06, "progress": 0.1}], "clusters": [{"node_id": 11, "size": 24}]},
    "ops_invariants": {"over_allocated_services": 0, "multi_primary_passengers": 0, "negative_free_seats": 0, "ok": True},
    "ops_passenger": {"passenger": PAX, "status": STATUS, "why": WHY},
    "ops_passenger_login_qr": LOGIN_QR,
    "ops_rules": {"active": {"version": 2, "weights": WHY["weights"]}, "history": [{"version": 1, "weights": WHY["weights"], "created_at": t(12, 0)},
                                                                                    {"version": 2, "weights": WHY["weights"], "created_at": t(12, 40)}]},
    "ops_rules_preview": {"placed_delta": 2, "by_needs_class": [{"needs_class": "priority", "placement_rate_before": 0.9, "placement_rate_after": 0.95}],
                          "movers": [{"passenger_id": 4021, "name": "Asha Wheeler", "service_label": BUS3["label"], "position_before": 4, "position_after": 2}]},
    "ops_rules_apply": {"version": 2},
    "ops_audit": {"items": [{"id": 1, "actor": "system", "action": "allocation.placed", "entity_type": "allocation", "entity_id": 311,
                             "explanation": ALLOC["explanation"], "created_at": t(12, 32)}], "page": 1, "page_size": 50, "total": 1},
    "ops_notifications": {"items": [{"passenger_name": "Asha Wheeler", "channel": "email_sim", "template": "placed", "body": NOTIF["body"], "created_at": t(12, 32)}],
                          "page": 1, "page_size": 50, "total": 1},
    "ops_open_booking": {"enabled": True},
    "ops_demo_personas": {"items": [{**PERSONA, "is_taken": True, "claimed_at": t(12, 20), "state": "AFFECTED"}]},
    "ops_stress_run": {"run_id": "stress-1"},
}

WS = {
    "service.status_changed": {"service_id": 1, "status": "cancelled", "delay_minutes": 0},
    "disruption.created": {"disruption": {"id": 3, "type": "cancellation", "service_id": 1, "edge_id": None, "delay_minutes": None, "reason": "Waterlogging", "created_at": t(12, 31), "resolved_at": None}},
    "disruption.resolved": {"disruption": {"id": 3, "type": "cancellation", "service_id": 1, "edge_id": None, "delay_minutes": None, "reason": "Waterlogging", "created_at": t(12, 31), "resolved_at": t(13, 0)}},
    "batch.opened": {"batch_id": 7, "closes_at": "2026-11-05T12:31:30+00:00"},
    "batch.closed": {"batch_id": 7, "closes_at": "2026-11-05T12:31:30+00:00"},
    "allocation.run_started": {"run_id": 5},
    "allocation.run_completed": {"run_id": 5, "stats": STATS},
    "allocation.result": {"state": "HELD", "allocation": ALLOC, "explanation": ALLOC["explanation"]},
    "offer.created": {"allocation": {**ALLOC, "choice_rank": "cascade"}},
    "swap.offer_created": {"allocation": {**ALLOC, "status": "swap_held", "is_primary": False, "choice_rank": "swap"}},
    "hold.expiring": {"allocation_id": 311, "seconds_left": 30},
    "hold.expired": {"allocation_id": 311},
    "allocation.confirmed": {"allocation_id": 311, "passenger_id": 4021, "service_id": 9},
    "allocation.declined": {"allocation_id": 311, "passenger_id": 4021, "service_id": 9},
    "seat.released": {"service_id": 9, "count": 1},
    "waitlist.position_changed": {"service_id": 9, "position": 1, "total": 5},
    "eta.updated": {"service_id": 9, "eta_at": t(13, 52)},
    "service.rerouted": {"service_id": 9, "polyline": POLY, "skipped_stops": [node(9, "VAN", "Vandalur", 12.8914, 80.0817)]},
    "vehicle.positions": {"items": [{"service_id": 9, "lat": 12.85, "lng": 80.06, "progress": 0.1}]},
    "kpi.updated": KPI,
    "rules.updated": {"version": 2},
    "pod.updated": {"pod": POD},
    "passenger.registered": {"passenger": PAX, "is_demo_persona": True},
    "persona.claimed": {"persona_id": 4021},
    "persona.released": {"persona_id": 4021},
    "notification.created": NOTIF,
    "stress.progress": {"sent": 500, "ok": 10, "conflicts": 480, "errors": 0},
    "stress.result": {"total": 1000, "confirmed": 10, "capacity": 10, "over_allocations": 0, "five_xx": 0, "passed": True},
}
ERRORS = {"error_seat_unavailable": {"error": {"code": "SEAT_UNAVAILABLE", "message": "That seat was just taken.", "details": {}}},
          "error_validation": {"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": {"fields": {"email": "value is not a valid email address"}}}}}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in EXAMPLES.items():
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, data in WS.items():
        msg = {"type": name, "ts": t(12, 31), "scenario": "potheri-demo", "data": data}
        (OUT / f"ws_{name.replace('.', '_')}.json").write_text(json.dumps(msg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, payload in ERRORS.items():
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(len(EXAMPLES), "REST examples,", len(WS), "WS examples,", len(ERRORS), "error examples ->", OUT)


if __name__ == "__main__":
    main()
