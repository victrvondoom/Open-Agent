"""Bounded model client for NVIDIA Nemotron.

The model only *phrases* hypotheses and counterarguments. It never calculates
money, never decides status and never authorizes actions. Every sentence it returns
must cite record ids that exist in the case; the validator drops anything else
and counts it as an unsupported claim.

Providers (OpenAI-compatible chat completions):
  - Meterless Nightshift (set LLM_BASE_URL to the local Nightshift endpoint)
  - NVIDIA API catalog  (LLM_BASE_URL=https://integrate.api.nvidia.com/v1)
If LLM_BASE_URL is unset or the call fails, a deterministic template narrator is
used and the run metadata says so (model = "deterministic-fallback").
"""

import json
import os
import time
import urllib.request

MAX_CALLS_PER_RUN = 2
DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"


def config():
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    return {"base_url": base, "model": os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            "provider": os.environ.get("LLM_PROVIDER", "nightshift" if "localhost" in base or "127.0.0.1" in base else "nvidia"),
            "api_key": os.environ.get("LLM_API_KEY", ""), "enabled": bool(base)}


SYSTEM = ("You are a finance-operations analyst. You may only restate facts given to you. "
          "Return strict JSON: {\"claims\": [{\"text\": str, \"cites\": [record_id,...]}]}. "
          "Every claim must cite at least one record id from the provided list. Do not compute new numbers; "
          "only use amounts that appear verbatim in the input. At most 4 claims, each under 40 words.")


class ModelClient:
    def __init__(self):
        self.cfg = config()
        self.calls = []

    @property
    def identity(self):
        return f"{self.cfg['provider']}:{self.cfg['model']}" if self.cfg["enabled"] else "deterministic-fallback"

    def narrate(self, role: str, facts: dict, fallback_claims: list[dict]) -> tuple[list[dict], dict]:
        meta = {"role": role, "model": "deterministic-fallback", "provider": None, "latency_ms": 0, "status": "fallback"}
        if not self.cfg["enabled"] or len(self.calls) >= MAX_CALLS_PER_RUN:
            meta["reason"] = "LLM_BASE_URL not set" if not self.cfg["enabled"] else "call budget exhausted"
            self.calls.append(meta)
            return fallback_claims, meta
        prompt = json.dumps({"task": role, "facts": facts}, default=str)
        body = json.dumps({"model": self.cfg["model"], "temperature": 0, "max_tokens": 700,
                           "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}).encode()
        headers = {"Content-Type": "application/json"}
        if self.cfg["api_key"]:
            headers["Authorization"] = f"Bearer {self.cfg['api_key']}"
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(self.cfg["base_url"] + "/chat/completions", data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=float(os.environ.get("LLM_TIMEOUT_S", "25"))) as resp:
                payload = json.loads(resp.read())
            content = payload["choices"][0]["message"]["content"]
            start, end = content.find("{"), content.rfind("}")
            claims = json.loads(content[start:end + 1])["claims"]
            if not isinstance(claims, list):
                raise ValueError("claims not a list")
            meta.update(model=payload.get("model", self.cfg["model"]), provider=self.cfg["provider"], status="ok",
                        usage=payload.get("usage"))
            result = [{"text": str(c.get("text", ""))[:400], "cites": [str(x) for x in c.get("cites", [])][:8], "origin": "model"}
                      for c in claims[:4] if isinstance(c, dict)]
        except Exception as exc:
            meta.update(status="error_fallback", error=type(exc).__name__)
            result = fallback_claims
        meta["latency_ms"] = round((time.monotonic() - t0) * 1000)
        self.calls.append(meta)
        return result, meta
