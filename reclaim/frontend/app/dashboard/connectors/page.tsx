"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck, ArrowRight, CheckCircle2, AlertTriangle, RefreshCw, Send, Lock, FileText, Plane, Mail, Building2,
} from "lucide-react";

interface ActionCapability {
  action_id: string;
  name: string;
  description: string;
  is_write: boolean;
  requires_human_approval: boolean;
  is_reversible: boolean;
  risk_level: string;
}

interface ConnectorManifest {
  connector_id: string;
  name: string;
  version: string;
  domain: string;
  description: string;
  execution_modes: string[];
  capabilities: ActionCapability[];
}

interface PreparedAction {
  prepared_action_id: string;
  connector_id: string;
  action_id: string;
  case_id: string;
  requires_human_approval: boolean;
  approval_state: string;
  approval_token?: string;
  summary?: string;
  summary_for_human?: string;
  consequences?: string[];
  payload?: Record<string, any>;
  reversibility?: boolean;
  estimated_benefit?: number;
}

interface ActionResult {
  operation_id: string;
  state: string;
  provider_reference?: string;
  output_data: Record<string, any>;
  executed_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function ConnectorsPage() {
  const [activeTab, setActiveTab] = useState<"aviation" | "email">("aviation");
  const [connectors, setConnectors] = useState<ConnectorManifest[]>([]);
  const [loading, setLoading] = useState(true);

  // Aviation Form
  const [pnr, setPnr] = useState("PNR-7788-IND");
  const [flightNumber, setFlightNumber] = useState("6E-204");
  const [airline, setAirline] = useState("IndiGo Airlines");
  const [ticketAmount, setTicketAmount] = useState(7500);
  const [hoursNotice, setHoursNotice] = useState(12);

  // Email Delivery Form
  const [recipientEmail, setRecipientEmail] = useState("nodal.officer@indigo.in");
  const [emailSubject, setEmailSubject] = useState("Statutory Refund Notice — PNR 7788-IND (IndiGo 6E-204)");
  const [emailBody, setEmailBody] = useState(
    "To: Principal Nodal Grievance Redressal Officer\n\n" +
    "RE: STATUTORY REFUND DEMAND UNDER DGCA CAR SERIES M PART IV\n" +
    "Flight 6E-204 was cancelled on less than 24 hours notice. Under Section 3.2, " +
    "passenger is entitled to a full ticket refund plus statutory compensation.\n\n" +
    "Demand is formally made for immediate disbursement within 7 working days."
  );

  const [prepared, setPrepared] = useState<PreparedAction | null>(null);
  const [approvalToken, setApprovalToken] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<ActionResult | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConnectors();
  }, []);

  async function fetchConnectors() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/connectors`);
      if (res.ok) {
        const data = await res.json();
        setConnectors(data);
      }
    } catch {
      // offline fallback
    } finally {
      setLoading(false);
    }
  }

  function handleTabChange(tab: "aviation" | "email") {
    setActiveTab(tab);
    setPrepared(null);
    setApprovalToken(null);
    setExecutionResult(null);
    setError(null);
  }

  async function handlePrepareAction() {
    setIsProcessing(true);
    setError(null);
    setExecutionResult(null);
    setApprovalToken(null);

    const isEmail = activeTab === "email";
    const connectorId = isEmail
      ? "reclaim.connectors.email_delivery"
      : "reclaim.connectors.aviation_refund";
    const actionId = isEmail ? "send_complaint_email" : "submit_airline_claim";

    const payload = isEmail
      ? {
          recipient_email: recipientEmail,
          subject: emailSubject,
          body: emailBody,
          case_id: "case-dispute-live-01",
        }
      : {
          pnr,
          flight_number: flightNumber,
          airline,
          cancellation_notice_hours: hoursNotice,
          paid_amount: ticketAmount,
          claim_package: {
            statutory_basis: "DGCA CAR Section 3 Series M Part IV Section 3.2",
            claimed_amount: ticketAmount + 10000,
          },
        };

    try {
      const res = await fetch(`${API_BASE}/connectors/${connectorId}/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_id: actionId,
          case_id: "case-dispute-live-01",
          payload,
          execution_mode: "sandbox",
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
      }
      const data = await res.json();
      setPrepared(data);
    } catch (err: any) {
      setError(err.message || "Failed to prepare action.");
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleGrantApproval() {
    if (!prepared) return;
    setIsProcessing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/connectors/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prepared_action: prepared,
          user_id: "claimant-citizen-01",
          consent_statement:
            activeTab === "email"
              ? `I explicitly review and authorize dispatching this formal legal dispute to ${recipientEmail}.`
              : "I explicitly review and authorize filing this statutory refund claim under DGCA guidelines.",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setApprovalToken(data.approval_token);
      } else {
        const errText = await res.text();
        throw new Error(errText);
      }
    } catch (err: any) {
      setError(err.message || "Approval issuance failed.");
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleExecuteAction() {
    if (!prepared || !approvalToken) return;
    setIsProcessing(true);
    setError(null);
    const connectorId = prepared.connector_id;
    try {
      const res = await fetch(`${API_BASE}/connectors/${connectorId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prepared_action: prepared,
          idempotency_key: `idemp-${Date.now()}`,
          approval_token: approvalToken,
        }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Execution failed");
      }
      const data = await res.json();
      setExecutionResult(data);
    } catch (err: any) {
      setError(err.message || "Action execution error");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="border-b-2 border-[#231f1d] pb-5">
        <div className="flex items-center gap-2">
          <span className="rounded border border-[#231f1d] bg-amber-300 px-2 py-0.5 font-mono text-[11px] font-black uppercase text-[#1c1917] shadow-[2px_2px_0_#231f1d]">
            ACTION FABRIC
          </span>
          <span className="font-mono text-xs font-bold text-amber-800">Switch-Independent Integration Layer</span>
        </div>
        <h1 className="mt-2 font-serif text-3xl font-extrabold tracking-tight text-[#1c1917]">
          Action Connectors &amp; Approval Center
        </h1>
        <p className="mt-1 font-serif italic text-sm text-stone-600">
          Connect approved dispute agents, regulatory portals, and verified outbound channels with an explicit human-in-the-loop approval gate.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b-2 border-[#231f1d] gap-2">
        <button
          onClick={() => handleTabChange("aviation")}
          className={`flex items-center gap-2 px-5 py-2.5 font-mono text-xs font-bold transition-all border-t-2 border-x-2 border-[#231f1d] rounded-t-lg -mb-0.5 ${
            activeTab === "aviation"
              ? "bg-white text-stone-900 border-b-2 border-b-white z-10 shadow-[2px_-2px_0_#231f1d]"
              : "bg-stone-200 text-stone-600 hover:bg-stone-100"
          }`}
        >
          <Plane className="size-4" /> Aviation Dispute Slice (DGCA)
        </button>
        <button
          onClick={() => handleTabChange("email")}
          className={`flex items-center gap-2 px-5 py-2.5 font-mono text-xs font-bold transition-all border-t-2 border-x-2 border-[#231f1d] rounded-t-lg -mb-0.5 ${
            activeTab === "email"
              ? "bg-white text-stone-900 border-b-2 border-b-white z-10 shadow-[2px_-2px_0_#231f1d]"
              : "bg-stone-200 text-stone-600 hover:bg-stone-100"
          }`}
        >
          <Mail className="size-4" /> Complaint Email Delivery (SMTP / Outbox)
        </button>
      </div>

      {/* Main Execution Card */}
      <div className="rounded-xl border-2 border-[#231f1d] bg-white p-6 shadow-[4px_4px_0_#231f1d]">
        <div className="flex items-center justify-between border-b-2 border-stone-200 pb-4 mb-5">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-lg border-2 border-[#231f1d] bg-amber-100 shadow-[2px_2px_0_#231f1d]">
              {activeTab === "aviation" ? <Plane className="size-5 text-[#92400e]" /> : <Mail className="size-5 text-[#92400e]" />}
            </div>
            <div>
              <h2 className="font-serif text-lg font-bold text-[#1c1917]">
                {activeTab === "aviation" ? "Flight Cancellation & Refund Slice" : "Outbound Evidence & Complaint Dispatch"}
              </h2>
              <p className="text-xs text-stone-500">
                {activeTab === "aviation"
                  ? "DGCA CAR Section 3 Series M Part IV · Sandbox & Live Verification"
                  : "Authenticated SMTP Transport / Local Durable Outbox for Test Verification"}
              </p>
            </div>
          </div>
          <span className="rounded-full border border-emerald-600 bg-emerald-50 px-2.5 py-0.5 font-mono text-[11px] font-bold text-emerald-800">
            ● READY
          </span>
        </div>

        {/* Input Parameters Form */}
        {activeTab === "aviation" ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Airline Carrier</label>
              <input
                type="text"
                value={airline}
                onChange={(e) => setAirline(e.target.value)}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Flight Number</label>
              <input
                type="text"
                value={flightNumber}
                onChange={(e) => setFlightNumber(e.target.value)}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Booking PNR</label>
              <input
                type="text"
                value={pnr}
                onChange={(e) => setPnr(e.target.value)}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Ticket Amount (₹)</label>
              <input
                type="number"
                value={ticketAmount}
                onChange={(e) => setTicketAmount(Number(e.target.value))}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Cancellation Notice (Hours)</label>
              <input
                type="number"
                value={hoursNotice}
                onChange={(e) => setHoursNotice(Number(e.target.value))}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={handlePrepareAction}
                disabled={isProcessing}
                className="w-full rounded-lg border-2 border-[#231f1d] bg-amber-300 p-2 text-xs font-mono font-bold text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-400 transition-all flex items-center justify-center gap-1.5"
              >
                <FileText className="size-4" /> 1. Prepare Carrier Claim
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Recipient Grievance Desk Email</label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
                />
              </div>
              <div>
                <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Subject Line</label>
                <input
                  type="text"
                  value={emailSubject}
                  onChange={(e) => setEmailSubject(e.target.value)}
                  className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-stone-700 uppercase mb-1">Formal Complaint Body</label>
              <textarea
                rows={4}
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
                className="w-full rounded-md border-2 border-[#231f1d] p-2 text-xs font-mono bg-[#fcfaf5]"
              />
            </div>
            <button
              onClick={handlePrepareAction}
              disabled={isProcessing}
              className="rounded-lg border-2 border-[#231f1d] bg-amber-300 px-6 py-2.5 text-xs font-mono font-bold text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-400 transition-all flex items-center gap-2"
            >
              <FileText className="size-4" /> 1. Prepare Email Dispatch
            </button>
          </div>
        )}

        {/* Step 2: Prepared Action Preview & Approval Gate */}
        {prepared && (
          <div className="mt-6 rounded-lg border-2 border-[#231f1d] bg-[#fbf9f2] p-5 shadow-[3px_3px_0_#231f1d]">
            <div className="flex items-center justify-between border-b border-stone-300 pb-3 mb-3">
              <span className="font-mono text-xs font-bold uppercase text-amber-900">
                Prepared Action: {prepared.prepared_action_id}
              </span>
              <span className="rounded bg-amber-100 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-900 border border-amber-300">
                STATUS: {prepared.approval_state.toUpperCase()}
              </span>
            </div>

            <p className="text-sm font-serif font-bold text-stone-900 mb-2">
              {prepared.summary || prepared.summary_for_human}
            </p>

            {prepared.consequences && (
              <div className="mb-4">
                <p className="font-mono text-[11px] font-bold text-stone-600 uppercase mb-1">Legal Notice &amp; Consequences:</p>
                <ul className="list-disc pl-5 text-xs text-stone-700 space-y-1">
                  {prepared.consequences.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Human Approval Gate Action */}
            <div className="mt-4 border-t border-stone-300 pt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Lock className="size-4 text-amber-800" />
                <span className="text-xs font-semibold text-stone-800">
                  {approvalToken ? "✓ Cryptographic Approval Token Granted" : "Human Approval Checkpoint: Consent Required"}
                </span>
              </div>

              <div className="flex gap-2">
                {!approvalToken ? (
                  <button
                    onClick={handleGrantApproval}
                    disabled={isProcessing}
                    className="rounded-md border-2 border-[#231f1d] bg-amber-400 px-4 py-2 text-xs font-mono font-bold text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-500 transition-all"
                  >
                    2. Authorize &amp; Sign Token
                  </button>
                ) : (
                  <button
                    onClick={handleExecuteAction}
                    disabled={isProcessing}
                    className="rounded-md border-2 border-[#231f1d] bg-emerald-500 px-5 py-2 text-xs font-mono font-bold text-white shadow-[2px_2px_0_#231f1d] hover:bg-emerald-600 transition-all flex items-center gap-1.5"
                  >
                    <Send className="size-3.5" /> 3. Execute Outbound Action &rarr;
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Execution Result & Audit Trail */}
        {executionResult && (
          <div className="mt-6 rounded-lg border-2 border-emerald-800 bg-emerald-50 p-5 shadow-[3px_3px_0_#15803d]">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle2 className="size-5 text-emerald-700" />
              <h3 className="font-serif text-base font-bold text-emerald-900">
                Action Executed &amp; Persisted to Case Ledger
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono text-emerald-950">
              <div>
                <strong>Operation ID:</strong> {executionResult.operation_id}
              </div>
              <div>
                <strong>Provider Reference:</strong> {executionResult.provider_reference || "N/A"}
              </div>
              <div>
                <strong>Operation State:</strong> {executionResult.state.toUpperCase()}
              </div>
              <div>
                <strong>Delivery Mode:</strong> {executionResult.output_data?.delivery_mode || executionResult.output_data?.mode || "DURABLE_OUTBOX"}
              </div>
              <div className="col-span-2 border-t border-emerald-200 pt-2 text-[11px] text-emerald-800">
                <strong>Audit Details:</strong> {JSON.stringify(executionResult.output_data)}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md border border-red-500 bg-red-50 p-3 text-xs text-red-700">
            {error}
          </div>
        )}
      </div>

      {/* Connector Registry Explorer */}
      <div>
        <h3 className="font-serif text-xl font-bold text-[#1c1917] mb-3">Action Fabric Registered Connectors</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {connectors.map((c) => (
            <div key={c.connector_id} className="rounded-lg border-2 border-[#231f1d] bg-white p-4 shadow-[2px_2px_0_#231f1d]">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs font-bold text-amber-900">{c.name}</span>
                <span className="rounded border border-[#231f1d] bg-stone-100 px-1.5 py-0.5 text-[9px] font-mono font-bold">
                  v{c.version}
                </span>
              </div>
              <p className="text-xs text-stone-600 mb-3">{c.description}</p>
              <div className="flex items-center justify-between text-[11px] font-mono text-stone-500 border-t border-stone-200 pt-2">
                <span>Domain: {c.domain.toUpperCase()}</span>
                <span>Capabilities: {c.capabilities?.length || 2}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
