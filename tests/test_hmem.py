"""H-MEM: one-to-one Python port of the official conformance runner over the official vectors,
plus PayProof precedent-memory behaviour (verified-only writes, no self-retrieval)."""
import json
import unittest
from pathlib import Path

from payproof.hmem import DAY_MS, HMEM, PrecedentMemory, case_patterns

V = json.loads((Path(__file__).parent / "vectors" / "hmem_conformance_vectors.json").read_text())
T0 = V["clock"]
S = V["sections"]


class ConformancePort(unittest.TestCase):
    def test_record_validation(self):
        for c in S["record-validation"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                try:
                    h.add(c["input"]["content"], c["input"]["source"])
                    rejected = False
                except ValueError:
                    rejected = True
                self.assertEqual(rejected, c["expect"] == "reject")

    def test_feedback_deltas(self):
        for c in S["feedback-deltas"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                m = h.add("feedback target record", "conformance", confidence=c["start"])
                before = m["accessCount"]
                h.feedback(m["id"], c["kind"])
                after = h.store.get(m["id"])
                self.assertAlmostEqual(after["confidence"], c["expectConfidence"], places=9)
                if "expectAccessDelta" in c:
                    self.assertEqual(after["accessCount"] - before, c["expectAccessDelta"])
                if c.get("expectTag"):
                    self.assertIn(c["expectTag"], after["tags"])

    def test_ranking_order(self):
        for c in S["ranking-order"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                by = {r["key"]: h.add(r["content"], "conformance", confidence=r["confidence"], layer=r["layer"]) for r in c["records"]}
                for r in c["records"]:
                    if r.get("supersededByKey"):
                        by[r["key"]]["supersededBy"] = by[r["supersededByKey"]]["id"]
                order = [x["memory"]["id"] for x in h.query(c["query"], threshold=0, top_n=10)["memories"]]
                exp = [by[k]["id"] for k in c["expectOrder"]]
                for a, b in zip(exp, exp[1:]):
                    self.assertLess(order.index(a), order.index(b))

    def test_sleep_guardrails(self):
        for c in S["sleep-guardrails"]:
            with self.subTest(c["id"]):
                now = [T0]
                h = HMEM(clock=lambda: now[0])
                by = {r["key"]: h.add(r["content"], r["source"], derived_from=r.get("derivedFrom")) for r in c["records"]}
                now[0] = T0 + c["ageDays"] * DAY_MS
                before = sorted(m["id"] for m in h.store.all())
                preview = h.sleep.preview()
                self.assertEqual(sorted(m["id"] for m in h.store.all()), before, "preview mutated the store")
                for k in c["expectArchived"]:
                    self.assertIn(by[k]["id"], preview["toArchive"])
                for k in c["expectProtected"]:
                    self.assertNotIn(by[k]["id"], preview["toArchive"])
                report = h.sleep.execute(preview)
                for k in c["expectProtected"]:
                    self.assertIsNotNone(h.store.get(by[k]["id"]))
                self.assertTrue(report["backupId"])

    def test_conflict_gate(self):
        for c in S["conflict-gate"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                a = h.add(c["a"]["content"], "conformance", confidence=c["a"]["confidence"])
                b = h.add(c["b"]["content"], "conformance", confidence=c["b"]["confidence"])
                found = h.conflicts.scan()
                self.assertTrue(found)
                outcome = h.conflicts.auto_resolve(found[0])
                self.assertIn(outcome, ("resolved", "queued"))
                if outcome == "resolved":
                    self.assertTrue(any(h.store.get(x["id"]).get("supersededBy") for x in (a, b)))
                self.assertTrue(h.store.get(a["id"]) and h.store.get(b["id"]))

    def test_ledger_audit(self):
        for c in S["ledger-audit"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                m = h.add("audited record", "conformance", confidence=c["start"])
                h.feedback(m["id"], c["kind"])
                hist = h.ledger.history(m["id"])
                self.assertEqual([e["action"] for e in hist], c["expectActions"])
                self.assertAlmostEqual(hist[-1]["previousState"]["confidence"], c["expectPrev"], places=9)
                self.assertAlmostEqual(hist[-1]["newState"]["confidence"], c["expectNew"], places=9)

    def test_dream_boundary(self):
        for c in S["dream-boundary"]:
            with self.subTest(c["id"]):
                h = HMEM(clock=lambda: T0)
                for r in c["records"]:
                    h.add(r["content"], "conformance", type=r["type"])
                count = len(h.store.all())
                proposals = h.dreaming.dream()
                self.assertTrue(proposals)
                self.assertEqual(len(h.store.all()), count)
                created = h.dreaming.approve(proposals[0]["id"])
                if created:
                    self.assertEqual(created["layer"], "long_term")
                    self.assertTrue(created["derived_from"] if "derived_from" in created else created["derivedFrom"])


class PrecedentTests(unittest.TestCase):
    def _settle(self, case_id):
        from payproof.actions import ActionService
        from payproof.sources import LocalFixtureSource, load_plans
        svc = ActionService(LocalFixtureSource(user_dir=None), load_plans(), audit_path=None)
        inv = svc.investigate(case_id, use_model=False)
        a = svc.propose(case_id, "ana")
        svc.decide(a["id"], "ctl" if a["required_permission"] == "controller" else "fin", True)
        svc.execute(a["id"], "ops", a["idempotency_key"])
        return inv, a

    def test_only_verified_outcomes_are_written_and_self_retrieval_is_excluded(self):
        pm = PrecedentMemory(clock=lambda: T0)
        inv, act = self._settle("CASE-1001")
        unverified = {**act, "state": "APPROVED"}
        self.assertIsNone(pm.record_verified(inv, unverified))
        rec = pm.record_verified(inv, act)
        self.assertIsNotNone(rec)
        self.assertIn(act["receipt"]["receipt_id"], rec["provenance"]["refs"])
        self.assertIs(pm.record_verified(inv, act), rec)  # idempotent
        self.assertEqual(pm.recall(inv)["precedents"], [])  # never its own precedent
        from payproof.sources import LocalFixtureSource, load_plans
        from payproof.workflow import investigate
        other = investigate(LocalFixtureSource(user_dir=None).load_case("CASE-1022"), load_plans())  # duplicate line
        got = pm.recall(other)["precedents"]
        self.assertTrue(got and got[0]["case_id"] == "CASE-1001")
        self.assertIn("SK-DUP", got[0]["shared_patterns"])
        self.assertIn("SK-DUP", case_patterns(other))


if __name__ == "__main__":
    unittest.main()
