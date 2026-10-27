"""Runtime sponsor-integration status. Derived from what actually happened in this process,
never from configuration alone.

    LIVE                   a real request / execution succeeded in this process
    CONFIGURED_UNVERIFIED  configured, but no successful call yet
    FALLBACK               not configured; local / simulated path in use
    UNAVAILABLE            configured, and the last attempt failed with no success since
"""

import os

from . import llm, sources
from . import world_model as wm

_WM = {"ingests": 0, "conformance_port": "8/8 (tests/test_world_model.py)"}


def record_world_model_ingest():
    _WM["ingests"] += 1


def _remote_state(configured: bool, ok_at, err) -> str:
    if not configured:
        return "FALLBACK"
    if ok_at:
        return "LIVE"
    return "UNAVAILABLE" if err else "CONFIGURED_UNVERIFIED"


def integration_status():
    cfg = llm.config()
    ls = llm.status()
    zs = sources.zetaris_status()
    z_configured = bool(os.environ.get("ZETARIS_REST_URL")) and os.environ.get("SAMPLE_MODE", "").lower() not in ("1", "true", "yes")
    rows = [
        {"sponsor": "Meterless", "capability": "World Model engine: evidence intake, as-of-cutoff verifier cross-check, "
                                                "model context builder, stale-evidence gate",
         "required": True, "state": "LIVE" if _WM["ingests"] else "CONFIGURED_UNVERIFIED",
         "detail": f"{wm.ENGINE}; in-process engine (Meterless engines are reference architectures implemented in-stack); "
                   f"{_WM['ingests']} ingests this process; conformance port {_WM['conformance_port']}"},
        {"sponsor": "Zetaris", "capability": "Federated read of the six source systems via documented REST SQL route",
         "required": True, "state": _remote_state(z_configured, zs["last_ok_at"], zs["last_error"]),
         "detail": (f"{zs['url_host']}: served {zs['systems_served'] or 'nothing yet'}; last error: {zs['last_error'] or 'none'}"
                    if z_configured else "ZETARIS_REST_URL not set (or SAMPLE_MODE) -> local synthetic fixtures")},
        {"sponsor": "NVIDIA Nemotron", "capability": "Explanation + strongest-counterargument phrasing (cite- and amount-checked)",
         "required": False, "state": _remote_state(cfg["enabled"], ls["last_ok_at"], ls["last_error"]),
         "detail": (f"{cfg['provider']} {cfg['model']}: {ls['ok_calls']} ok / {ls['failed_calls']} failed calls; "
                    f"served model {ls['served_model'] or '-'}; last error {ls['last_error'] or 'none'}")
         if cfg["enabled"] else "NVIDIA_API_KEY / LLM_BASE_URL not set -> deterministic template narrator"},
        {"sponsor": "Cursor", "capability": "Development environment (not a runtime integration)", "required": True,
         "state": "N/A", "detail": "See docs/INTEGRATIONS.md"},
    ]
    return {"rows": rows, "summary": {r["sponsor"]: r["state"] for r in rows}}
