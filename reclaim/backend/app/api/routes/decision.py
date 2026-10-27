from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, get_current_user
from app.database.postgres.repositories import case_repository
from app.services.decision_engine import (
    CandidateAction,
    DecisionRankingResponse,
    OptimizationWeights,
    decision_engine,
)

router = APIRouter()


class OptimizeDecisionRequest(BaseModel):
    case_id: str
    candidates: list[CandidateAction] = Field(default_factory=list)
    available_evidence: list[str] = Field(default_factory=list)
    days_since_incident: int = 5
    weights: OptimizationWeights | None = None


@router.post("/optimize", response_model=DecisionRankingResponse)
async def optimize_decision_path(
    req: OptimizeDecisionRequest,
    user: CurrentUser = Depends(get_current_user),
) -> DecisionRankingResponse:
    """Evaluate candidate dispute actions and rank optimal escalation path using multi-objective utility.

    Directly inspects real case facts, evidence artifacts, and records the optimization event to the case timeline.
    Only the case owner may do so: its documents are read and its timeline written.
    """
    case = await case_repository.get_case(req.case_id, user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or access denied")
    documents = await case_repository.list_documents(req.case_id) if req.case_id else []

    # Detect available evidence from real attached case documents if not explicitly passed
    detected_evidence = list(req.available_evidence)
    if not detected_evidence:
        for doc in documents:
            fname = (doc.get("filename") or "").lower()
            dtype = (doc.get("document_type") or "").lower()
            text = (doc.get("text_extract") or doc.get("text_preview") or "").lower()

            if any(k in fname or k in dtype or k in text for k in ["pnr", "ticket", "boarding", "booking"]):
                detected_evidence.extend(["booking_pnr", "carrier_ticket_number"])
            if any(k in fname or k in dtype or k in text for k in ["reject", "denial", "cancellation", "delay"]):
                detected_evidence.extend(["cancellation_sms_or_email", "airline_rejection_proof"])
            if any(k in fname or k in dtype or k in text for k in ["legal", "notice", "advocate"]):
                detected_evidence.append("formal_legal_notice")
            if any(k in fname or k in dtype or k in text for k in ["invoice", "bill", "receipt"]):
                detected_evidence.append("payment_receipt")

    if not detected_evidence:
        # Default minimum verifiable baseline
        detected_evidence = ["booking_pnr", "cancellation_sms_or_email"]

    detected_evidence = sorted(list(set(detected_evidence)))

    # Formulate domain-grounded candidate actions if none provided
    candidates = req.candidates
    if not candidates:
        domain_name = case.get("domain") if case else "airlines"
        domain_str = domain_name.value if hasattr(domain_name, "value") else str(domain_name)
        institution = case.get("institution_name", "Service Provider") if case else "Airlines"

        candidates = [
            CandidateAction(
                action_key="direct_carrier_claim",
                name=f"Direct Dispute & Demand Notice ({institution})",
                stage="direct",
                expected_benefit_inr=15000.0,
                expected_cost_inr=0.0,
                expected_delay_days=7.0,
                risk_level=0.10,
                privacy_exposure=0.05,
                reversibility=False,
                prerequisite_evidence=["booking_pnr", "cancellation_sms_or_email"],
                statutory_deadline_days=30,
            ),
            CandidateAction(
                action_key="statutory_escalation",
                name="Statutory Regulatory Grievance (Nodal / Ombudsman Escalation)",
                stage="escalation",
                expected_benefit_inr=15000.0,
                expected_cost_inr=0.0,
                expected_delay_days=14.0,
                risk_level=0.20,
                privacy_exposure=0.20,
                reversibility=False,
                prerequisite_evidence=["booking_pnr", "carrier_ticket_number", "airline_rejection_proof"],
                statutory_deadline_days=60,
            ),
            CandidateAction(
                action_key="consumer_forum_filing",
                name="District Consumer Disputes Redressal Commission (DCDRC Filing)",
                stage="regulatory",
                expected_benefit_inr=35000.0,
                expected_cost_inr=500.0,
                expected_delay_days=90.0,
                risk_level=0.35,
                privacy_exposure=0.60,
                reversibility=False,
                prerequisite_evidence=["booking_pnr", "formal_legal_notice", "airline_rejection_proof"],
                statutory_deadline_days=730,
            ),
        ]

    result = decision_engine.evaluate_candidates(
        case_id=req.case_id,
        candidates=candidates,
        available_evidence=detected_evidence,
        days_since_incident=req.days_since_incident,
        weights=req.weights,
    )

    # Persist the decision optimization event to the case history if case exists
    if req.case_id and case:
        top_pick = result.ranked_actions[0] if result.ranked_actions else None
        recommended_title = top_pick.name if top_pick else result.optimal_action_key
        score_str = f"{top_pick.utility_score:.2f}" if top_pick else "N/A"
        await case_repository.add_event(
            req.case_id,
            {
                "actor": "decision_engine",
                "event_type": "decision_optimized",
                "title": f"Decision Optimized: {recommended_title}",
                "body": (
                    f"Selected highest multi-objective utility score ({score_str}) across "
                    f"{len(result.ranked_actions)} paths. Evidence considered: {', '.join(detected_evidence)}."
                ),
            },
        )

    return result
