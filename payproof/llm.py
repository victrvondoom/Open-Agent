"""Bounded model client for NVIDIA Nemotron.

The model only *phrases* hypotheses and counterarguments. It never calculates
money, never decides status and never authorizes actions. Every sentence it returns
must cite record ids that exist in the case; the validator drops anything else
and counts it as an unsupported claim.

Providers (OpenAI-compatible chat completions):
  - NVIDIA API catalog: set NVIDIA_API_KEY (nvapi-...); base defaults to
    https://integrate.api.nvidia.com/v1, model to DEFAULT_MODEL (override with LLM_MODEL)
  - any other OpenAI-compatible endpoint serving Nemotron (e.g. Meterless Nightshift):
    LLM_BASE_URL + LLM_API_KEY (+ LLM_PROVIDER label)
If nothing is configured, SAMPLE_MODE=true, or a call fails, a deterministic template
narrator is used and the run metadata says so (model = "deterministic-fallback").
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

MAX_CALLS_PER_RUN = 2
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"  # organizer troubleshooting guide, section 7.3
# Copy the exact id from the model page on build.nvidia.com; verify with `python3 run.py --verify-model`.
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

# Runtime truth: LIVE only after a real completion from the configured endpoint succeeded in this process.
_STATUS = {"last_ok_at": None, "last_error": None, "ok_calls": 0, "failed_calls": 0, "served_model": None, "model_listed": None}


def status():
    return dict(_STATUS)


def config():
    key = os.environ.get("LLM_API_KEY") or os.environ.get("NVIDIA_API_KEY", "")
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/") or (NVIDIA_BASE_URL if os.environ.get("NVIDIA_API_KEY") else "")
    sample = os.environ.get("SAMPLE_MODE", "").lower() in ("1", "true", "yes")
    provider = os.environ.get("LLM_PROVIDER") or ("nvidia" if base == NVIDIA_BASE_URL else "openai-compatible")
    return {"base_url": base, "model": os.environ.get("LLM_MODEL", DEFAULT_MODEL), "provider": provider,
            "api_key": key, "enabled": bool(base) and not sample}


def verify_model(cfg=None) -> dict:
    """GET {base}/models (OpenAI-compatible discovery) and check the configured id is listed."""
    cfg = cfg or config()
    if not cfg["enabled"]:
        return {"ok": False, "reason": "LLM not configured (set NVIDIA_API_KEY or LLM_BASE_URL)"}
    req = urllib.request.Request(cfg["base_url"] + "/models", headers={"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {})
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("LLM_TIMEOUT_S", "25"))) as resp:
            ids = [m.get("id") for m in json.loads(resp.read()).get("data", [])]
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HTTP {e.code} from /models"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "reason": f"{type(e).__name__} contacting /models"}
    listed = cfg["model"] in ids
    _STATUS["model_listed"] = listed
    nemotron = sorted(i for i in ids if i and "nemotron" in i.lower())
    return {"ok": listed, "model": cfg["model"], "listed": listed, "nemotron_models_available": nemotron[:20],
            "reason": None if listed else "configured model id not in /models"}


SYSTEM = ("You are a finance-operations analyst. You may only restate facts given to you. "
          "Return strict JSON: {\"claims\": [{\"text\": str, \"cites\": [record_id,...]}]}. "
          "Every claim must cite at least one record id from the provided list. Do not compute new numbers; "
          "only use amounts that appear verbatim in the input. At most 4 claims, each under 40 words.")


_CACHE: dict[str, tuple] = {}  # (role, facts) hash -> (claims, meta); identical facts are never re-sent


class ModelClient:
    def __init__(self, enabled: bool | None = None):
        self.cfg = config()
        if enabled is False:
            self.cfg["enabled"] = False
        self.calls = []

    @property
    def identity(self):
        return f"{self.cfg['provider']}:{self.cfg['model']}" if self.cfg["enabled"] else "deterministic-fallback"

    def narrate(self, role: str, facts: dict, fallback_claims: list[dict]) -> tuple[list[dict], dict]:
        meta = {"role": role, "model": "deterministic-fallback", "provider": None, "latency_ms": 0, "status": "fallback"}
        if not self.cfg["enabled"] or len(self.calls) >= MAX_CALLS_PER_RUN:
            meta["reason"] = "model not configured or disabled for this path" if not self.cfg["enabled"] else "call budget exhausted"
            self.calls.append(meta)
            return fallback_claims, meta
        prompt = json.dumps({"task": role, "facts": facts}, default=str, sort_keys=True)
        key = hashlib.sha256((self.cfg["model"] + role + prompt).encode()).hexdigest()
        if key in _CACHE:
            claims, cached = _CACHE[key]
            meta = {**cached, "cached": True}
            self.calls.append(meta)
            return claims, meta
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
            _STATUS.update(last_ok_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), served_model=meta["model"])
            _STATUS["ok_calls"] += 1
            result = [{"text": str(c.get("text", ""))[:400], "cites": [str(x) for x in c.get("cites", [])][:8], "origin": "model"}
                      for c in claims[:4] if isinstance(c, dict)]
        except Exception as exc:
            code = getattr(exc, "code", None)
            meta.update(status="error_fallback", error=f"{type(exc).__name__}{f' {code}' if code else ''}")
            _STATUS.update(last_error=meta["error"])
            _STATUS["failed_calls"] += 1
            result = fallback_claims
        meta["latency_ms"] = round((time.monotonic() - t0) * 1000)
        if meta["status"] == "ok":
            _CACHE[key] = (result, meta)
        self.calls.append(meta)
        return result, meta
