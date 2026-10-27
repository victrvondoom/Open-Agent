import Link from "next/link";
import { DOMAINS } from "@/lib/aperture/tokens";

export default function Footer() {
  return (
    <footer
      style={{
        position: "relative",
        zIndex: 1,
        borderTop: "2px solid #231f1d",
        backgroundColor: "#fcfaf5",
        padding: "3.5rem 1.5rem 2.5rem",
        fontFamily: "var(--font-mono)",
        fontSize: "0.75rem",
        color: "var(--bone)",
      }}
    >
      <div style={{ maxWidth: "1100px", margin: "0 auto", display: "flex", flexWrap: "wrap", gap: "2.5rem", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span style={{ letterSpacing: "0.08em", fontWeight: 900, fontSize: "0.95rem" }}>RECLAIM</span>
            <span style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem", borderRadius: "3px", background: "#fef3c7", color: "#92400e", fontWeight: 700, border: "1px solid #231f1d" }}>Voice Flow</span>
            <span style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem", borderRadius: "3px", background: "#ede9fe", color: "#5b21b6", fontWeight: 800, border: "1px solid #231f1d" }}>Open Agent Hackathon</span>
          </div>
          <div style={{ color: "#b45309", fontSize: "0.75rem", fontWeight: 700, marginBottom: "0.4rem" }}>
            From problem to proof to resolution &middot; Built for Open Agent Hackathon
          </div>
          <div style={{ color: "#575147", maxWidth: "300px", lineHeight: 1.6, fontWeight: 500 }}>
            Universal Evidence-to-Action Operating System for consumer claims, refunds, and regulatory dispute workflows.
          </div>
        </div>
        <div style={{ display: "flex", gap: "3rem", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <span style={{ opacity: 0.5, marginBottom: "0.25rem" }}>ACTION FABRIC</span>
            <Link href="/dashboard/connectors" className="aperture-nav-link">Connectors &amp; Approval</Link>
            <Link href="/dashboard/text-splitter" className="aperture-nav-link">Regulation Splitter</Link>
            <Link href="/dashboard/decision-optimizer" className="aperture-nav-link">Decision Optimizer</Link>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <span style={{ opacity: 0.5, marginBottom: "0.25rem" }}>PLATFORM</span>
            <Link href="/dashboard" className="aperture-nav-link">Dashboard</Link>
            <Link href="/dashboard/new" className="aperture-nav-link">New Claim Intake</Link>
          </div>
        </div>
      </div>
      <div style={{ maxWidth: "1100px", margin: "2rem auto 0", opacity: 0.6, fontSize: "0.72rem" }}>
        &copy; {new Date().getFullYear()} RECLAIM &middot; 🏆 Built for Open Agent Hackathon. All rights reserved.
      </div>
    </footer>
  );
}
