"""Export the synthetic source snapshots as one CSV per source system for Zetaris.

Output: data/zetaris/<system>_records.csv with columns
    case_key, record_id, record_type, effective_at, recorded_at, payload_json
payload_json is the original record, unmodified, so ZetarisSource can map rows back
into the evidence model with record ids and provenance intact.

Run: python3 scripts/export_zetaris_csv.py   then follow docs/zetaris/register.sql
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "zetaris"
SYSTEMS = ("hris", "crm", "clm", "billing", "comp", "payroll")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    writers, files, counts = {}, {}, {}
    for system in SYSTEMS:
        files[system] = (OUT / f"{system}_records.csv").open("w", newline="")
        writers[system] = csv.writer(files[system], quoting=csv.QUOTE_ALL)
        writers[system].writerow(["case_key", "record_id", "record_type", "effective_at", "recorded_at", "payload_json"])
        counts[system] = 0
    for path in sorted((ROOT / "data" / "cases").glob("CASE-*.json")):
        case = json.loads(path.read_text())
        for system in SYSTEMS:
            for rec in case["sources"][system]["records"]:
                writers[system].writerow([case["case_id"], rec["id"], rec["type"], rec.get("effective_at", ""),
                                          rec.get("recorded_at", ""), json.dumps(rec, sort_keys=True)])
                counts[system] += 1
    for f in files.values():
        f.close()
    print("wrote", ", ".join(f"{s}={n}" for s, n in counts.items()), "rows to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
