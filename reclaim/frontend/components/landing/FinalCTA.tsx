"use client";

import Link from "next/link";
import { motion } from "framer-motion";

export default function FinalCTA() {
  return (
    <section style={{ position: "relative", zIndex: 1, padding: "8rem 1.5rem", textAlign: "center" }}>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-15%" }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        style={{
          maxWidth: "700px",
          margin: "0 auto",
          background: "#ffffff",
          border: "2px solid #231f1d",
          boxShadow: "5px 5px 0px #231f1d",
          borderRadius: "12px",
          padding: "3.5rem 2rem",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.78rem",
            letterSpacing: "0.14em",
            color: "#d97706",
            marginBottom: "0.75rem",
            fontWeight: 800,
          }}
        >
          VOICE FLOW &middot; VOICE TO JUSTICE
        </p>
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2rem, 4.5vw, 3.2rem)",
            fontWeight: 400,
            lineHeight: 1.15,
            marginBottom: "1.25rem",
            color: "#1a1715",
          }}
        >
          Whisper and solve using Voice Flow.
        </h2>
        <p style={{ fontSize: "1.05rem", lineHeight: 1.6, color: "#575147", opacity: 0.9, marginBottom: "2rem" }}>
          Turn spoken consumer complaints into legally grounded claim files, evidence packages, and official appeals in seconds.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
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
            }}
          >
            Whisper &amp; Solve Your Claim &rarr;
          </Link>
          <Link
            href="/dashboard/new"
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
            }}
          >
            Start New Analysis
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
