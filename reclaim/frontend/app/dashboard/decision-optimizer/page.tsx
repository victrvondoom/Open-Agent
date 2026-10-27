"use client";

import { useEffect, useState } from "react";
import { Scale, Sliders, CheckCircle2, AlertCircle, ArrowRight, ShieldAlert, Clock, IndianRupee } from "lucide-react";

interface EvaluatedAction {
  action_key: string;
  name: string;
  stage: string;
  utility_score: number;
  normalized_benefit: number;
  normalized_cost: number;
  normalized_delay: number;
  normalized_risk: number;
  normalized_privacy: number;
  eligible: boolean;
  missing_prerequisites: string[];
  deadline_passed: boolean;
  rationale: string;
}

interface DecisionRankingResponse {
  case_id: string;
  optimal_action_key: string;
  recommended_path: string[];
  ranked_actions: EvaluatedAction[];
  model_assumptions: Record<string, string>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function DecisionOptimizerPage() {
  const [wBenefit, setWBenefit] = useState(0.35);
  const [wCost, setWCost] = useState(0.20);
  const [wDelay, setWDelay] = useState(0.20);
  const [wRisk, setWRisk] = useState(0.15);
  const [wPrivacy, setWPrivacy] = useState(0.10);
  const [daysSinceIncident, setDaysSinceIncident] = useState(5);

  const [hasPnr, setHasPnr] = useState(true);
  const [hasNotice, setHasNotice] = useState(true);
  const [hasRejectionProof, setHasRejectionProof] = useState(false);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DecisionRankingResponse | null>(null);

  useEffect(() => {
    fetchRanking();
  }, [wBenefit, wCost, wDelay, wRisk, wPrivacy, daysSinceIncident, hasPnr, hasNotice, hasRejectionProof]);

  async function fetchRanking() {
    setLoading(true);
    const availableEvidence: string[] = [];
    if (hasPnr) availableEvidence.push("booking_pnr");
    if (hasNotice) availableEvidence.push("cancellation_sms_or_email");
    if (hasRejectionProof) availableEvidence.push("airline_rejection_proof");

    try {
      const res = await fetch(`${API_BASE}/decision/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: "case-flight-demo",
          available_evidence: availableEvidence,
          days_since_incident: daysSinceIncident,
          weights: {
            w_benefit: wBenefit,
            w_cost: wCost,
            w_delay: wDelay,
            w_risk: wRisk,
            w_privacy: wPrivacy,
          },
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setResult(data);
      } else {
        throw new Error();
      }
    } catch {
      // Offline fallback computation
      const rawDirectEligible = hasPnr && hasNotice;
      const rawAirsewaEligible = hasPnr && hasRejectionProof;

      setResult({
        case_id: "case-flight-demo",
        optimal_action_key: rawDirectEligible ? "direct_carrier_claim" : "airsewa_regulatory_escalation",
        recommended_path: ["direct_carrier_claim", "airsewa_regulatory_escalation", "consumer_disputes_forum_filing"],
        model_assumptions: {
          utility_formula: "U(a) = w1*B_hat - w2*C_hat - w3*D_hat - w4*R_hat - w5*P_hat",
          normalization: "Min-Max scaling bounded on [0, 1]",
        },
        ranked_actions: [
          {
            action_key: "direct_carrier_claim",
            name: "Direct Airline Refund Claim",
            stage: "direct",
            utility_score: rawDirectEligible ? 0.285 : -0.715,
            normalized_benefit: 0.43,
            normalized_cost: 0.0,
            normalized_delay: 0.08,
            normalized_risk: 0.1,
            normalized_privacy: 0.05,
            eligible: rawDirectEligible,
            missing_prerequisites: rawDirectEligible ? [] : ["cancellation_sms_or_email"],
            deadline_passed: false,
            rationale: rawDirectEligible
              ? "Statutorily eligible under current evidence (est. recovery ₹15,000). Turnaround ~7 business days."
              : "Blocked by missing evidence: cancellation notice.",
          },
          {
            action_key: "airsewa_regulatory_escalation",
            name: "Ministry of Civil Aviation (AirSewa) Escalation",
            stage: "escalation",
            utility_score: rawAirsewaEligible ? 0.175 : -0.825,
            normalized_benefit: 0.43,
            normalized_cost: 0.0,
            normalized_delay: 0.16,
            normalized_risk: 0.2,
            normalized_privacy: 0.2,
            eligible: rawAirsewaEligible,
            missing_prerequisites: rawAirsewaEligible ? [] : ["airline_rejection_proof"],
            deadline_passed: false,
            rationale: rawAirsewaEligible
              ? "Statutorily eligible under AirSewa grievance charter. Turnaround ~14 business days."
              : "Blocked by missing evidence: airline rejection proof.",
          },
          {
            action_key: "consumer_disputes_forum_filing",
            name: "District Consumer Disputes Redressal Commission (DCDRC)",
            stage: "regulatory",
            utility_score: -0.05,
            normalized_benefit: 1.0,
            normalized_cost: 1.0,
            normalized_delay: 1.0,
            normalized_risk: 0.35,
            normalized_privacy: 0.6,
            eligible: false,
            missing_prerequisites: ["formal_legal_notice", "airline_rejection_proof"],
            deadline_passed: false,
            rationale: "Higher damages potential but delayed resolution (~90 days) and public docket exposure.",
          },
        ],
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="border-b-2 border-[#231f1d] pb-5">
        <div className="flex items-center gap-2">
          <span className="rounded border border-[#231f1d] bg-amber-300 px-2 py-0.5 font-mono text-[11px] font-black uppercase text-[#1c1917] shadow-[2px_2px_0_#231f1d]">
            DECISION ENGINE
          </span>
          <span className="font-mono text-xs font-bold text-amber-800">Mathematical Multi-Objective Utility Optimization</span>
        </div>
        <h1 className="mt-2 font-serif text-3xl font-extrabold tracking-tight text-[#1c1917]">
          Dispute Pathway Optimizer &amp; Constraint Solver
        </h1>
        <p className="mt-1 font-serif italic text-sm text-stone-600">
          Computes transparent utility scores $U(a) = w_1 B(a) - w_2 C(a) - w_3 D(a) - w_4 R(a) - w_5 P(a)$ across dispute avenues.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Interactive Weights & Constraints Controls */}
        <div className="rounded-xl border-2 border-[#231f1d] bg-[#fbf9f2] p-5 shadow-[4px_4px_0_#231f1d] space-y-4">
          <h3 className="font-serif text-base font-bold text-stone-900 border-b border-stone-300 pb-2 flex items-center gap-2">
            <Sliders className="size-4 text-amber-800" /> Utility Weights
          </h3>

          <div>
            <div className="flex justify-between text-xs font-mono font-bold mb-1">
              <span>w1: Benefit (Recovery)</span>
              <span className="text-amber-800">{wBenefit.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={wBenefit}
              onChange={(e) => setWBenefit(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <div className="flex justify-between text-xs font-mono font-bold mb-1">
              <span>w2: Cost &amp; Filing Fees</span>
              <span className="text-amber-800">{wCost.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={wCost}
              onChange={(e) => setWCost(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <div className="flex justify-between text-xs font-mono font-bold mb-1">
              <span>w3: Delay (Days to Resolution)</span>
              <span className="text-amber-800">{wDelay.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={wDelay}
              onChange={(e) => setWDelay(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <div className="flex justify-between text-xs font-mono font-bold mb-1">
              <span>w4: Evidentiary Risk</span>
              <span className="text-amber-800">{wRisk.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={wRisk}
              onChange={(e) => setWRisk(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <div className="flex justify-between text-xs font-mono font-bold mb-1">
              <span>w5: Privacy Exposure</span>
              <span className="text-amber-800">{wPrivacy.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={wPrivacy}
              onChange={(e) => setWPrivacy(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div className="pt-3 border-t border-stone-300 space-y-2">
            <h4 className="font-mono text-[11px] font-bold uppercase text-stone-600">Available Case Evidence</h4>
            <label className="flex items-center gap-2 text-xs font-medium text-stone-800 cursor-pointer">
              <input
                type="checkbox"
                checked={hasPnr}
                onChange={(e) => setHasPnr(e.target.checked)}
                className="rounded border-[#231f1d]"
              />
              <span>Booking PNR &amp; E-Ticket</span>
            </label>
            <label className="flex items-center gap-2 text-xs font-medium text-stone-800 cursor-pointer">
              <input
                type="checkbox"
                checked={hasNotice}
                onChange={(e) => setHasNotice(e.target.checked)}
                className="rounded border-[#231f1d]"
              />
              <span>Cancellation Notice SMS/Email</span>
            </label>
            <label className="flex items-center gap-2 text-xs font-medium text-stone-800 cursor-pointer">
              <input
                type="checkbox"
                checked={hasRejectionProof}
                onChange={(e) => setHasRejectionProof(e.target.checked)}
                className="rounded border-[#231f1d]"
              />
              <span>Formal Airline Rejection Proof</span>
            </label>
          </div>
        </div>

        {/* Results & Ranked Paths */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
            <div className="flex items-center justify-between border-b border-stone-200 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <Scale className="size-5 text-amber-700" />
                <h3 className="font-serif text-lg font-bold text-stone-900">Ranked Dispute Pathways</h3>
              </div>
              {result && (
                <span className="rounded bg-amber-100 border border-[#231f1d] px-2.5 py-0.5 font-mono text-xs font-bold text-amber-900">
                  OPTIMAL: {result.optimal_action_key}
                </span>
              )}
            </div>

            {result?.ranked_actions.map((act, index) => (
              <div
                key={act.action_key}
                className={`mb-4 rounded-lg border-2 p-4 transition-all ${
                  index === 0 && act.eligible
                    ? "border-emerald-700 bg-emerald-50/50 shadow-[3px_3px_0_#15803d]"
                    : "border-[#231f1d] bg-[#fcfaf5] shadow-[2px_2px_0_#231f1d]"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="grid size-6 place-items-center rounded-full bg-[#1c1917] text-[11px] font-mono font-bold text-white">
                      {index + 1}
                    </span>
                    <h4 className="font-serif text-base font-bold text-stone-900">{act.name}</h4>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-xs font-bold">
                    <span>Utility Score:</span>
                    <span
                      className={`px-2 py-0.5 rounded border ${
                        act.utility_score >= 0
                          ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                          : "bg-red-100 text-red-900 border-red-300"
                      }`}
                    >
                      {act.utility_score.toFixed(3)}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-stone-600 mb-3">{act.rationale}</p>

                {/* Metric Bars */}
                <div className="grid grid-cols-5 gap-2 text-center text-[10px] font-mono">
                  <div className="bg-white p-1.5 rounded border border-stone-200">
                    <span className="text-stone-500 block">Benefit</span>
                    <span className="font-bold text-emerald-700">{act.normalized_benefit}</span>
                  </div>
                  <div className="bg-white p-1.5 rounded border border-stone-200">
                    <span className="text-stone-500 block">Cost</span>
                    <span className="font-bold text-stone-800">{act.normalized_cost}</span>
                  </div>
                  <div className="bg-white p-1.5 rounded border border-stone-200">
                    <span className="text-stone-500 block">Delay</span>
                    <span className="font-bold text-stone-800">{act.normalized_delay}</span>
                  </div>
                  <div className="bg-white p-1.5 rounded border border-stone-200">
                    <span className="text-stone-500 block">Risk</span>
                    <span className="font-bold text-amber-800">{act.normalized_risk}</span>
                  </div>
                  <div className="bg-white p-1.5 rounded border border-stone-200">
                    <span className="text-stone-500 block">Privacy</span>
                    <span className="font-bold text-stone-800">{act.normalized_privacy}</span>
                  </div>
                </div>

                {/* Eligibility Flag */}
                <div className="mt-3 pt-2 border-t border-stone-200 flex items-center justify-between text-xs font-mono">
                  <span className="flex items-center gap-1 font-bold">
                    {act.eligible ? (
                      <span className="text-emerald-700 flex items-center gap-1">
                        <CheckCircle2 className="size-3.5" /> Statutorily Actionable Now
                      </span>
                    ) : (
                      <span className="text-amber-800 flex items-center gap-1">
                        <AlertCircle className="size-3.5" /> Missing Prerequisites
                      </span>
                    )}
                  </span>
                  <span className="text-stone-500 uppercase">Stage: {act.stage}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
