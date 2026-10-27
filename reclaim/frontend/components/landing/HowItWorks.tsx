"use client";

import { motion } from "framer-motion";
import { LIFECYCLE_STEPS } from "@/lib/aperture/tokens";
import { useAperture } from "./ApertureContext";

export default function HowItWorks() {
  const { triggerPulse } = useAperture();

  return (
    <section
      id="how-it-works"
      style={{
        position: "relative",
        zIndex: 1,
        padding: "6rem 1.5rem",
      }}
    >
      <div
        style={{
          maxWidth: "540px",
          marginLeft: "auto",
          marginRight: "clamp(1.5rem, 8vw, 8rem)",
          backgroundColor: "#ffffff",
          border: "2px solid #231f1d",
          boxShadow: "4px 4px 0px #231f1d",
          borderRadius: "10px",
          padding: "2.25rem",
        }}
      >
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "#7c3aed", marginBottom: "1.5rem", fontWeight: 800 }}>
          01&ndash;06 &middot; REQUEST LIFECYCLE
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {LIFECYCLE_STEPS.map((step, i) => (
            <motion.div
              key={step.n}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-10%" }}
              transition={{ duration: 0.45, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
              onMouseEnter={triggerPulse}
              style={{ display: "flex", gap: "1rem", cursor: "default", alignItems: "flex-start" }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.75rem",
                  fontWeight: 800,
                  background: "#fef3c7",
                  color: "#92400e",
                  border: "1.5px solid #231f1d",
                  padding: "0.2rem 0.5rem",
                  borderRadius: "4px",
                  boxShadow: "1.5px 1.5px 0px #231f1d",
                  lineHeight: 1,
                  marginTop: "0.15rem",
                }}
              >
                {step.n}
              </span>
              <div>
                <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.25rem", color: "#1a1715" }}>
                  {step.title}
                </h3>
                <p style={{ fontSize: "0.92rem", lineHeight: 1.6, color: "#575147", margin: 0 }}>{step.body}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
