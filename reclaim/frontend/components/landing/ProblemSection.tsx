"use client";

import { motion } from "framer-motion";

export default function ProblemSection() {
  return (
    <section
      style={{
        position: "relative",
        zIndex: 1,
        minHeight: "70vh",
        display: "flex",
        alignItems: "center",
        padding: "6rem 1.5rem",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-15%" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        style={{
          maxWidth: "540px",
          marginLeft: "clamp(1.5rem, 8vw, 8rem)",
          backgroundColor: "#ffffff",
          border: "2px solid #231f1d",
          boxShadow: "4px 4px 0px #231f1d",
          borderRadius: "10px",
          padding: "2.25rem",
        }}
      >
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "#b45309", marginBottom: "0.75rem", fontWeight: 800 }}>
          VOICE-FIRST JUSTICE
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.8rem, 3.4vw, 2.5rem)", fontWeight: 400, lineHeight: 1.15, marginBottom: "1.25rem", color: "#1a1715" }}>
          Don&apos;t navigate complex legal forms. Just whisper and solve.
        </h2>
        <p style={{ fontSize: "0.95rem", lineHeight: 1.7, color: "#575147" }}>
          Traditional portals trap aggrieved consumers in rigid dropdowns, opaque terminology, and endless delays.
          With RESOLVE and Voice Flow, you simply speak or whisper what happened in your own words. Our platform
          cleanses speech fillers, identifies regulatory violations across 8 domains, and generates ironclad statutory filings automatically.
        </p>
      </motion.div>
    </section>
  );
}
