"""Meterless engine adapter (advisory only).

Intended use: a Meterless engine (World Model) ranks the counterfactual scenarios
by investigative priority. The deterministic engine still computes every amount;
the engine output can only reorder the scenarios shown to the reviewer.

STATUS: The HTTP contract below is an assumption. It has NOT been verified against
a running Meterless engine in this repository. With METERLESS_URL unset (the
default) the deterministic ranking (largest absolute variance impact first) is used
and reported as `deterministic-fallback`.
"""

import json
import os
import time
import urllib.request


def rank_scenarios(case_id: str, scenarios: list[dict]) -> tuple[list[dict], dict]:
    url = os.environ.get("METERLESS_URL", "").rstrip("/")
    engine = os.environ.get("METERLESS_ENGINE", "world-model")
    meta = {"engine": engine, "status": "deterministic-fallback", "latency_ms": 0}
    if not url:
        meta["reason"] = "METERLESS_URL not set"
        return scenarios, meta
    t0 = time.monotonic()
    try:
        body = json.dumps({"engine": engine, "case_id": case_id,
                           "scenarios": [{"id": s["id"], "delta_change": s["delta_change"], "changed_facts": s["changed_facts"]}
                                         for s in scenarios]}).encode()
        req = urllib.request.Request(f"{url}/v1/engines/{engine}/rank", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            order = json.loads(resp.read())["order"]
        known = {s["id"]: s for s in scenarios}
        ranked = [known[i] for i in order if i in known] + [s for s in scenarios if s["id"] not in order]
        meta["status"] = "ok"
        return ranked, meta
    except Exception as exc:
        meta.update(status="error_fallback", error=type(exc).__name__)
        return scenarios, meta
    finally:
        meta["latency_ms"] = round((time.monotonic() - t0) * 1000)
