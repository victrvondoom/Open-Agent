import { apertureColors } from "@/lib/aperture/tokens";

// Low-tier / reduced-motion / pre-hydration substitute for the R3F scene --
// same chaos -> order color language and composition, rendered as a static
// SVG so it costs nothing to paint and never stutters.
export default function ApertureFallback() {
  return (
    <div
      aria-hidden
      style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}
    >
      <svg width="100%" height="100%" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1200 800">
        <defs>
          <linearGradient id="ap-facet-light" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#faf6ee" />
          </linearGradient>
          <linearGradient id="ap-facet-cream" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fbf7ef" />
            <stop offset="100%" stopColor="#f0e7d8" />
          </linearGradient>
        </defs>
        <rect width="1200" height="800" fill="#f7f4ec" />
        <polygon
          points="600,260 720,330 700,470 560,500 480,410 520,300"
          fill="url(#ap-facet-light)"
          stroke="#231f1d"
          strokeWidth="2"
        />
        <polygon
          points="600,260 700,470 520,300"
          fill="url(#ap-facet-cream)"
          stroke="#231f1d"
          strokeWidth="1.5"
        />
        <line x1="600" y1="260" x2="700" y2="470" stroke="#231f1d" strokeWidth="1.5" />
        <line x1="720" y1="330" x2="560" y2="500" stroke="#231f1d" strokeWidth="1.5" />
        {Array.from({ length: 14 }).map((_, i) => (
          <circle
            key={`chaos-${i}`}
            cx={140 + (i % 7) * 34 + Math.sin(i) * 12}
            cy={340 + Math.floor(i / 7) * 60 + Math.cos(i) * 10}
            r={2.5}
            fill="#d97706"
            stroke="#231f1d"
            strokeWidth="0.8"
          />
        ))}
        {Array.from({ length: 16 }).map((_, i) => (
          <circle
            key={`order-${i}`}
            cx={820 + (i % 8) * 30}
            cy={380 + Math.floor(i / 8) * 26}
            r={2.2}
            fill="#0284c7"
            stroke="#231f1d"
            strokeWidth="0.8"
          />
        ))}
      </svg>
    </div>
  );
}
