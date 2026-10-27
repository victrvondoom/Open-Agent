// Design tokens for the Aperture landing page ((marketing) route group only).
// Scoped deliberately separate from the dashboard's --proxy-* tokens in
// app/globals.css -- this page has its own chaos/order narrative palette.

export const apertureColors = {
  void: "#f7f4ec",
  ink: "#f4ede2",
  ember: "#ea580c",
  cyan: "#0284c7",
  violet: "#7c3aed",
  bone: "#1a1715",
} as const;

export const DOMAINS = [
  { key: "banking", label: "Banking" },
  { key: "health_insurance", label: "Health Insurance" },
  { key: "airlines", label: "Airlines" },
  { key: "telecom", label: "Telecom" },
  { key: "ecommerce", label: "E-Commerce" },
  { key: "government", label: "Government" },
  { key: "housing", label: "Housing" },
  { key: "healthcare", label: "Healthcare" },
] as const;

export const LIFECYCLE_STEPS = [
  { n: "01", title: "Whisper (Voice Flow)", body: "Whisper or speak your dispute naturally; Voice Flow cleanses filler words, normalizes statutory terms, and streams clean claim telemetry." },
  { n: "02", title: "Authenticate & Gate", body: "Every transcript and document carries a verified caller identity before it touches a domain agent." },
  { n: "03", title: "Route Specialists", body: "Domain classification picks the exact regulatory specialist -- or cross-domain council -- your query needs." },
  { n: "04", title: "Retrieve Precedent", body: "Vector + graph lookups pull authoritative statutes, ombudsman rulings, and case law." },
  { n: "05", title: "Enforce Evidence", body: "Voice claims are cross-checked and grounded against legal policy before shaping the outcome." },
  { n: "06", title: "Solve & Draft", body: "Specialist agents draft ready-to-file statutory notices, compensation calculations, and resolution strategies." },
] as const;
