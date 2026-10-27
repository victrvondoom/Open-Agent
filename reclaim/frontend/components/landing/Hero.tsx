"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useSystemHealth } from "./useSystemHealth";
import CountUp from "./CountUp";

export default function Hero() {
  const { health, loading } = useSystemHealth();

  return (
    <section
      style={{
        position: "relative",
        zIndex: 1,
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "0 1.5rem",
      }}
    >
      <div style={{ maxWidth: "760px", margin: "0 auto", textAlign: "center", position: "relative", zIndex: 2 }}>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.35rem 0.95rem",
            borderRadius: "999px",
            background: "#fef3c7",
            border: "2px solid #231f1d",
            boxShadow: "2px 2px 0px #231f1d",
            marginBottom: "1.25rem",
          }}
        >
          <span style={{ fontSize: "0.85rem" }}>🏆</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", letterSpacing: "0.08em", color: "#92400e", fontWeight: 800 }}>
            BUILT FOR OPEN AGENT HACKATHON
          </span>
          <span style={{ color: "#231f1d", opacity: 0.4 }}>&middot;</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "#b45309", fontWeight: 700 }}>
            RECLAIM OPERATING SYSTEM
          </span>
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2.6rem, 6vw, 4.2rem)",
            lineHeight: 1.08,
            fontWeight: 400,
            color: "var(--bone)",
            marginBottom: "1rem",
          }}
        >
          From problem to proof to resolution.
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 0.85, y: 0 }}
          transition={{ duration: 0.5, delay: 0.16, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontSize: "1.05rem", lineHeight: 1.65, color: "var(--bone)", marginBottom: "1.75rem" }}
        >
          Speak or enter your dispute in any tone or language. RECLAIM grounds every grievance in verified statutory regulations, optimizes dispute pathways, and coordinates action execution through the Switch-independent Action Fabric with explicit human approval.
        </motion.p>

        {/* Public Product Announcement */}
        <motion.div
          id="announcement"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          style={{
            maxWidth: "720px",
            margin: "0 auto 2.25rem",
            padding: "1.25rem 1.5rem",
            borderRadius: "8px",
            background: "#ffffff",
            border: "2px solid #231f1d",
            boxShadow: "4px 4px 0px #231f1d",
            textAlign: "left",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", fontWeight: 800, color: "#92400e", letterSpacing: "0.06em" }}>
              📢 INTRODUCING RECLAIM
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: "3px", background: "#fef3c7", border: "1px solid #231f1d", fontWeight: 700 }}>
              Universal Action OS
            </span>
          </div>
          <p style={{ fontSize: "0.95rem", lineHeight: 1.55, color: "#1c1917", fontWeight: 600, marginBottom: "0.6rem" }}>
            &ldquo;Your rights shouldn&rsquo;t depend on knowing the right words. RECLAIM helps you understand the evidence, explore your options, and take the next step&mdash;through one connected workflow.&rdquo;
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", fontSize: "0.72rem", fontFamily: "var(--font-mono)", color: "#575147" }}>
            <span>
              <strong style={{ color: "#15803d" }}>✓ Active Now:</strong> Flight Cancellation Slice &middot; Recursive Regulation Splitter &middot; Human Approval Gate
            </span>
            <span>
              <strong style={{ color: "#b45309" }}>⚡ Upcoming:</strong> Multi-domain Banking &middot; Cross-Citizen Institution Radar
            </span>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.24, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}
        >
          <Link
            href="/dashboard/new"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: "0.85rem 1.6rem",
              borderRadius: "6px",
              background: "#f59e0b",
              color: "#1a1715",
              fontWeight: 800,
              border: "2px solid #231f1d",
              boxShadow: "3px 3px 0px #231f1d",
              textDecoration: "none",
              transition: "transform 0.08s ease, box-shadow 0.08s ease",
            }}
          >
            Whisper &amp; Solve Now &rarr;
          </Link>
          <a
            href="#live-demo"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: "0.85rem 1.6rem",
              borderRadius: "6px",
              border: "2px solid #231f1d",
              color: "#1a1715",
              background: "#ffffff",
              fontWeight: 700,
              boxShadow: "3px 3px 0px #231f1d",
              textDecoration: "none",
              transition: "transform 0.08s ease, box-shadow 0.08s ease",
            }}
          >
            Live Interactive Studio
          </a>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.32, ease: [0.16, 1, 0.3, 1] }}
          style={{
            marginTop: "2rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexWrap: "wrap",
            gap: "0.5rem",
          }}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", color: "var(--bone)", opacity: 0.7, letterSpacing: "0.06em", fontWeight: 700 }}>
            QUICK SCENARIOS:
          </span>
          {[
            { label: "✈️ Flight Cancelled", q: "My flight was cancelled 2 hours prior to departure and the airline refused a refund." },
            { label: "💳 Double UPI ₹5k", q: "My bank charged me twice for the same UPI transaction of Rs 5,000 and refuses to reverse it." },
            { label: "🏥 Cataract Denied", q: "My health insurance claim of Rs 1,45,000 was denied for a pre-existing condition exclusion." },
            { label: "📱 Airtel Postpaid", q: "My telecom provider is billing me for a postpaid plan I cancelled two months ago." },
            { label: "🏢 RERA Possession", q: "My builder delayed possession of my flat by 18 months under RERA and refuses delay interest." },
          ].map((item) => (
            <Link
              key={item.label}
              href={`/dashboard/new?q=${encodeURIComponent(item.q)}`}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.72rem",
                padding: "0.35rem 0.75rem",
                borderRadius: "5px",
                border: "1.5px solid #231f1d",
                background: "#ffffff",
                color: "#1a1715",
                textDecoration: "none",
                fontWeight: 700,
                boxShadow: "2px 2px 0px #231f1d",
                transition: "all 0.12s ease",
              }}
            >
              {item.label}
            </Link>
          ))}
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.5 }}
        style={{
          position: "absolute",
          bottom: "2rem",
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: "var(--font-mono)",
          fontSize: "0.78rem",
          color: "var(--bone)",
          opacity: 0.65,
        }}
      >
        {loading ? (
          "connecting to resolve..."
        ) : health ? (
          <>
            <CountUp value={health.vector_store.total_points ?? null} /> knowledge chunks indexed ·{" "}
            {health.vector_store.collections ?? 0} domain collections · {health.graph_store.events ?? 0} case events tracked
          </>
        ) : (
          "backend unreachable -- start the API to see live status"
        )}
      </motion.div>
    </section>
  );
}
