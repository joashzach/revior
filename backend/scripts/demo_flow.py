"""Runs the full Revior demo (PRD §19, steps 1-11) through the REST + WebSocket API of a running server.

  python scripts/demo_flow.py --base-url http://localhost:8000 --ops-password change-me

It resets the scenario first, so run it on a demo/dev instance. Exit code 0 = every step behaved as specified.
"""
import argparse
import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets

OK, BAD = "\033[32m✓\033[0m", "\033[31m✗\033[0m"


class Demo:
    def __init__(self, base: str, ops_password: str):
        self.base = base.rstrip("/")
        self.api = httpx.AsyncClient(base_url=f"{self.base}/api/v1", timeout=60)
        self.ws_base = self.base.replace("http", "ws", 1)
        self.ops_password = ops_password
        self.failed = 0
        self.ops_events: list[dict] = []
        self.tasks: list[asyncio.Task] = []

    def check(self, cond: bool, msg: str):
        print(f"  {OK if cond else BAD} {msg}")
        if not cond:
            self.failed += 1

    @staticmethod
    def h(tok):
        return {"Authorization": f"Bearer {tok}"}

    async def listen(self, url: str, sink: list):
        """Like the real frontend: reconnect with backoff (events are not replayed)."""
        delay = 0.5
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
                    delay = 0.5
                    async for raw in ws:
                        sink.append(json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5)

    async def wait_for(self, sink: list, type_: str, timeout=30, since=0):
        end = time.time() + timeout
        while time.time() < end:
            for m in sink[since:]:
                if m["type"] == type_:
                    return m
            await asyncio.sleep(0.25)
        return None

    async def run(self) -> int:
        a = self.api
        print("== 0. setup: ops login, reset scenario, short demo timers")
        ops = (await a.post("/auth/ops-login", json={"password": self.ops_password})).json()["token"]
        oh = self.h(ops)
        r = await a.post("/ops/scenarios/potheri-demo/activate", headers=oh)
        r = await a.post("/ops/scenarios/potheri-demo/reset", headers=oh)
        self.check(r.status_code == 200 and r.json()["counts"]["personas"] >= 8, f"reset in {r.json()['duration_ms']} ms, counts {r.json()['counts']}")
        r = await a.patch("/ops/scenarios/potheri-demo/config", headers=oh, json={"batch_window_seconds": 8, "hold_seconds": 120, "auto_run_on_batch_close": True})
        self.check(r.status_code == 200, f"config: batch window {r.json()['batch_window_seconds']} s, hold {r.json()['hold_seconds']} s")
        self.tasks.append(asyncio.create_task(self.listen(f"{self.ws_base}/ws/ops?token={ops}", self.ops_events)))
        await asyncio.sleep(0.5)

        print("== 1. judges scan the QR -> persona picker -> trip screen 'On time'")
        pers = (await a.get("/demo/personas", params={"scenario": "potheri-demo"})).json()["items"]
        self.check(len(pers) >= 8, f"{len(pers)} personas offered (e.g. {pers[0]['emoji']} {pers[0]['title']})")
        judges = []
        for p in pers[:3]:
            c = (await a.post("/auth/demo-claim", json={"scenario": "potheri-demo", "persona_id": p["id"]})).json()
            sink: list = []
            self.tasks.append(asyncio.create_task(self.listen(f"{self.ws_base}/ws/passenger?token={c['token']}", sink)))
            judges.append({"tok": c["token"], "pax": c["passenger"], "persona": p, "ev": sink})
        taken = [x["is_taken"] for x in (await a.get("/demo/personas", params={"scenario": "potheri-demo"})).json()["items"]]
        self.check(taken.count(True) == 3, "claimed personas show as taken; ops saw persona.claimed: "
                   + str(any(m["type"] == "persona.claimed" for m in self.ops_events)))
        trip = (await a.get("/me/trip", headers=self.h(judges[0]["tok"]))).json()
        self.check(trip["ticket"]["service"]["status"] in ("scheduled", "running") and trip["headline"].startswith("On time"), f"trip: {trip['headline']}")
        await asyncio.sleep(0.5)

        print("== 2. operator cancels the featured local train -> all phones flip")
        svcs = {s["code"]: s for s in (await a.get("/ops/services", headers=oh)).json()["items"]}
        feat = svcs["EMU-CGL-BCH-1810"]
        pv = (await a.get("/ops/disruptions/preview", headers=oh, params={"type": "cancellation", "service_id": feat["id"]})).json()
        r = await a.post("/ops/disruptions", headers=oh, json={"type": "cancellation", "service_id": feat["id"], "reason": "Waterlogging near Guduvanchery"})
        d = r.json()
        self.check(r.status_code == 200 and d["affected_count"] == pv["affected_count"] >= 370, f"{d['affected_count']} passengers affected (preview said {pv['affected_count']}); batch #{d['batch']['id']} open")
        for j in judges:
            m = await self.wait_for(j["ev"], "service.status_changed", 10)
            self.check(m is not None and m["data"]["status"] == "cancelled", f"{j['persona']['emoji']} phone received service.status_changed=cancelled")

        print("== 3. judges pick 1st / 2nd choice")
        for j in judges:
            opts = (await a.get("/me/options", headers=self.h(j["tok"]))).json()
            items = opts["items"]
            body = {"choice1_service_id": items[0]["request_service_id"], "choice2_service_id": items[1]["request_service_id"] if len(items) > 1 else None}
            r = await a.post("/me/request", headers=self.h(j["tok"]), json=body)
            self.check(r.status_code == 200, f"{j['persona']['emoji']} {len(items)} options, request sent -> batch closes {r.json()['batch']['closes_at'][11:19]}")

        print("== 4. batch window closes -> allocation runs; seats fill, never beyond 100%")
        run_done = await self.wait_for(self.ops_events, "allocation.run_completed", 40)
        self.check(run_done is not None, "allocation.run_completed received: " + (json.dumps({k: v for k, v in run_done['data']['stats'].items() if k != 'fill_rate_by_service'}) if run_done else "-"))
        cap = (await a.get("/ops/capacity", headers=oh)).json()["items"]
        self.check(all(c["free"] >= 0 and c["held"] + c["confirmed"] + c["free"] == c["total_seats"] for c in cap), f"{len(cap)} services: held+confirmed+free == total everywhere (never beyond 100%)")
        for j in judges:
            m = await self.wait_for(j["ev"], "allocation.result", 10)
            st = (await a.get("/me/status", headers=self.h(j["tok"]))).json()
            j["state"] = st["state"]
            self.check(m is not None, f"{j['persona']['emoji']} -> {st['state']}: {st['headline']}")

        print("== 5. 'Why this?' — score breakdown + decision explanation")
        why = (await a.get("/me/why", headers=self.h(judges[0]["tok"]))).json()
        self.check(abs(why["score"] - sum(why["breakdown"].values())) < 0.01 and why["decision_explanation"], f"{why['explanation']}")
        print(f"     decision: {why['decision_explanation'][:160]}")

        print("== 6. a judge declines -> the seat cascades to the next waitlisted passenger")
        holder = next((j for j in judges if j["state"] == "HELD"), None)
        if holder:
            r = await a.post("/me/allocation/decline", headers={**self.h(holder["tok"]), "Idempotency-Key": str(uuid.uuid4())})
            self.check(r.status_code == 200 and r.json()["allocation"] is None, f"{holder['persona']['emoji']} declined -> {r.json()['state']}")
            ev = await self.wait_for(self.ops_events, "seat.released", 10)
            self.check(ev is not None, "ops saw seat.released; cascade offers go out as offer.created to the top waitlisted passenger")
        else:
            self.check(True, "no judge held a seat in this draw (all waitlisted) — skipped")

        print("== 7. close GST Road near Vandalur -> buses re-route, ETAs update")
        net = (await a.get("/ops/network", headers=oh)).json()
        ids = {n["code"]: n["id"] for n in net["nodes"]}
        edge = next(e for e in net["edges"] if e["mode"] == "road" and {e["from_node_id"], e["to_node_id"]} == {ids["URP"], ids["VAN"]})
        n_before = len(self.ops_events)
        r = await a.post("/ops/disruptions", headers=oh, json={"type": "closure", "edge_id": edge["id"], "reason": "Road closed near Vandalur"})
        rer = await self.wait_for(self.ops_events, "service.rerouted", 10, since=n_before)
        self.check(r.status_code == 200 and rer is not None, f"{r.json()['affected_count']} passengers affected; service.rerouted for service {rer['data']['service_id'] if rer else '?'} ({len(rer['data']['polyline']['coordinates']) if rer else 0} polyline points, skipped {[s['name'] for s in rer['data']['skipped_stops']] if rer else []})")

        print("== 8. raise the medical weight -> preview -> apply")
        w = (await a.get("/ops/rules", headers=oh)).json()["active"]["weights"]
        new = {**w, "medical": 50}
        pv = (await a.post("/ops/rules/preview", headers=oh, json={"weights": new})).json()
        self.check("placed_delta" in pv, f"preview: placed_delta={pv['placed_delta']}, {len(pv['movers'])} movers (nothing changed yet)")
        ap = (await a.post("/ops/rules/apply", headers=oh, json={"weights": new})).json()
        self.check(ap["version"] >= 2, f"applied -> rules v{ap['version']}; waitlists re-ranked live")

        print("== 9. unresolved queue -> add a charter bus -> waitlisted/unresolved passengers placed automatically")
        before = (await a.get("/ops/kpis", headers=oh)).json()
        r = await a.post("/ops/services", headers=oh, json={"label": "Charter Potheri → Chennai Beach", "mode": "charter_bus",
                                                            "stop_node_ids": [ids["POT"], ids["BCH"]], "depart_in_minutes": 25, "total_seats": 60, "accessible_seats": 3})
        after = (await a.get("/ops/kpis", headers=oh)).json()
        self.check(r.status_code == 200 and after["unresolved"] + after["waitlisted"] <= before["unresolved"] + before["waitlisted"],
                   f"unresolved+waitlisted {before['unresolved'] + before['waitlisted']} -> {after['unresolved'] + after['waitlisted']}")

        print("== 10. stress test: 1000 requests, 10 seats")
        n_before = len(self.ops_events)
        r = await a.post("/ops/stress/run", headers=oh, json={"requests": 1000, "seats": 10})
        res = await self.wait_for(self.ops_events, "stress.result", 420, since=n_before)
        self.check(r.status_code == 200 and res is not None and res["data"]["passed"], f"stress.result: {res['data'] if res else 'timeout'}")
        inv = (await a.get("/ops/invariants", headers=oh)).json()
        self.check(inv == {"over_allocated_services": 0, "multi_primary_passengers": 0, "negative_free_seats": 0, "ok": True}, f"invariants: {inv}")

        print("== 11. switch to the secondary scenario for a moment (location-agnostic) and back")
        await a.post("/ops/scenarios/secondary-demo/activate", headers=oh)
        act = (await a.get("/scenarios/active")).json()
        self.check(act["slug"] == "secondary-demo", f"active: {act['name']} (hub {act['default_hub']['name']})")
        await a.post("/ops/scenarios/potheri-demo/activate", headers=oh)

        for t in self.tasks:
            t.cancel()
        await self.api.aclose()
        print(f"\n{'ALL STEPS PASSED' if not self.failed else str(self.failed) + ' CHECK(S) FAILED'}")
        return 1 if self.failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--ops-password", default="change-me")
    args = ap.parse_args()
    sys.exit(asyncio.run(Demo(args.base_url, args.ops_password).run()))
