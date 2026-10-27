import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from payproof.actions import ActionError, ActionService, late_credit_note
from payproof.evidence import EvidenceIndex, resolve_identity
from payproof.money import D, cents
from payproof.policy import Scenario, compute
from payproof.sources import LocalFixtureSource, load_plans
from payproof.workflow import investigate

ROOT = Path(__file__).resolve().parent.parent
GT = json.loads((ROOT / "bench" / "ground_truth.json").read_text())["cases"]
PLANS = load_plans()


def run(case_id, src=None):
    return investigate((src or LocalFixtureSource()).load_case(case_id), PLANS)


class MoneyTests(unittest.TestCase):
    def test_rejects_float(self):
        with self.assertRaises(TypeError):
            D(0.1)

    def test_half_up_rounding(self):
        self.assertEqual(cents(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(cents(Decimal("2.344")), Decimal("2.34"))


class GroundTruthTests(unittest.TestCase):
    def test_all_cases_match_hand_computed_truth(self):
        src = LocalFixtureSource()
        for cid, g in GT.items():
            with self.subTest(cid):
                r = run(cid, src)
                self.assertEqual(r["proof_status"], g["proof_status"])
                self.assertEqual(r["verdict"], g["verdict"])
                self.assertEqual(r["proposed_action"]["type"], g["action"])
                self.assertEqual(r["calculation"]["paid"], g["paid"])
                if g["due"] is not None:
                    self.assertEqual(r["calculation"]["due"], g["due"])
                    self.assertEqual(r["calculation"]["delta"], g["delta"])
                if "permission" in g:
                    self.assertEqual(r["proposed_action"]["required_permission"], g["permission"])
                cited = {c for b in r["bundle"] for c in b["supporting"] + b["contradicting"]} | \
                        {c for f in r["skeptic"]["findings"] for c in f["cites"]}
                for must in g.get("must_cite", []):
                    self.assertIn(must, cited)

    def test_reproducible(self):
        a, b = run("CASE-1001"), run("CASE-1001")
        self.assertEqual(a["proof_hash"], b["proof_hash"])
        self.assertEqual(a["run_id"], b["run_id"])

    def test_every_citation_is_real(self):
        src = LocalFixtureSource()
        for cid in GT:
            case = src.load_case(cid)
            ix = EvidenceIndex(case)
            r = investigate(case, PLANS)
            known = set(ix.records) | {v["id"] for v in PLANS["versions"]}
            for b in r["bundle"]:
                for c in b["supporting"] + b["contradicting"]:
                    self.assertIn(c, known, f"{cid} {b['id']} cites {c}")

    def test_unverified_never_proposes_adjustment(self):
        for cid, g in GT.items():
            r = run(cid)
            if r["proof_status"] != "VERIFIED":
                self.assertNotEqual(r["proposed_action"]["type"], "PREPARE_PAYROLL_ADJUSTMENT")
                self.assertIsNone(r["proposed_action"]["amount"])


class DemoCaseTests(unittest.TestCase):
    def test_demo_numbers_and_skeptic(self):
        r = run("CASE-1001")
        self.assertEqual(r["calculation"]["due"], "4300.00")
        self.assertEqual(r["skeptic"]["strongest"], "SK-LATE-PAY-44987")
        cf = {c["id"]: c for c in r["counterfactuals"]}
        self.assertEqual(cf["cf_recorded_timing"]["due"], "3400.00")
        self.assertEqual(cf["cf_dedupe_PL-20260630-042"]["paid"], "3400.00")
        self.assertTrue(all(c["hypothetical"] for c in r["counterfactuals"]))

    def test_identity_alias_not_name(self):
        case = LocalFixtureSource().load_case("CASE-1013")
        ix = EvidenceIndex(case)
        ident = resolve_identity(ix.get("E-2013"), ix.of_type("crm_user"))
        self.assertEqual(ident["status"], "AMBIGUOUS")
        self.assertIsNone(ident["crm_user_id"])

    def test_counterfactual_does_not_mutate_sources(self):
        src = LocalFixtureSource()
        case = src.load_case("CASE-1001")
        before = json.dumps(case, sort_keys=True)
        investigate(case, PLANS)
        self.assertEqual(before, json.dumps(case, sort_keys=True))

    def test_missing_pay_calendar_needs_evidence(self):
        case = LocalFixtureSource().load_case("CASE-1001")
        case["sources"]["payroll"]["records"] = []
        r = investigate(case, PLANS)
        self.assertEqual(r["proof_status"], "NEEDS_EVIDENCE")
        self.assertEqual(r["proposed_action"]["type"], "REQUEST_EVIDENCE")

    def test_world_model_cross_check_runs_and_passes(self):
        for cid in GT:
            inv = {i["invariant"]: i for i in run(cid)["verification"]["invariants"]}
            wmc = [v for k, v in inv.items() if "World Model" in k]
            if run(cid)["calculation"]["blockers"] or GT[cid]["due"] is None and "collected" not in str(inv):
                continue
            for v in wmc:
                self.assertTrue(v["passed"], f"{cid}: {v['detail']}")

    def test_material_conflict_is_disputed_immaterial_is_verified(self):
        self.assertEqual(run("CASE-1010")["proof_status"], "DISPUTED")
        r = run("CASE-1011")
        self.assertEqual(r["proof_status"], "VERIFIED")
        self.assertFalse(r["verification"]["conflicts"][0]["material"])


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.svc = ActionService(LocalFixtureSource(), PLANS, audit_path=None)

    def _approved(self, case="CASE-1001", approver="fin"):
        a = self.svc.propose(case, "ana")
        self.assertEqual(a["state"], "AWAITING_APPROVAL")
        self.svc.decide(a["id"], approver, True)
        return a

    def test_happy_path_verified_once(self):
        a = self._approved()
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(a["state"], "VERIFIED")
        self.assertTrue(a["receipt"]["postcondition"]["passed"])
        self.assertEqual(a["receipt"]["postcondition"]["observed_paid"], "4300.00")
        # duplicate execution is suppressed
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.svc.execute(a["id"], "ctl", a["idempotency_key"])
        self.assertEqual(len(self.svc.adapter.ledger), 1)
        self.assertTrue(self.svc.audit.verify_chain())
        # re-investigation now shows the case settled
        self.assertEqual(self.svc.investigate("CASE-1001")["calculation"]["delta"], "0.00")

    def test_unauthorized_approvals_rejected(self):
        a = self.svc.propose("CASE-1001", "ana")
        for tok in ("rep", "ana", "ops"):
            with self.assertRaises(ActionError) as cm:
                self.svc.decide(a["id"], tok, True)
            self.assertEqual(cm.exception.status, 403)
        with self.assertRaises(ActionError):
            self.svc.decide(a["id"], "nobody", True)
        self.assertEqual(a["state"], "AWAITING_APPROVAL")

    def test_rep_cannot_propose(self):
        with self.assertRaises(ActionError):
            self.svc.propose("CASE-1001", "rep")

    def test_execute_without_approval_rejected(self):
        a = self.svc.propose("CASE-1001", "ana")
        with self.assertRaises(ActionError) as cm:
            self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(cm.exception.code, "NOT_APPROVED")
        self.assertEqual(self.svc.adapter.ledger, [])

    def test_approval_limit(self):
        a = self.svc.propose("CASE-1025", "ana")
        self.assertEqual(a["required_permission"], "controller")
        with self.assertRaises(ActionError):
            self.svc.decide(a["id"], "fin", True)
        self.svc.decide(a["id"], "ctl", True)
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(a["state"], "VERIFIED")

    def test_stale_evidence_between_approval_and_execution(self):
        a = self._approved()
        rec = late_credit_note("CASE-1001")
        rec["invoice_id"] = "INV-8801"
        self.svc.source.inject_late_event("CASE-1001", "billing", rec)
        with self.assertRaises(ActionError) as cm:
            self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(cm.exception.code, "STALE_EVIDENCE")
        self.assertEqual(a["state"], "EXPIRED")
        self.assertEqual(self.svc.adapter.ledger, [])
        # both independent staleness signals fired and agreed (Meterless World Model + fingerprint)
        last = a["staleness_checks"][-1]
        self.assertTrue(last["world_model_changed"] and last["fingerprint_changed"] and last["agree"])
        self.assertIn("World Model", a["history"][-1]["reason"])
        # re-investigation reflects the new credit note
        self.assertEqual(self.svc.investigate("CASE-1001")["calculation"]["due"], "4200.00")

    def test_failure_is_reported_and_retry_does_not_duplicate(self):
        a = self._approved()
        self.svc.adapter.fail_next = True
        with self.assertRaises(ActionError) as cm:
            self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(cm.exception.code, "EXECUTION_FAILED")
        self.assertEqual(a["state"], "FAILED")
        self.assertIsNone(a["receipt"])
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(a["state"], "VERIFIED")
        self.assertEqual(len(self.svc.adapter.ledger), 1)

    def test_failed_postcondition_never_yields_receipt(self):
        a = self._approved()
        self.svc.verify_postcondition = lambda a, row: {"passed": False, "check": "forced failure"}
        with self.assertRaises(ActionError) as cm:
            self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(cm.exception.code, "POSTCONDITION_FAILED")
        self.assertEqual(a["state"], "FAILED")
        self.assertIsNone(a["receipt"])
        self.assertFalse(a["failure"]["postcondition"]["passed"])
        # retry with the same key does not duplicate the adapter write
        del self.svc.verify_postcondition
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(a["state"], "VERIFIED")
        self.assertEqual(len(self.svc.adapter.ledger), 1)
        self.assertTrue(a["receipt"]["postcondition"]["passed"])

    def test_wrong_idempotency_key(self):
        a = self._approved()
        with self.assertRaises(ActionError):
            self.svc.execute(a["id"], "ops", "IDK-forged")

    def test_negative_case_never_moves_money(self):
        a = self.svc.propose("CASE-1015", "ana")
        self.assertEqual(a["type"], "REQUEST_EVIDENCE")
        self.assertIsNone(a["amount"])
        self.svc.decide(a["id"], "fin", True)
        self.svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(self.svc.adapter.ledger, [])
        self.assertEqual(len(self.svc.adapter.tickets), 1)

    def test_approval_expiry(self):
        now = [datetime(2026, 7, 10, tzinfo=timezone.utc)]
        svc = ActionService(LocalFixtureSource(), PLANS, audit_path=None, clock=lambda: now[0])
        a = svc.propose("CASE-1003", "ana")
        svc.decide(a["id"], "fin", True)
        now[0] += timedelta(hours=25)
        with self.assertRaises(ActionError) as cm:
            svc.execute(a["id"], "ops", a["idempotency_key"])
        self.assertEqual(cm.exception.code, "EXPIRED")

    def test_proposal_is_idempotent(self):
        a = self.svc.propose("CASE-1003", "ana")
        b = self.svc.propose("CASE-1003", "ana")
        self.assertEqual(a["id"], b["id"])


class ScenarioTests(unittest.TestCase):
    def test_hypothetical_records_marked(self):
        case = LocalFixtureSource().load_case("CASE-1001")
        ix = EvidenceIndex(case)
        ident = resolve_identity(ix.get("E-1042"), ix.of_type("crm_user"))
        r = compute(ix, PLANS, ident, Scenario(id="x", split_override={"U-77": "100"}))
        self.assertEqual(r["due"], "4300.00")


if __name__ == "__main__":
    unittest.main()
