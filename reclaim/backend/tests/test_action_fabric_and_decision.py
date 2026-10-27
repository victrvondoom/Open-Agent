from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.connectors.approval_gate import approval_gate
from app.services.connectors.models import ApprovalState, ExecutionMode
from app.services.connectors.registry import connector_registry
from app.services.decision_engine import CandidateAction, OptimizationWeights, decision_engine


@pytest.fixture
def client():
    return TestClient(app)


def test_connector_discovery(client):
    res = client.get("/api/v1/connectors")
    assert res.status_code == 200
    manifests = res.json()
    assert len(manifests) >= 1
    aviation = next((m for m in manifests if m["connector_id"] == "reclaim.connectors.aviation_refund"), None)
    assert aviation is not None
    assert aviation["domain"] == "airlines"
    action_ids = [c["action_id"] for c in aviation["capabilities"]]
    assert "check_statutory_eligibility" in action_ids
    assert "submit_airline_claim" in action_ids


def test_connector_health(client):
    res = client.get("/api/v1/connectors/health")
    assert res.status_code == 200
    statuses = res.json()
    assert len(statuses) >= 1
    assert statuses[0]["healthy"] is True


def test_aviation_refund_flow_with_approval_gate(client, jwt_auth, owned_case, isolated_stores):
    import uuid
    run_id = uuid.uuid4().hex[:8]
    # Case-scoped connector routes require an authenticated owner of the case.
    headers = jwt_auth(f"user-{run_id}")
    case_id = owned_case(f"user-{run_id}")

    # 1. Evaluate eligibility (Read-only, no approval needed)
    prep_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/prepare",
        headers=headers,
        json={
            "action_id": "check_statutory_eligibility",
            "case_id": case_id,
            "payload": {
                "airline": "IndiGo",
                "flight_number": "6E-204",
                "cancellation_notice_hours": 12,
                "ticket_amount": 7500,
                "jurisdiction": "IN",
            },
            "execution_mode": "sandbox",
        },
    )
    assert prep_res.status_code == 200
    prepared = prep_res.json()
    assert prepared["requires_human_approval"] is False
    assert prepared["approval_state"] == ApprovalState.NOT_REQUIRED.value

    # Execute read-only action without token
    exec_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/execute",
        headers=headers,
        json={
            "prepared_action": prepared,
            "idempotency_key": f"idemp-elig-{run_id}",
        },
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["state"] == "completed"
    assert exec_data["output_data"]["eligible"] is True
    assert exec_data["output_data"]["refund_amount"] == 7500

    # 2. Prepare consequential action: submit_airline_claim (requires explicit approval)
    prep_claim_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/prepare",
        headers=headers,
        json={
            "action_id": "submit_airline_claim",
            "case_id": case_id,
            "payload": {
                "pnr": f"PNR{run_id.upper()}",
                "passenger_email": "passenger@example.com",
                "airline": "IndiGo",
                "claim_package": {
                    "statutory_basis": "DGCA CAR Series M Part IV",
                    "claimed_amount": 17500,
                },
            },
            "execution_mode": "sandbox",
        },
    )
    assert prep_claim_res.status_code == 200
    prep_claim = prep_claim_res.json()
    assert prep_claim["requires_human_approval"] is True
    assert prep_claim["approval_state"] == ApprovalState.PENDING_APPROVAL.value

    # Attempting to execute WITHOUT approval token must fail with 403 Forbidden!
    blocked_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/execute",
        headers=headers,
        json={
            "prepared_action": prep_claim,
            "idempotency_key": f"idemp-claim-{run_id}",
        },
    )
    assert blocked_res.status_code == 403
    assert "Approval Gate" in blocked_res.json()["detail"]

    # 3. Grant explicit human approval
    appr_res = client.post(
        "/api/v1/connectors/approve",
        headers=headers,
        json={
            "prepared_action": prep_claim,
            "user_id": f"user-{run_id}",
            "consent_statement": "I explicitly authorize filing this statutory refund claim under DGCA guidelines.",
        },
    )
    assert appr_res.status_code == 200
    token = appr_res.json()["approval_token"]
    assert token is not None

    # Update prepared action with the token and execute
    prep_claim["approval_state"] = ApprovalState.APPROVED.value
    prep_claim["approval_token"] = token

    exec_claim_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/execute",
        headers=headers,
        json={
            "prepared_action": prep_claim,
            "idempotency_key": f"idemp-claim-{run_id}",
            "approval_token": token,
        },
    )
    assert exec_claim_res.status_code == 200
    claim_outcome = exec_claim_res.json()
    assert claim_outcome["state"] == "completed"
    assert claim_outcome["output_data"]["status"] == "DISPATCHED_TO_CARRIER"
    assert "carrier_claim_id" in claim_outcome["output_data"]

    # Replay attack prevention: token should now be consumed
    replay_res = client.post(
        "/api/v1/connectors/reclaim.connectors.aviation_refund/execute",
        headers=headers,
        json={
            "prepared_action": prep_claim,
            "idempotency_key": f"idemp-claim-replay-{run_id}",
            "approval_token": token,
        },
    )
    assert replay_res.status_code == 403
    assert "consumed" in replay_res.json()["detail"]



def test_decision_engine_optimization_and_constraints(client, jwt_auth, owned_case, isolated_stores):
    # /decision/optimize reads the case and writes its timeline: owner only.
    res = client.post(
        "/api/v1/decision/optimize",
        headers=jwt_auth("user-decision"),
        json={
            "case_id": owned_case("user-decision"),
            "available_evidence": ["booking_pnr", "cancellation_sms_or_email"],
            "days_since_incident": 4,
            "weights": {
                "w_benefit": 0.40,
                "w_cost": 0.20,
                "w_delay": 0.20,
                "w_risk": 0.10,
                "w_privacy": 0.10,
            },
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["optimal_action_key"] == "direct_carrier_claim"
    assert len(data["ranked_actions"]) == 3
    # Check that the direct claim ranks highest due to speed and minimal friction
    top = data["ranked_actions"][0]
    assert top["action_key"] == "direct_carrier_claim"
    assert top["eligible"] is True
    assert top["utility_score"] > 0


def test_split_endpoint(client):
    res = client.post(
        "/api/v1/split",
        json={
            "text": "DGCA CAR Series M Part IV Section 3.2 specifies passenger compensation.\n\nRefund must be given in 7 days.",
            "max_chunk_size": 150,
            "overlap": 15,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_chunks"] >= 1
    assert data["max_chunk_measured"] <= 150
    assert any("Section 3.2" in c["text"] for c in data["chunks"])


def test_email_complaint_connector_and_outbox(client, jwt_auth, owned_case, isolated_stores):
    headers = jwt_auth("user-irda-claimant")
    case_id = owned_case("user-irda-claimant")

    # 1. Prepare complaint email
    prep_res = client.post(
        "/api/v1/connectors/reclaim.connectors.email_delivery/prepare",
        headers=headers,
        json={
            "action_id": "send_complaint_email",
            "case_id": case_id,
            "payload": {
                "recipient_email": "nodal.officer@starhealth.in",
                "subject": "Statutory Appeal Under IRDAI Master Circular 2024",
                "body": "Formal legal complaint regarding arbitrary denial of cataract surgery claim.",
                "case_id": case_id,
            },
            "execution_mode": "sandbox",
        },
    )
    assert prep_res.status_code == 200
    prepared = prep_res.json()
    assert prepared["requires_human_approval"] is True

    # 2. Issue human approval token
    appr_res = client.post(
        "/api/v1/connectors/approve",
        headers=headers,
        json={
            "prepared_action": prepared,
            "user_id": "user-irda-claimant",
            "consent_statement": "I explicitly review and authorize dispatching this legal complaint to Star Health.",
        },
    )
    assert appr_res.status_code == 200
    token = appr_res.json()["approval_token"]

    # 3. Execute email complaint in sandbox mode
    exec_res = client.post(
        "/api/v1/connectors/reclaim.connectors.email_delivery/execute",
        headers=headers,
        json={
            "prepared_action": prepared,
            "idempotency_key": "idemp-email-dispute-01",
            "approval_token": token,
        },
    )
    assert exec_res.status_code == 200
    out = exec_res.json()
    assert out["state"] == "completed"
    assert "OUTBOX" in out["provider_reference"] or "MSG" in out["provider_reference"]
    assert out["output_data"]["recipient"] == "nodal.officer@starhealth.in"

    # 4. Check case operations listing endpoint
    ops_res = client.get(f"/api/v1/connectors/cases/{case_id}/operations", headers=headers)
    assert ops_res.status_code == 200
    case_ops = ops_res.json()
    assert len(case_ops) >= 1
    assert case_ops[0]["case_id"] == case_id

