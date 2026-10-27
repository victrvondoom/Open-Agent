"""Runtime sponsor-integration status. Reports what is configured, never what is assumed."""

import os

from .llm import config as llm_config


def integration_status():
    llm = llm_config()
    rows = [
        {"sponsor": "NVIDIA Nemotron", "capability": "Narrative + strongest-counterargument phrasing (validated, cite-checked)",
         "required": True, "mode": "live" if llm["enabled"] else "fallback",
         "detail": f"{llm['provider']}:{llm['model']} @ {llm['base_url']}" if llm["enabled"]
         else "LLM_BASE_URL not set -> deterministic template narrator"},
        {"sponsor": "Meterless Nightshift", "capability": "AI provider routing Nemotron (OpenAI-compatible endpoint)",
         "required": True, "mode": "live" if llm["enabled"] and llm["provider"] == "nightshift" else "not configured",
         "detail": "Set LLM_BASE_URL to the local Nightshift endpoint and LLM_PROVIDER=nightshift"},
        {"sponsor": "Meterless Engine", "capability": "World Model ranking of counterfactual scenarios (advisory only)",
         "required": True, "mode": "configured (unverified contract)" if os.environ.get("METERLESS_URL") else "fallback",
         "detail": "METERLESS_URL not set -> deterministic impact ranking" if not os.environ.get("METERLESS_URL")
         else os.environ["METERLESS_URL"]},
        {"sponsor": "Zetaris", "capability": "Federated query over the six source systems (allowlisted SQL templates)",
         "required": True, "mode": "configured (unverified)" if os.environ.get("ZETARIS_URL") else "fallback",
         "detail": "ZETARIS_URL not set -> local synthetic fixtures" if not os.environ.get("ZETARIS_URL") else os.environ["ZETARIS_URL"]},
        {"sponsor": "Cursor", "capability": "Development environment (not a runtime integration)", "required": True,
         "mode": "n/a at runtime", "detail": "See docs/INTEGRATIONS.md"},
    ]
    live = [r["sponsor"] for r in rows if r["mode"] == "live"]
    return {"rows": rows, "summary": {"live": live, "fallback": [r["sponsor"] for r in rows if r["mode"] == "fallback"]}}
