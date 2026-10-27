from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class OptimizationWeights(BaseModel):
    w_benefit: float = Field(default=0.35, description="Weight for expected economic/remedy benefit")
    w_cost: float = Field(default=0.20, description="Weight for friction/financial cost")
    w_delay: float = Field(default=0.20, description="Weight for resolution delay in days")
    w_risk: float = Field(default=0.15, description="Weight for evidentiary or procedural risk")
    w_privacy: float = Field(default=0.10, description="Weight for personal data exposure")


class CandidateAction(BaseModel):
    action_key: str
    name: str
    stage: str  # "direct", "escalation", "regulatory"
    expected_benefit_inr: float = Field(description="Expected monetary or statutory recovery in INR")
    expected_cost_inr: float = Field(default=0.0, description="Filing fees, legal costs, or courier charges")
    expected_delay_days: float = Field(description="Expected business days to resolution")
    risk_level: float = Field(ge=0.0, le=1.0, description="0.0 = certain statutory basis, 1.0 = highly contested")
    privacy_exposure: float = Field(ge=0.0, le=1.0, description="0.0 = direct private negotiation, 1.0 = public docket")
    reversibility: bool = True
    prerequisite_evidence: list[str] = Field(default_factory=list)
    statutory_deadline_days: int | None = None


class EvaluatedAction(BaseModel):
    action_key: str
    name: str
    stage: str
    utility_score: float
    normalized_benefit: float
    normalized_cost: float
    normalized_delay: float
    normalized_risk: float
    normalized_privacy: float
    eligible: bool
    missing_prerequisites: list[str]
    deadline_passed: bool
    rationale: str


class DecisionRankingResponse(BaseModel):
    case_id: str
    optimal_action_key: str
    recommended_path: list[str]
    ranked_actions: list[EvaluatedAction]
    weights_used: OptimizationWeights
    model_assumptions: dict[str, str]


class ReclaimDecisionEngine:
    """Mathematical multi-objective utility optimizer and constraint validator for dispute actions.

    Computes:
      U(a) = w1 * B_hat(a) - w2 * C_hat(a) - w3 * D_hat(a) - w4 * R_hat(a) - w5 * P_hat(a)
    subject to evidentiary, regulatory deadline, and jurisdictional constraints.
    """

    def __init__(self, default_weights: OptimizationWeights | None = None):
        self.weights = default_weights or OptimizationWeights()

    def evaluate_candidates(
        self,
        case_id: str,
        candidates: list[CandidateAction],
        available_evidence: list[str],
        days_since_incident: int = 5,
        weights: OptimizationWeights | None = None,
    ) -> DecisionRankingResponse:
        w = weights or self.weights

        if not candidates:
            raise ValueError("No candidate actions provided for evaluation")

        max_benefit = max((c.expected_benefit_inr for c in candidates), default=1.0) or 1.0
        max_cost = max((c.expected_cost_inr for c in candidates), default=1.0) or 1.0
        max_delay = max((c.expected_delay_days for c in candidates), default=30.0) or 30.0

        evaluated: list[EvaluatedAction] = []
        available_set = set(available_evidence)

        for c in candidates:
            # 1. Normalization
            b_hat = c.expected_benefit_inr / max_benefit
            c_hat = c.expected_cost_inr / max_cost if max_cost > 0 else 0.0
            d_hat = min(1.0, c.expected_delay_days / max_delay) if max_delay > 0 else 0.0
            r_hat = c.risk_level
            p_hat = c.privacy_exposure

            # 2. Multi-objective utility computation
            utility = (
                w.w_benefit * b_hat
                - w.w_cost * c_hat
                - w.w_delay * d_hat
                - w.w_risk * r_hat
                - w.w_privacy * p_hat
            )

            # 3. Constraint checking
            missing = [req for req in c.prerequisite_evidence if req not in available_set]
            deadline_passed = False
            if c.statutory_deadline_days and days_since_incident > c.statutory_deadline_days:
                deadline_passed = True

            eligible = (len(missing) == 0) and not deadline_passed

            # Penalize ineligible options in ranking
            if not eligible:
                utility -= 1.0

            # 4. Human-readable explanation
            reasons = []
            if eligible:
                reasons.append(f"Statutorily eligible under current evidence (est. recovery ₹{c.expected_benefit_inr:,.0f}).")
                reasons.append(f"Turnaround ~{c.expected_delay_days:.0f} business days.")
            else:
                if missing:
                    reasons.append(f"Blocked by missing evidence: {', '.join(missing)}.")
                if deadline_passed:
                    reasons.append(f"Statutory filing deadline ({c.statutory_deadline_days} days) has expired.")

            evaluated.append(
                EvaluatedAction(
                    action_key=c.action_key,
                    name=c.name,
                    stage=c.stage,
                    utility_score=round(utility, 4),
                    normalized_benefit=round(b_hat, 3),
                    normalized_cost=round(c_hat, 3),
                    normalized_delay=round(d_hat, 3),
                    normalized_risk=round(r_hat, 3),
                    normalized_privacy=round(p_hat, 3),
                    eligible=eligible,
                    missing_prerequisites=missing,
                    deadline_passed=deadline_passed,
                    rationale=" ".join(reasons),
                )
            )

        # Sort descending by utility
        evaluated.sort(key=lambda x: x.utility_score, reverse=True)
        optimal = evaluated[0].action_key if evaluated else "none"

        # Sequential escalation path
        stages_order = ["direct", "escalation", "regulatory"]
        path = [e.action_key for s in stages_order for e in evaluated if e.stage == s]

        return DecisionRankingResponse(
            case_id=case_id,
            optimal_action_key=optimal,
            recommended_path=path,
            ranked_actions=evaluated,
            weights_used=w,
            model_assumptions={
                "utility_formula": "U(a) = w1*B_hat - w2*C_hat - w3*D_hat - w4*R_hat - w5*P_hat",
                "normalization": "Min-Max scaling bounded on [0, 1]",
                "penalty": "Missing evidence or expired deadlines apply strict -1.0 utility penalty",
            },
        )


decision_engine = ReclaimDecisionEngine()
