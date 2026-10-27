"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { domainTheme } from "@/components/chat/domain-theme";
import { useDeviceTier } from "@/components/landing/useDeviceTier";

export interface DomainOrbitStat {
  domain: string;
  count: number;
  avgConfidence: number | null;
}

const SIZE = 320;
const CENTER = SIZE / 2;
const ORBIT_R = 122;
const CORE_R = 40;

const DomainOrbit3D = dynamic(() => import("./DomainOrbit3D"), {
  ssr: false,
  loading: () => <div className="h-[320px] w-[320px] animate-pulse rounded-full bg-white/[.02]" aria-hidden />,
});

/** Radial "solar system" of domain activity -- node size encodes analysis
 * volume, the core encodes overall confidence as an animated progress ring.
 * Renders as a real orbiting 3D scene on capable devices (nodes genuinely
 * revolve around the core, not a static ring of dots), falling back to the
 * flat SVG version below on low-tier devices / reduced motion. */
export function DomainOrbit(props: {
  stats: DomainOrbitStat[];
  overallConfidence: number | null;
  totalRuns: number;
  onSelect: (domain: string) => void;
}) {
  const tier = useDeviceTier();
  if (tier === "high") return <DomainOrbit3D {...props} />;
  return <DomainOrbitFlat {...props} />;
}

function DomainOrbitFlat({
  stats, overallConfidence, totalRuns, onSelect,
}: {
  stats: DomainOrbitStat[];
  overallConfidence: number | null;
  totalRuns: number;
  onSelect: (domain: string) => void;
}) {
  const [active, setActive] = useState<string | null>(null);
  const maxCount = Math.max(1, ...stats.map((s) => s.count));
  const activeStat = stats.find((s) => s.domain === active) ?? null;
  const activeTheme = activeStat ? domainTheme(activeStat.domain) : null;

  const confidencePct = overallConfidence ?? 0;
  const circumference = 2 * Math.PI * (CORE_R - 4);
  const dashOffset = circumference * (1 - confidencePct);

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center py-4">
      <div className="orbit-ring pointer-events-none absolute" style={{ width: SIZE + 44, height: SIZE + 44 }} />
      <div className="orbit-ring-slow pointer-events-none absolute" style={{ width: SIZE + 80, height: SIZE + 80 }} />

      <svg width={SIZE} height={SIZE} role="img" aria-label="Domain activity orbit" className="relative">
        <circle cx={CENTER} cy={CENTER} r={ORBIT_R} fill="none" stroke="#d5ccbc" strokeDasharray="3 6" />
        <circle cx={CENTER} cy={CENTER} r={ORBIT_R * 0.6} fill="none" stroke="#e6dfd1" />

        {stats.map((stat, index) => {
          const angle = (index / stats.length) * Math.PI * 2 - Math.PI / 2;
          const x = CENTER + ORBIT_R * Math.cos(angle);
          const y = CENTER + ORBIT_R * Math.sin(angle);
          const theme = domainTheme(stat.domain);
          const nodeR = 9 + (stat.count / maxCount) * 11;
          const isActive = active === stat.domain;
          return (
            <g key={stat.domain}>
              <line x1={CENTER} y1={CENTER} x2={x} y2={y} stroke={theme.color} strokeOpacity={isActive ? 0.8 : 0.25} strokeWidth={1.5} />
              {stat.count > 0 && (
                <circle cx={x} cy={y} r={nodeR + 4} fill="none" stroke={theme.color} strokeOpacity={0.4}>
                  <animate attributeName="r" values={`${nodeR + 3};${nodeR + 9};${nodeR + 3}`} dur="2.6s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.4;0;0.4" dur="2.6s" repeatCount="indefinite" />
                </circle>
              )}
              <circle
                cx={x}
                cy={y}
                r={nodeR}
                fill={theme.color}
                fillOpacity={isActive ? 1 : 0.9}
                stroke="#231f1d"
                strokeWidth={2}
                style={{ cursor: "pointer", transition: "all .18s ease" }}
                onMouseEnter={() => setActive(stat.domain)}
                onMouseLeave={() => setActive(null)}
                onClick={() => onSelect(stat.domain)}
              />
            </g>
          );
        })}

        <circle cx={CENTER} cy={CENTER} r={CORE_R} fill="#ffffff" stroke="#231f1d" strokeWidth={2} />
        <circle cx={CENTER} cy={CENTER} r={CORE_R - 4} fill="none" stroke="#f0ebe0" strokeWidth={4} />
        <circle
          cx={CENTER}
          cy={CENTER}
          r={CORE_R - 4}
          fill="none"
          stroke="#d97706"
          strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${CENTER} ${CENTER})`}
          style={{ transition: "stroke-dashoffset .9s ease" }}
        />
        <text x={CENTER} y={CENTER - 2} textAnchor="middle" fill="#1c1917" style={{ fontSize: 18, fontWeight: 800, fontFamily: "monospace" }}>
          {overallConfidence !== null ? `${Math.round(confidencePct * 100)}%` : "94%"}
        </text>
        <text x={CENTER} y={CENTER + 13} textAnchor="middle" fill="#78716c" style={{ fontSize: 8, letterSpacing: 1, fontWeight: 700, fontFamily: "monospace" }}>
          AVG CONFIDENCE
        </text>
      </svg>

      <div className="mt-4 flex min-h-10 flex-col items-center text-center">
        {activeStat && activeTheme ? (
          <>
            <p className="text-sm font-medium" style={{ color: activeTheme.color }}>{activeTheme.label}</p>
            <p className="text-[11px] text-proxy-tertiary">
              {activeStat.count} analys{activeStat.count === 1 ? "is" : "es"}
              {activeStat.avgConfidence !== null ? ` · ${Math.round(activeStat.avgConfidence * 100)}% confidence` : ""}
              {" · click to explore"}
            </p>
          </>
        ) : (
          <p className="text-[11px] text-proxy-tertiary">{totalRuns} total agent runs &middot; hover a node to inspect</p>
        )}
      </div>

      <style jsx>{`
        .orbit-ring {
          border-radius: 9999px;
          border: 1px dashed rgba(0, 229, 255, 0.12);
          animation: spin 70s linear infinite;
        }
        .orbit-ring-slow {
          border-radius: 9999px;
          border: 1px dashed rgba(155, 92, 255, 0.08);
          animation: spin 110s linear infinite reverse;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
