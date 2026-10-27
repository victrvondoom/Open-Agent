"""Build the consumer-dispute demo fixtures and the frozen benchmark splits.

    python scripts/build_consumer_fixtures.py            # writes data/consumer/ and bench/consumer/
    python scripts/build_consumer_fixtures.py --check    # verify the committed manifest (no writes)

Demo: curated cases (data/consumer/cases/) + a shared fixture lake of institution records
(data/consumer/lake/), including bookings nobody has disputed yet so intake can file new claims.
Benchmark: dev / holdout / adversarial splits from separate seeds and date windows, each with
oracle ground truth and a SHA-256 manifest so a frozen split cannot change silently.
"""

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from payproof.consumer_cases import IST, LABELS, build, generate, manifest_hash  # noqa: E402

DEMO = [("valid_full", "north"), ("credit_shell_forced", "north"), ("notice_conflict", "north"),
        ("refund_already_received", "north"), ("extraordinary_corroborated", "north"), ("injection_document", "north"),
        ("fabricated_citation", "north"), ("airline_refund_unconfirmed", "north"), ("valid_refund_only", "south"),
        ("missing_booking", "north")]
UNFILED = ["valid_full", "partial_refund"]
ADVERSARIAL = ["injection_document", "injection_record", "fabricated_citation", "agent_wrong_amount", "notice_conflict",
               "payment_mismatch", "airline_refund_unconfirmed", "extraordinary_uncorroborated", "identity_ambiguous",
               "identity_mismatch", "stale_feed", "source_unavailable", "domain_mismatch", "refund_in_transit"]
SPLITS = {  # name: (labels, seed, first case number, departure window start)
    "dev": (sorted(LABELS) * 2, 11, 5001, datetime(2026, 9, 1, tzinfo=IST)),
    "holdout": (sorted(LABELS) * 3, 9029, 6001, datetime(2026, 5, 1, tzinfo=IST)),
    "adversarial": (ADVERSARIAL * 4, 4242, 7001, datetime(2026, 7, 1, tzinfo=IST)),
}
CLOCK = "2026-10-26T12:00:00Z"  # fixture clock: runtime-filed demo claims are evaluated as of this instant


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_demo():
    rng = random.Random(2026)
    lake = {s: [] for s in ("airline_pss", "flight_ops", "payments", "airport_ops")}
    cases_dir = ROOT / "data" / "consumer" / "cases"
    for f in cases_dir.glob("CDX-*.json") if cases_dir.exists() else []:
        f.unlink()
    for i, (label, tenant) in enumerate(DEMO):
        b = build(f"CDX-{3001 + i:04d}", label, rng, tenant)
        b["case"]["tags"] = ["demo"] + b["case"]["tags"]
        dump(cases_dir / f"{b['case']['case_id']}.json", b["case"])
        for s, recs in b["records"].items():
            lake[s] += recs
    unfiled = []
    for i, label in enumerate(UNFILED):  # institution records exist; no claim filed yet
        b = build(f"CDX-{3901 + i:04d}", label, rng, "north", datetime(2026, 9, 20, tzinfo=IST))
        for s, recs in b["records"].items():
            lake[s] += recs
        bk = b["records"]["airline_pss"][0]
        unfiled.append({"booking_ref": bk["booking_ref"], "passenger_name": bk["passenger_name"].title(), "flight_no": bk["flight_no"],
                        "carrier": bk["carrier"], "route": f"{bk['origin']}-{bk['destination']}",
                        "scheduled_departure": bk["scheduled_departure"], "total_paid": bk["total_paid"]})
    lake_dir = ROOT / "data" / "consumer" / "lake"
    for s, recs in lake.items():
        dump(lake_dir / f"{s}.json", sorted(recs, key=lambda r: r["id"]))
    clock = datetime.fromisoformat(CLOCK.replace("Z", "+00:00"))
    feeds = {s: {"as_of": (clock - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")} for s in lake}
    dump(lake_dir / "_feeds.json", {**feeds, "_clock": CLOCK,
                                    "_note": "Local fixture snapshot. Runtime-filed claims are evaluated as of _clock."})
    dump(lake_dir / "_unfiled_bookings.json", unfiled)
    return len(DEMO), sum(len(v) for v in lake.values())


def build_splits():
    manifest = {"generator": "payproof.consumer_cases", "oracle": "payproof.consumer_cases.oracle (independent of reclaim_policy)",
                "splits": {}}
    for name, (labels, seed, start, base) in SPLITS.items():
        cases = generate(labels, seed, start, ("north", "south"), base)
        rows = [{"label": c["params"]["label"], "category": c["category"], "case": c["case"], "records": c["records"], "truth": c["truth"]}
                for c in cases]
        dump(ROOT / "bench" / "consumer" / f"{name}.json", rows)
        manifest["splits"][name] = {"seed": seed, "first_case": f"CDX-{start:04d}", "cases": len(rows),
                                    "departure_window_start": base.isoformat(), "sha256": manifest_hash(cases),
                                    "labels": sorted(set(labels))}
    manifest["leakage_controls"] = [
        "holdout and adversarial use seeds and date windows never used during development (dev seed 11)",
        "ground truth comes from the scenario oracle, not from the engine under test",
        "the engine never reads bench/ files; the harness verifies split hashes before scoring",
        "caveat: all splits share scenario families designed by the same team, so the holdout guards against "
        "instance overfitting, not against blind spots in the scenario design itself"]
    return manifest


def main():
    if "--check" in sys.argv:
        manifest = json.loads((ROOT / "bench" / "consumer" / "manifest.json").read_text(encoding="utf-8"))
        bad = [name for name, (labels, seed, start, base) in SPLITS.items()
               if manifest_hash(generate(labels, seed, start, ("north", "south"), base)) != manifest["splits"][name]["sha256"]]
        print("manifest OK" if not bad else f"manifest MISMATCH: {bad}")
        return 1 if bad else 0
    n_demo, n_rec = build_demo()
    manifest = build_splits()
    dump(ROOT / "bench" / "consumer" / "manifest.json", manifest)
    print(f"demo cases: {n_demo}; lake records: {n_rec}")
    for k, v in manifest["splits"].items():
        print(f"{k}: {v['cases']} cases, seed {v['seed']}, sha256 {v['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
