"use client";

import Link from "next/link";

export default function Nav() {
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        backgroundColor: "#fcfaf5",
        borderBottom: "2px solid #231f1d",
        boxShadow: "0 2px 0px rgba(35, 31, 29, 0.05)",
      }}
    >
      <div
        style={{
          background: "#231f1d",
          color: "#fef3c7",
          padding: "0.4rem 1rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "0.6rem",
          fontFamily: "var(--font-mono)",
          fontSize: "0.72rem",
          fontWeight: 700,
          letterSpacing: "0.04em",
          borderBottom: "1.5px solid #3d3632",
          width: "100%",
        }}
      >
        <span
          style={{
            background: "#f59e0b",
            color: "#1c1917",
            padding: "0.1rem 0.5rem",
            borderRadius: "3px",
            fontSize: "0.65rem",
            fontWeight: 900,
            letterSpacing: "0.06em",
          }}
        >
          🏆 HACKATHON
        </span>
        <span>
          Built for Open Agent Hackathon &mdash; Voice-First Autonomous Consumer Justice
        </span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.75rem 1.75rem",
          width: "100%",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.95rem", letterSpacing: "0.08em", color: "var(--bone)", fontWeight: 900 }}>
              RECLAIM
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.65rem",
                padding: "0.15rem 0.5rem",
                borderRadius: "4px",
                background: "#fef3c7",
                color: "#92400e",
                fontWeight: 700,
                border: "1.5px solid #231f1d",
                boxShadow: "1px 1px 0px #231f1d",
                letterSpacing: "0.04em",
              }}
            >
              Voice Flow
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.65rem",
                padding: "0.15rem 0.5rem",
                borderRadius: "4px",
                background: "#ede9fe",
                color: "#5b21b6",
                fontWeight: 800,
                border: "1.5px solid #231f1d",
                boxShadow: "1px 1px 0px #231f1d",
                letterSpacing: "0.04em",
              }}
            >
              Open Agent Hackathon
            </span>
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.68rem", color: "#b45309", letterSpacing: "0.03em", fontWeight: 700 }}>
            From problem to proof to resolution &middot; Universal Evidence &amp; Action Operating System
          </span>
        </div>
        <nav style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
          <a href="#announcement" className="aperture-nav-link" style={{ fontWeight: 600 }}>RECLAIM Vision</a>
          <a href="#how-it-works" className="aperture-nav-link" style={{ fontWeight: 600 }}>How it works</a>
          <Link href="/dashboard/connectors" className="aperture-nav-link" style={{ fontWeight: 700, color: "#92400e" }}>Action Fabric</Link>
          <Link href="/dashboard/text-splitter" className="aperture-nav-link" style={{ fontWeight: 600 }}>Splitter Inspector</Link>
          <Link
            href="/dashboard"
            className="aperture-nav-link"
            style={{ fontWeight: 600, opacity: 0.9 }}
          >
            Dashboard
          </Link>
          <Link
            href="/dashboard"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.78rem",
              padding: "0.5rem 1rem",
              border: "2px solid #231f1d",
              borderRadius: "6px",
              color: "#1a1715",
              background: "#ffffff",
              fontWeight: 800,
              boxShadow: "2px 2px 0px #231f1d",
              textDecoration: "none",
              transition: "all 0.1s ease",
            }}
          >
            Enter Platform &rarr;
          </Link>
        </nav>
      </div>
    </header>
  );
}
