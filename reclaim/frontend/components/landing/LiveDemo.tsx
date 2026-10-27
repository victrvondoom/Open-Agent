"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, RotateCw, Mic, Sparkles, ArrowRight, CheckCircle2, ShieldCheck, Zap, Terminal, Activity } from "lucide-react";
import { getSystemHealth, classifyQuery, API_BASE, type SystemHealth, type DomainCandidate } from "@/lib/api-client";
import { cleanTranscript } from "@/lib/voice-engine";

const HEALTH_URL = `${API_BASE.replace(/\/api\/v1\/?$/, "")}/health`;

interface SamplePrompt {
  label: string;
  domain: string;
  rawSpeech: string;
  institution: string;
  regulationHint: string;
}

const SAMPLE_PROMPTS: SamplePrompt[] = [
  {
    label: "IndiGo Flight Cancelled",
    domain: "airlines",
    rawSpeech: "Um, basically, IndiGo cancelled my flight 6E-241 two hours prior to departure and, you know, refused a cash refund or hotel care.",
    institution: "InterGlobe Aviation (IndiGo)",
    regulationHint: "DGCA CAR Section 3 Series M Part IV & Full Cash Refund Mandate",
  },
  {
    label: "Star Health Claim Denied",
    domain: "health_insurance",
    rawSpeech: "Like, my health insurance claim of Rs 145000 was denied by Star Health for pre-existing conditions, but I have had the policy for 36 months.",
    institution: "Star Health & Allied Insurance",
    regulationHint: "IRDAI Master Circular 2024 & Section 45 3-Year Incontestability",
  },
  {
    label: "HDFC Duplicate UPI Debit",
    domain: "banking",
    rawSpeech: "Actually, HDFC bank charged me twice for the same UPI transaction of Rs 5000 and refused to reverse it after T+1 day.",
    institution: "HDFC Bank Ltd",
    regulationHint: "RBI Harmonisation of Turn Around Time (TAT) & ₹100/day penal compensation",
  },
  {
    label: "Airtel Erroneous Billing",
    domain: "telecom",
    rawSpeech: "Well, Airtel is continuing to bill me for a postpaid broadband plan that I cancelled two months ago with written proof.",
    institution: "Bharti Airtel Ltd",
    regulationHint: "TRAI Quality of Service Regulations & Billing Dispute Redressal",
  },
  {
    label: "DLF 18-Mo Delayed Possession",
    domain: "housing",
    rawSpeech: "So, the builder DLF delayed possession of my apartment by 18 months under RERA and refuses to pay delay interest.",
    institution: "DLF Limited",
    regulationHint: "RERA Section 18 Mandatory Delay Interest at SBI MCLR + 2%",
  },
];

export default function LiveDemo() {
  const [activeTab, setActiveTab] = useState<"voice" | "telemetry">("voice");

  // Telemetry state
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0);

  // Voice Flow interactive state
  const [selectedSample, setSelectedSample] = useState<SamplePrompt>(SAMPLE_PROMPTS[0]);
  const [customText, setCustomText] = useState(SAMPLE_PROMPTS[0].rawSpeech);
  const [cleanedOutput, setCleanedOutput] = useState("");
  const [candidates, setCandidates] = useState<DomainCandidate[]>([]);
  const [classifying, setClassifying] = useState(false);
  const [isSimulatingSpeech, setIsSimulatingSpeech] = useState(false);

  const runHealth = () => {
    setLoading(true);
    setError(null);
    getSystemHealth()
      .then(({ health, latencyMs }) => {
        setHealth(health);
        setLatencyMs(latencyMs);
        setRuns((r) => r + 1);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    runHealth();
  }, []);

  // Process text through Voice Flow cleanup and live classification
  const processInput = (text: string) => {
    const cleaned = cleanTranscript(text);
    setCleanedOutput(cleaned);

    if (cleaned.trim().length > 10) {
      setClassifying(true);
      classifyQuery(cleaned)
        .then((res) => {
          setCandidates(res.candidates);
        })
        .catch(() => {
          setCandidates([]);
        })
        .finally(() => {
          setClassifying(false);
        });
    } else {
      setCandidates([]);
    }
  };

  useEffect(() => {
    processInput(customText);
  }, [customText]);

  const handlePickSample = (sample: SamplePrompt) => {
    setSelectedSample(sample);
    setCustomText(sample.rawSpeech);
  };

  const handleSimulateWhisper = () => {
    setIsSimulatingSpeech(true);
    setTimeout(() => {
      setIsSimulatingSpeech(false);
      processInput(customText);
    }, 600);
  };

  return (
    <section id="live-demo" style={{ position: "relative", zIndex: 1, padding: "6rem 1.5rem" }}>
      <div style={{ maxWidth: "860px", margin: "0 auto" }}>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.78rem",
            letterSpacing: "0.14em",
            color: "var(--cyan)",
            marginBottom: "0.75rem",
            textAlign: "center",
            fontWeight: 700,
          }}
        >
          LIVE INTERACTIVE STUDIO
        </p>
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(1.8rem, 3.2vw, 2.4rem)",
            fontWeight: 400,
            textAlign: "center",
            marginBottom: "1.25rem",
            color: "var(--bone)",
          }}
        >
          Whisper and solve live using Voice Flow.
        </h2>
        <p style={{ textAlign: "center", opacity: 0.75, maxWidth: "620px", margin: "0 auto 2rem", fontSize: "0.95rem", lineHeight: 1.6 }}>
          Experience real-time voice speech cleanup, statutory entity grounding, and instant agent classification on the running RESOLVE engine.
        </p>

        {/* Tab switcher */}
        <div style={{ display: "flex", justifyContent: "center", gap: "0.75rem", marginBottom: "1.75rem" }}>
          <button
            onClick={() => setActiveTab("voice")}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.8rem",
              padding: "0.55rem 1.2rem",
              borderRadius: "6px",
              border: "2px solid #231f1d",
              background: activeTab === "voice" ? "#f59e0b" : "#ffffff",
              color: "#1a1715",
              boxShadow: "2px 2px 0px #231f1d",
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              cursor: "pointer",
              transition: "all 0.1s ease",
            }}
          >
            <Sparkles size={14} /> Voice Flow Live Studio
          </button>
          <button
            onClick={() => setActiveTab("telemetry")}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.8rem",
              padding: "0.55rem 1.2rem",
              borderRadius: "6px",
              border: "2px solid #231f1d",
              background: activeTab === "telemetry" ? "#f59e0b" : "#ffffff",
              color: "#1a1715",
              boxShadow: "2px 2px 0px #231f1d",
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              cursor: "pointer",
              transition: "all 0.1s ease",
            }}
          >
            <Activity size={14} /> Engine Telemetry &amp; Health
          </button>
        </div>

        <motion.div
          layout
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          style={{
            backgroundColor: "#fdfbf7",
            border: "2px solid #231f1d",
            boxShadow: "5px 5px 0px #231f1d",
            borderRadius: "12px",
            padding: "1.75rem",
          }}
        >
          {activeTab === "voice" ? (
            <div>
              {/* Preset Dispute Scenarios */}
              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", opacity: 0.7, letterSpacing: "0.06em", textTransform: "uppercase", display: "block", marginBottom: "0.5rem", fontWeight: 700 }}>
                  Select a Real-World Spoken Scenario:
                </span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {SAMPLE_PROMPTS.map((sample) => {
                    const isSelected = selectedSample.label === sample.label;
                    return (
                      <button
                        key={sample.label}
                        onClick={() => handlePickSample(sample)}
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.75rem",
                          padding: "0.4rem 0.8rem",
                          borderRadius: "5px",
                          border: isSelected ? "2px solid #231f1d" : "1.5px solid #231f1d",
                          background: isSelected ? "#fef3c7" : "#ffffff",
                          color: isSelected ? "#92400e" : "#1a1715",
                          boxShadow: isSelected ? "2px 2px 0px #231f1d" : "1.5px 1.5px 0px #231f1d",
                          fontWeight: isSelected ? 800 : 600,
                          cursor: "pointer",
                          transition: "all 0.1s ease",
                        }}
                      >
                        {sample.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Spoken Textarea */}
              <div style={{ marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                  <label style={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", fontWeight: 700, color: "var(--bone)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <Mic size={14} style={{ color: "#d97706" }} /> Spoken Audio Ingestion (with Speech Fillers):
                  </label>
                  <button
                    onClick={handleSimulateWhisper}
                    disabled={isSimulatingSpeech}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.7rem",
                      padding: "0.3rem 0.65rem",
                      borderRadius: "4px",
                      background: "#fef3c7",
                      border: "1.5px solid #231f1d",
                      boxShadow: "1.5px 1.5px 0px #231f1d",
                      color: "#92400e",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      fontWeight: 700,
                    }}
                  >
                    {isSimulatingSpeech ? <Loader2 size={11} className="aperture-spin" /> : <Zap size={11} />}
                    {isSimulatingSpeech ? "Whispering..." : "Simulate Live Whisper"}
                  </button>
                </div>
                <textarea
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                  rows={2}
                  style={{
                    width: "100%",
                    borderRadius: "6px",
                    border: "2px solid #231f1d",
                    padding: "0.75rem 0.95rem",
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.9rem",
                    color: "#1a1715",
                    background: "#ffffff",
                    boxShadow: "inset 1px 1px 3px rgba(0,0,0,0.06)",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                  placeholder="Speak or type your consumer dispute here in any language..."
                />
              </div>

              {/* Dynamic Pipeline Output Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "1rem", marginBottom: "1.25rem" }}>
                {/* Cleaned Voice Flow Box */}
                <div
                  style={{
                    padding: "1rem",
                    borderRadius: "6px",
                    background: "#ffffff",
                    border: "2px solid #231f1d",
                    boxShadow: "2px 2px 0px #231f1d",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.35rem" }}>
                    <ShieldCheck size={14} style={{ color: "#15803d" }} />
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", fontWeight: 800, color: "#15803d", textTransform: "uppercase" }}>
                      Voice Flow Cleaned &amp; Grounded
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: "0.85rem", lineHeight: 1.55, color: "#1a1715", fontStyle: "italic" }}>
                    &ldquo;{cleanedOutput}&rdquo;
                  </p>
                  <div style={{ marginTop: "0.5rem", fontSize: "0.68rem", fontFamily: "var(--font-mono)", color: "#575147", fontWeight: 600 }}>
                    ✓ Fillers removed &middot; Statutory entity codes normalized
                  </div>
                </div>

                {/* Live Classification Box */}
                <div
                  style={{
                    padding: "1rem",
                    borderRadius: "6px",
                    background: "#ffffff",
                    border: "2px solid #231f1d",
                    boxShadow: "2px 2px 0px #231f1d",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                      <CheckCircle2 size={14} style={{ color: "#7c3aed" }} />
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", fontWeight: 800, color: "#7c3aed", textTransform: "uppercase" }}>
                        Multi-Domain Agent Routing
                      </span>
                    </div>
                    {classifying && <Loader2 size={12} className="aperture-spin" style={{ color: "var(--violet)" }} />}
                  </div>

                  {candidates.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                      {candidates.slice(0, 2).map((c) => (
                        <div key={c.domain} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", fontWeight: 700, color: "#1a1715", textTransform: "capitalize" }}>
                            {c.domain.replace("_", " ")}
                          </span>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "#0284c7", fontWeight: 800 }}>
                            {Math.round(c.confidence * 100)}% Match
                          </span>
                        </div>
                      ))}
                      <div style={{ marginTop: "0.35rem", fontSize: "0.72rem", fontFamily: "var(--font-mono)", color: "#c2410c", fontWeight: 700 }}>
                        Statute: {selectedSample.regulationHint}
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "#575147" }}>
                      {classifying ? "Classifying against 8 regulated domains..." : "Routing to specialist agent..."}
                    </div>
                  )}
                </div>
              </div>

              {/* Action Button to Launch in Dashboard */}
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <Link
                  href={`/dashboard/new?q=${encodeURIComponent(cleanedOutput)}`}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.82rem",
                    padding: "0.7rem 1.35rem",
                    borderRadius: "6px",
                    background: "#f59e0b",
                    color: "#1a1715",
                    fontWeight: 800,
                    textDecoration: "none",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.45rem",
                    border: "2px solid #231f1d",
                    boxShadow: "3px 3px 0px #231f1d",
                  }}
                >
                  Whisper &amp; Solve This Claim in Dashboard <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          ) : (
            /* Telemetry Tab */
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", color: "#575147", display: "flex", alignItems: "center", gap: "0.35rem", fontWeight: 600 }}>
                  <Terminal size={14} /> ~ curl {HEALTH_URL}
                </span>
                <button
                  onClick={runHealth}
                  disabled={loading}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    background: "#ffffff",
                    border: "1.5px solid #231f1d",
                    boxShadow: "1.5px 1.5px 0px #231f1d",
                    borderRadius: "4px",
                    padding: "0.35rem 0.75rem",
                    color: "#1a1715",
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.74rem",
                    cursor: "pointer",
                  }}
                >
                  {loading ? <Loader2 size={12} className="aperture-spin" /> : <RotateCw size={12} />}
                  run again
                </button>
              </div>

              {loading && <div style={{ color: "#575147", fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}>Connecting to backend...</div>}

              {error && !loading && (
                <div style={{ color: "#c2410c", fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}>
                  Request failed: {error}
                  <div style={{ opacity: 0.75, marginTop: "0.5rem", fontSize: "0.75rem" }}>
                    The backend isn&apos;t reachable from here -- start it and hit &quot;run again&quot;.
                  </div>
                </div>
              )}

              {health && !loading && !error && (
                <>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.82rem", color: "#0284c7", marginBottom: "0.75rem", fontWeight: 700 }}>
                    &#8618; {latencyMs}ms &middot; status: {health.status} &middot; provider: {health.llm.provider}
                    {health.llm.reasoning_model ? ` (${health.llm.reasoning_model})` : ""} &middot; run #{runs}
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      lineHeight: 1.6,
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8rem",
                      background: "#ffffff",
                      padding: "1rem",
                      borderRadius: "6px",
                      border: "2px solid #231f1d",
                      boxShadow: "2px 2px 0px #231f1d",
                      color: "#1a1715",
                    }}
                  >
{JSON.stringify(
  {
    status: health.status,
    vector_store: health.vector_store,
    graph_store: health.graph_store,
    llm: health.llm,
  },
  null,
  2
)}
                  </pre>
                </>
              )}
            </div>
          )}
        </motion.div>
      </div>
    </section>
  );
}
