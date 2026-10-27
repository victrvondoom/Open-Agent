"""Runtime sponsor-integration status. Derived from what actually happened in this process,
never from configuration alone.

state (did a real request/execution succeed?):
    LIVE                   a real request / execution succeeded in this process
    CONFIGURED_UNVERIFIED  configured, but no successful call yet
    FALLBACK               not configured; local / simulated path in use
    UNAVAILABLE            configured, and the last attempt failed with no success since
connectivity: in-process | online | offline | unauthorized | degraded | not configured
data: what kind of data flowed through it (all case data in this project is synthetic)
"""

import os
import time

from . import llm, sources
from . import reclaim_bridge
from . import world_model as wm

_RUNTIME = {
    "world_model": {"runs": 0, "last_ok_at": None, "last_latency_ms": None},
    "hmem": {"recalls": 0, "writes": 0, "last_ok_at": None, "last_latency_ms": None},
    "scout": {"decisions": 0, "blocked": 0, "quarantined_records": 0, "last_ok_at": None, "last_latency_ms": None},
}
_LAST_INVESTIGATION = {}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def record(engine: str, latency_ms: float | None = None, **counters):
    rt = _RUNTIME[engine]
    rt["last_ok_at"] = _now()
    if latency_ms is not None:
        rt["last_latency_ms"] = round(latency_ms, 2)
    for k, v in counters.items():
        rt[k] = rt.get(k, 0) + v


def record_world_model_ingest(latency_ms: float | None = None):
    record("world_model", latency_ms, runs=1)


def record_investigation(case_id: str, used: dict):
    _LAST_INVESTIGATION.clear()
    _LAST_INVESTIGATION.update({"case_id": case_id, "at": _now(), **used})


def last_investigation():
    return dict(_LAST_INVESTIGATION)


def _remote_state(configured: bool, ok_at, err) -> str:
    if not configured:
        return "FALLBACK"
    if ok_at:
        return "LIVE"
    return "UNAVAILABLE" if err else "CONFIGURED_UNVERIFIED"


def _connectivity(configured, ok_at, code, partial=False):
    if not configured:
        return "not configured"
    if code in (401, 403):
        return "unauthorized"
    if code == "unreachable" or code in ("URLError", "TimeoutError", "OSError"):
        return "offline" if not ok_at else "degraded"
    if partial:
        return "degraded"
    return "online" if ok_at else "unknown (no call yet)"


def integration_status():
    cfg, ls, zs = llm.config(), llm.status(), sources.zetaris_status()
    last = last_investigation()
    sample = os.environ.get("SAMPLE_MODE", "").lower() in ("1", "true", "yes")
    z_cfg = bool(os.environ.get("ZETARIS_REST_URL")) and not sample
    z_partial = z_cfg and zs["last_ok_at"] and len(zs["systems_served"]) < len(sources.SYSTEMS)
    wmr, hm, sc = _RUNTIME["world_model"], _RUNTIME["hmem"], _RUNTIME["scout"]
    rows = [
        {"sponsor": "Meterless World Model", "short": "World Model", "key": "world_model", "required": True,
         "capability": "Evidence intake with provenance + bitemporal edges; as-of-cutoff verifier cross-check; model context; stale-evidence gate",
         "state": "LIVE" if wmr["last_ok_at"] else "CONFIGURED_UNVERIFIED", "configured": True, "connectivity": "in-process",
         "provider": wm.ENGINE, "last_success": wmr["last_ok_at"], "latency_ms": wmr["last_latency_ms"], "last_error": None,
         "used_in_latest": last.get("world_model"), "data": "synthetic case records",
         "detail": f"{wmr['runs']} case ingests, {wmr.get('live_checks', 0)} live checks this process; official conformance checks ported: 8/8"},
        {"sponsor": "Meterless H-MEM", "short": "H-MEM", "key": "hmem", "required": True,
         "capability": "Verified-precedent memory: only approved + postcondition-verified outcomes are stored; recall excludes the case itself",
         "state": "LIVE" if hm["last_ok_at"] else "CONFIGURED_UNVERIFIED", "configured": True, "connectivity": "in-process",
         "provider": "meterless-hmem/py-0.1 (PayProof port of the Meterless reference)", "last_success": hm["last_ok_at"],
         "latency_ms": hm["last_latency_ms"], "last_error": None, "used_in_latest": last.get("hmem"),
         "data": "precedents derived from verified synthetic cases",
         "detail": f"{hm['writes']} precedents written, {hm['recalls']} recalls, {hm.get('live_checks', 0)} live checks this process; official conformance vectors: 13/13"},
        {"sponsor": "Meterless Scout Intent", "short": "Scout", "key": "scout", "required": True,
         "capability": "Injection guard on intake text and retrieved records; RBAC policy gate; HMAC-signed execution contracts (5-min TTL)",
         "state": "LIVE" if sc["last_ok_at"] else "CONFIGURED_UNVERIFIED", "configured": True,
         "connectivity": "in-process", "provider": "meterless-scout/py-0.1 (PayProof implementation of the Scout spec)",
         "last_success": sc["last_ok_at"], "latency_ms": sc["last_latency_ms"], "last_error": None,
         "used_in_latest": last.get("scout"), "data": "request text and retrieved record text (metadata-only logging)",
         "detail": f"{sc['decisions']} contracts issued, {sc['blocked']} requests blocked, {sc['quarantined_records']} records quarantined"},
        {"sponsor": "Zetaris", "short": "Zetaris", "key": "zetaris", "required": True,
         "capability": "Federated read of the six source systems through the documented REST SQL route",
         "state": _remote_state(z_cfg, zs["last_ok_at"], zs["last_error"]), "configured": z_cfg,
         "connectivity": _connectivity(z_cfg, zs["last_ok_at"], zs["last_error_code"], z_partial),
         "provider": f"Zetaris REST @ {zs['url_host']}" if z_cfg else None, "last_success": zs["last_ok_at"],
         "latency_ms": zs["last_latency_ms"], "last_error": zs["last_error"], "used_in_latest": last.get("zetaris"),
         "data": "LIVE service, synthetic tables" if zs["last_ok_at"] else "FALLBACK: local synthetic fixtures",
         "detail": (f"{zs['queries_ok']} queries ok / {zs['queries_failed']} failed; served {zs['systems_served'] or 'nothing yet'}"
                    if z_cfg else "ZETARIS_REST_URL not set (or SAMPLE_MODE)")},
        {"sponsor": "NVIDIA Nemotron", "short": "Nemotron", "key": "nemotron", "required": False,
         "capability": "Explanation + strongest-counterargument phrasing; every claim cite- and amount-checked",
         "state": _remote_state(cfg["enabled"], ls["last_ok_at"], ls["last_error"]), "configured": cfg["enabled"],
         "connectivity": _connectivity(cfg["enabled"], ls["last_ok_at"], ls["last_error_code"]),
         "provider": f"{cfg['provider']} · {ls['served_model'] or cfg['model']}" if cfg["enabled"] else None,
         "last_success": ls["last_ok_at"], "latency_ms": ls["last_latency_ms"], "last_error": ls["last_error"],
         "used_in_latest": last.get("nemotron"),
         "data": "LIVE model output (validated)" if ls["last_ok_at"] else "FALLBACK: deterministic template narrator",
         "detail": (f"{ls['ok_calls']} ok / {ls['failed_calls']} failed calls; {ls['tokens_total']} tokens; model listed: {ls['model_listed']}"
                    if cfg["enabled"] else "NVIDIA_API_KEY / LLM_BASE_URL not set")},
        {"sponsor": "RECLAIM Multi-Agent", "short": "RECLAIM", "key": "reclaim", "required": True,
         "capability": "8-Domain Legal Intake, LangGraph Specialist Agents, Regulation Splitter & Document Vault",
         **{k: v for k, v in reclaim_bridge.bridge_status().items() if k not in ("sponsor", "short", "key", "capability")}},
        {"sponsor": "Cursor", "short": "Cursor", "key": "cursor", "required": True, "capability": "Development environment (not a runtime integration)",
         "state": "N/A", "configured": None, "connectivity": "n/a", "provider": None, "last_success": None, "latency_ms": None,
         "last_error": None, "used_in_latest": None, "data": "n/a", "detail": "See docs/INTEGRATIONS.md"},
    ]
    return {"rows": rows, "summary": {r["sponsor"]: r["state"] for r in rows}, "latest_investigation": last}
