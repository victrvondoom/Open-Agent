"""Source-system adapters.

`LocalFixtureSource` reads synthetic snapshots from data/cases (the default and the
only adapter exercised by tests). `ZetarisSource` runs a fixed allowlist of
parameterised federated SQL templates against a Zetaris endpoint; it is used only
when ZETARIS_URL is set and is NOT verified against a live Zetaris instance.

Either adapter returns the same shape: {case_id, dispute, feeds, sources{system: {system, records}}}.
Late-arriving events (stale-evidence simulation) are layered on top without
mutating the original records.
"""

import copy
import hashlib
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "cases"
PLANS_PATH = ROOT / "data" / "plans.json"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def load_plans():
    return json.loads(PLANS_PATH.read_text())


class LocalFixtureSource:
    name = "local-fixtures"
    live = False

    def __init__(self, cases_dir: Path = CASES_DIR):
        self.cases_dir = cases_dir
        self._overlays: dict[str, list[dict]] = {}

    def list_case_ids(self):
        return sorted(p.stem for p in self.cases_dir.glob("CASE-*.json"))

    def _base(self, case_id: str) -> dict:
        if not case_id.replace("-", "").isalnum():
            raise KeyError(case_id)
        path = self.cases_dir / f"{case_id}.json"
        if not path.exists():
            raise KeyError(case_id)
        return json.loads(path.read_text())

    def load_case(self, case_id: str) -> dict:
        case = self._base(case_id)
        for event in self._overlays.get(case_id, []):
            system = event["system"]
            case["sources"][system]["records"].append(copy.deepcopy(event["record"]))
        case["late_events"] = copy.deepcopy(self._overlays.get(case_id, []))
        return case

    def inject_late_event(self, case_id: str, system: str, record: dict):
        self._base(case_id)  # existence check
        self._overlays.setdefault(case_id, []).append({"system": system, "record": record})

    def reset(self):
        self._overlays.clear()


# Allowlisted federated queries. Only these templates may be sent to Zetaris and only
# the named parameter (:case_key) is bound — no model-generated SQL is ever executed.
ZETARIS_QUERIES = {
    "hris": "SELECT * FROM hris_sim.employees WHERE case_key = :case_key",
    "crm": "SELECT * FROM crm_sim.records WHERE case_key = :case_key",
    "clm": "SELECT * FROM clm_sim.records WHERE case_key = :case_key",
    "billing": "SELECT * FROM billing_sim.records WHERE case_key = :case_key",
    "comp": "SELECT * FROM comp_sim.records WHERE case_key = :case_key",
    "payroll": "SELECT * FROM payroll_sim.records WHERE case_key = :case_key",
}


class ZetarisSource(LocalFixtureSource):
    """Federated source via Zetaris. Falls back to fixtures per system on error, and
    records which systems were actually served by Zetaris (`provenance`)."""

    name = "zetaris"

    def __init__(self, url: str, token: str | None):
        super().__init__()
        self.url = url.rstrip("/")
        self.token = token
        self.live = True

    def _query(self, system: str, case_id: str):
        body = json.dumps({"sql": ZETARIS_QUERIES[system], "params": {"case_key": case_id}}).encode()
        req = urllib.request.Request(self.url + "/query", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("unexpected Zetaris response shape")
        return rows

    def load_case(self, case_id: str) -> dict:
        case = super().load_case(case_id)
        provenance = {}
        for system in ZETARIS_QUERIES:
            try:
                rows = self._query(system, case_id)
                case["sources"][system]["records"] = rows
                provenance[system] = "zetaris"
            except Exception as exc:  # honest per-system fallback
                provenance[system] = f"fixture-fallback ({type(exc).__name__})"
        case["provenance"] = provenance
        return case


def make_source():
    url = os.environ.get("ZETARIS_URL")
    if url:
        return ZetarisSource(url, os.environ.get("ZETARIS_TOKEN"))
    return LocalFixtureSource()
