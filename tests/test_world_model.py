"""World Model engine tests.

ConformancePortTests is a one-to-one Python port of the 8 checks in the official
Meterless suite (Meterless/Meterless engines/world-model/conformance/runner.ts, Apache-2.0).
It is a port, not the official runner; see docs/INTEGRATIONS.md for running the runner itself.
"""

import json
import unittest

from payproof.sources import LocalFixtureSource
from payproof.world_model import (ProvenanceError, WorldModel, context_for, decide, entity_id_from_name,
                                  ingest_case, normalize_name)

OBSERVATIONS = [
    {"externalId": "a1", "title": "Fed holds rates", "at": "2026-05-17T14:00:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T14:00:00.000Z"}, "entities": [{"type": "person", "name": "Jerome Powell"}]},
    {"externalId": "a2", "title": "Powell signals patience", "at": "2026-05-17T16:30:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T16:30:00.000Z"}, "entities": [{"type": "person", "name": "Jerome Powell"}]},
]


def at(s):
    return {"kind": "manual", "at": s}


class ConformancePortTests(unittest.TestCase):
    def test_sid_001_diacritics_and_nbsp_normalize_identically(self):
        self.assertEqual(normalize_name("José  García"), normalize_name("Jose Garcia"))
        self.assertEqual(entity_id_from_name("person", "José García"), entity_id_from_name("person", "jose garcia"))

    def test_sid_002_distinct_names_stay_distinct(self):
        self.assertNotEqual(entity_id_from_name("org", "Acme Corp"), entity_id_from_name("org", "Acme Corporation"))
        self.assertNotEqual(entity_id_from_name("person", "x"), entity_id_from_name("org", "x"))

    def test_band_001_merge_bands_at_boundaries(self):
        self.assertEqual(decide(0.85), "auto-merge")
        self.assertEqual(decide(0.84), "review")
        self.assertEqual(decide(0.82), "review")
        self.assertEqual(decide(0.81), "new")

    def test_prov_001_writes_without_provenance_rejected(self):
        w = WorldModel("conf")
        with self.assertRaises(ProvenanceError):
            w.upsert_entity(type="person", name="No Provenance", source=None)

    def test_idem_001_same_batch_twice_empty_diff(self):
        w = WorldModel("conf")
        w.ingest(OBSERVATIONS)
        shape1 = w.state_shape_canonical()
        second = w.ingest(OBSERVATIONS)
        self.assertFalse(second["changed"])
        self.assertEqual(w.state_shape_canonical(), shape1)

    def test_idem_002_mutated_batch_changes_shape(self):
        w = WorldModel("conf")
        w.ingest(OBSERVATIONS)
        shape1 = w.state_shape_canonical()
        mutated = [{**OBSERVATIONS[0], "title": OBSERVATIONS[0]["title"] + " (edited)"}, OBSERVATIONS[1]]
        run = w.ingest(mutated)
        self.assertTrue(run["changed"])
        self.assertNotEqual(w.state_shape_canonical(), shape1)

    def test_bitemp_001_superseding_edge_and_point_in_time(self):
        w = WorldModel("conf")
        w.upsert_entity(type="player", external_key={"system": "g", "id": "p1"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
        w.upsert_entity(type="team", external_key={"system": "g", "id": "a"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
        w.upsert_entity(type="team", external_key={"system": "g", "id": "b"}, attrs={}, source=at("2088-03-01T00:00:00.000Z"))
        w.relate("player:g:p1", "plays-for", "team:g:a", valid_from="2087-01-01T00:00:00.000Z", source=at("2087-01-01T00:00:00.000Z"))
        w.relate("player:g:p1", "plays-for", "team:g:b", valid_from="2088-03-01T00:00:00.000Z", source=at("2088-03-01T00:00:00.000Z"))
        now = w.neighbors_of("player:g:p1", via="plays-for")
        self.assertEqual([e["id"] for e in now], ["team:g:b"])
        then = w.neighbors_of("player:g:p1", via="plays-for", at="2087-06-01T00:00:00.000Z")
        self.assertEqual([e["id"] for e in then], ["team:g:a"])

    def test_audit_001_every_mutation_audited_in_order(self):
        w = WorldModel("conf")
        w.upsert_entity(type="x", name="Audit One", source=at("2026-01-01T00:00:00.000Z"))
        w.upsert_entity(type="x", name="Audit Two", source=at("2026-01-02T00:00:00.000Z"))
        audit = w.audit()
        self.assertGreaterEqual(len(audit), 2)
        for i in range(1, len(audit)):
            self.assertGreater(audit[i]["seq"], audit[i - 1]["seq"])


class PayProofWorldModelTests(unittest.TestCase):
    def test_case_ingest_is_idempotent_and_detects_late_events(self):
        src = LocalFixtureSource()
        w = WorldModel("CASE-1001")
        first = ingest_case(w, src.load_case("CASE-1001"))
        self.assertTrue(first["changed"])
        again = ingest_case(w, src.load_case("CASE-1001"))
        self.assertFalse(again["changed"])
        self.assertEqual(again["state_hash"], first["state_hash"])
        src.inject_late_event("CASE-1001", "billing", {"id": "CN-LATE", "type": "credit_note", "invoice_id": "INV-8801",
                                                        "amount": "1000.00", "issued_date": "2026-06-25",
                                                        "effective_at": "2026-06-25", "recorded_at": "2026-07-20T09:00:00Z"})
        late = ingest_case(w, src.load_case("CASE-1001"))
        self.assertTrue(late["changed"])
        self.assertEqual(late["processed"], 1)

    def test_provenance_and_bitemporal_edges(self):
        w = WorldModel("CASE-1001")
        ingest_case(w, LocalFixtureSource().load_case("CASE-1001"))
        pay = w.entities["payment:billing:PAY-44987"]
        self.assertEqual(pay["source"]["kind"], "billing-sim (NetSuite-like)")
        self.assertEqual(pay["source"]["at"], "2026-07-03T12:00:00Z")  # recorded time
        edge = next(r for r in w.relationships.values() if r["from"] == "payment:billing:PAY-44987")
        self.assertEqual(edge["validFrom"], "2026-06-10T00:00:00.000Z")  # effective time
        # as of the cutoff the late-recorded payment is a valid edge on the invoice
        on_invoice = w.neighbors_of("invoice:billing:INV-8801", via="pays", at="2026-06-30T23:59:59.000Z")
        self.assertIn("payment:billing:PAY-44987", [e["id"] for e in on_invoice])

    def test_context_builder_is_grounded(self):
        w = WorldModel("CASE-1001")
        rep = ingest_case(w, LocalFixtureSource().load_case("CASE-1001"))
        ctx = context_for(w, rep["ids"]["OPP-5521"])
        ids = {c["id"] for c in ctx}
        self.assertTrue({"CTR-3301", "SPL-5521-1", "U-77"} <= ids)
        self.assertTrue(all(c["source"] for c in ctx))
        json.dumps(ctx)


if __name__ == "__main__":
    unittest.main()
