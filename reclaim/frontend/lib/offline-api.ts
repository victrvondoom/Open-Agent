import { SYNTHETIC_SCENARIOS, scenarioFor, syntheticClassify, syntheticMultiDomain } from "@/lib/synthetic-scenarios";

// Offline "demo backend". When the real API can't be reached (or errors), the
// patched fetch below answers every /api/v1 route from a small database kept in
// localStorage, so every page renders real-looking, *changing* data: uploads add
// documents, analyses add cases/appeals/events, status changes persist, and a
// live feed keeps appending activity. Nothing here is a static page.

type Json = Record<string, any>;
interface Db {
  cases: Json[];
  documents: Json[];
  appeals: Json[];
  events: Json[];
  lastTick: number;
}

const KEY = "reclaim:offline-db-v2";
const uid = () => Math.random().toString(36).slice(2, 10);
const iso = (msAgo = 0) => new Date(Date.now() - msAgo).toISOString();
const DAY = 86400000;

// Case volume per domain: deliberately uneven, like a real complaint mix.
const VOLUME: Record<string, number> = {
  banking: 160, telecom: 125, ecommerce: 110, airlines: 100, health_insurance: 72, housing: 38, government: 11, healthcare: 2,
};

const VARIANTS: Record<string, { institutions: string[]; issues: Array<[string, string]> }> = {
  banking: {
    institutions: ["Metro National Bank", "Union Crest Bank", "Bharat Savings Bank", "Coastal Trust Bank", "Apex Finserve", "Sundaram Co-operative Bank"],
    issues: [["Duplicate UPI debit not reversed", "A UPI payment of Rs {a} was debited twice and the bank has not reversed the second debit."], ["Unauthorised card transaction", "A card transaction of Rs {a} that I never made appeared on my statement and the bank rejected my dispute."], ["Loan prepayment charge dispute", "The bank charged a prepayment penalty of Rs {a} on a floating-rate loan."], ["ATM cash not dispensed", "The ATM debited Rs {a} but dispensed no cash; the refund is overdue."], ["Chargeback refused", "The bank refused a chargeback of Rs {a} for a service that was never delivered."], ["Minimum balance penalty", "Penalty of Rs {a} was levied on a zero-balance account."]],
  },
  telecom: {
    institutions: ["Connectel Mobile", "Nexa Broadband", "BlueWave Telecom", "Zenith Fibre", "Orbit Wireless"],
    issues: [["Billed after plan cancellation", "I am still being billed Rs {a} a month for a plan I cancelled."], ["Number porting delayed", "My mobile number port request has been pending for over two weeks."], ["Broadband outage, no rebate", "My broadband has been down for 9 days and no rental rebate was given."], ["Roaming charges mis-billed", "I was charged Rs {a} for international roaming I had not activated."], ["Value-added service auto-activated", "A paid caller-tune service of Rs {a} was activated without my consent."]],
  },
  ecommerce: {
    institutions: ["ShopKart Marketplace", "Urbancart", "TrendBazaar", "QuickMart Online", "HomeNest Store", "GadgetGrid"],
    issues: [["Counterfeit product delivered", "The branded item I ordered for Rs {a} is counterfeit and the seller refuses a return."], ["Refund stuck after return pickup", "My return was picked up but the refund of Rs {a} has not been credited."], ["Defective appliance, warranty denied", "The appliance stopped working within 3 months and warranty service was denied."], ["Wrong item delivered", "I received the wrong product and the platform keeps closing my ticket."], ["Order cancelled after payment", "My order of Rs {a} was cancelled by the seller after payment."], ["Delivery marked complete, not received", "The parcel is marked delivered but I never received it."]],
  },
  airlines: {
    institutions: ["SkyJet Airways", "IndoAir", "Horizon Airlines", "AeroLink", "Falcon Air"],
    issues: [["Cancelled flight, refund stalled", "My flight was cancelled and the airline offered only a voucher instead of the Rs {a} refund."], ["Baggage lost in transit", "My checked baggage was lost and the compensation offered is far below the limit."], ["Denied boarding despite confirmed ticket", "I was denied boarding despite a confirmed ticket and received no compensation."], ["Long delay, no meals provided", "A 5-hour delay occurred and no meals or refreshments were provided."], ["Refund of taxes not processed", "Airport taxes of Rs {a} on an unused ticket have not been refunded."]],
  },
  health_insurance: {
    institutions: ["Star Shield Health Insurance", "CarePlus Insurance", "LifeGuard Health", "Vitalis Insurance"],
    issues: [["Claim denied as pre-existing", "My claim of Rs {a} was denied as a pre-existing condition after 5 years of continuous cover."], ["Cashless pre-authorisation refused", "Cashless approval was refused at the hospital and I had to pay Rs {a} upfront."], ["Partial settlement with deductions", "The insurer deducted Rs {a} as 'non-payable items' without a breakdown."], ["Renewal premium hike", "My renewal premium rose sharply after a single claim."], ["Claim delayed beyond 30 days", "My reimbursement claim has been pending for 45 days."]],
  },
  housing: {
    institutions: ["Horizon Realty Developers", "GreenArc Builders", "Landmark Estates", "Skyline Infra"],
    issues: [["Possession delayed beyond RERA date", "Possession of my flat is delayed by {m} months and no interest is offered."], ["Security deposit not returned", "My landlord has withheld a deposit of Rs {a} after move-out."], ["Carpet area shortfall", "The delivered carpet area is lower than the agreement for sale."], ["Maintenance overcharge", "The society is charging maintenance above the agreed rate."]],
  },
  government: {
    institutions: ["Regional Passport Office", "District Revenue Office", "State Transport Department"],
    issues: [["Passport renewal pending 90 days", "My passport renewal has been under review for 90 days."], ["Certificate application stuck", "My income certificate application has been pending beyond the citizen charter timeline."], ["Pension credit delayed", "My pension has not been credited for two months."]],
  },
  healthcare: {
    institutions: ["CityCare Multispeciality Hospital", "Sunrise Diagnostics"],
    issues: [["Overcharged hospital bill", "The hospital bill exceeded the estimate by Rs {a} with no itemisation."], ["Discharge summary withheld", "The hospital is withholding my discharge summary until an unexplained balance is paid."]],
  },
};

function rng(seedNum: number) {
  let t = seedNum;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function pickStatus(rand: () => number, ageDays: number): string {
  const r = rand();
  if (ageDays < 4) return r < 0.4 ? "intake" : r < 0.75 ? "analyzing" : "review_required";
  if (ageDays < 20) return r < 0.2 ? "review_required" : r < 0.45 ? "ready_for_approval" : r < 0.8 ? "submitted" : "resolved";
  return r < 0.52 ? "resolved" : r < 0.72 ? "submitted" : r < 0.82 ? "closed" : r < 0.9 ? "ready_for_approval" : "review_required";
}

function seed(): Db {
  const db: Db = { cases: [], documents: [], appeals: [], events: [], lastTick: Date.now() };
  const rand = rng(20260);
  let n = 0;
  Object.entries(VOLUME).forEach(([domain, count]) => {
    const s = scenarioFor(domain)!;
    const v = VARIANTS[domain];
    for (let k = 0; k < count; k++) {
      n++;
      // Recent cases are likelier than old ones (rand^1.6 skews towards "now").
      const ageDays = Math.floor(Math.pow(rand(), 1.6) * 180);
      const created = ageDays * DAY + Math.floor(rand() * DAY);
      const [title, tpl] = v.issues[Math.floor(rand() * v.issues.length)];
      const amount = (Math.round((1500 + rand() * 48000) / 50) * 50).toLocaleString("en-IN");
      const institution = v.institutions[Math.floor(Math.pow(rand(), 1.8) * v.institutions.length)];
      const status = pickStatus(rand, ageDays);
      const conf = Number((0.55 + rand() * 0.4).toFixed(2));
      const id = `case-${domain}-${String(k + 1).padStart(3, "0")}`;
      const summary = tpl.replace("{a}", amount).replace("{m}", String(6 + Math.floor(rand() * 20)));
      const multi = rand() < 0.14;
      db.cases.push({
        id, user_id: "device", domain, title, institution_name: institution, summary, jurisdiction: "IN", status,
        created_at: iso(created), updated_at: iso(Math.max(0, created - rand() * 9 * DAY)), avg_confidence: status === "intake" ? null : conf,
        run_count: status === "intake" ? 0 : 1 + Math.floor(rand() * 3), completed_runs: status === "intake" ? 0 : 1 + Math.floor(rand() * 2),
        domains_involved: multi ? [domain, SYNTHETIC_SCENARIOS[Math.floor(rand() * 8)].domain] : [domain],
      });
      db.events.push({ id: `e${n}a`, case_id: id, event_type: "case_created", title: `Case opened: ${title}`, body: summary, actor: "user", created_at: iso(created) });
      if (status !== "intake") {
        db.events.push({ id: `e${n}b`, case_id: id, event_type: "analysis_completed", title: `Multi-agent analysis completed (${Math.round(conf * 100)}% success estimate)`, body: s.strategy[Math.floor(rand() * s.strategy.length)], actor: "agent", created_at: iso(created - 40 * 60000) });
      }
      const docCount = Math.floor(rand() * 3);
      for (let j = 0; j < docCount; j++) {
        const name = s.missingDocs[(k + j) % s.missingDocs.length];
        const docId = `doc-${id}-${j}`;
        db.documents.push({
          id: docId, document_id: docId, case_id: id, filename: `${name.toLowerCase().replace(/[^a-z0-9]+/g, "_")}_${String(k + 1).padStart(3, "0")}.pdf`,
          mime_type: "application/pdf", size_bytes: Math.floor(40000 + rand() * 900000),
          text_extract: `${name} — ${institution}. ${s.clauses[j % s.clauses.length]}.`, document_type: j === 0 ? "evidence" : "correspondence", domain,
          indexed: rand() > 0.05, chunks_indexed: 3 + Math.floor(rand() * 22), created_at: iso(Math.max(0, created - (j + 1) * 3600000)),
        });
      }
      if (status !== "intake" && status !== "analyzing" && rand() < 0.78) {
        const astatus = status === "resolved" ? (rand() < 0.7 ? "resolved" : "sent") : status === "submitted" ? (rand() < 0.6 ? "sent" : "escalated") : rand() < 0.8 ? "draft" : "sent";
        db.appeals.push({
          id: `appeal-${id}`, case_id: id, user_id: "device", version: 1 + Math.floor(rand() * 3), title: s.letterSubject, domain, document_type: "appeal_letter", status: astatus,
          content: `To the Grievance Officer, ${institution}\n\nSubject: ${s.letterSubject}\n\n${summary} ${s.story[2]}\n\nEvidence attached: ${s.missingDocs.slice(0, 2).join("; ")}.\nReferences: ${s.regulations.join("; ")}.`,
          created_at: iso(Math.max(0, created - 2 * 3600000)),
        });
        db.events.push({ id: `e${n}c`, case_id: id, event_type: "appeal_generated", title: `Appeal drafted: ${s.letterSubject}`, body: null, actor: "agent", created_at: iso(Math.max(0, created - 2 * 3600000)) });
      }
    }
  });
  return db;
}

function load(): Db {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Db;
  } catch { /* fall through to a fresh seed */ }
  const db = seed();
  save(db);
  return db;
}
function save(db: Db) {
  try { window.localStorage.setItem(KEY, JSON.stringify(db)); } catch { /* storage unavailable: state lives for this call only */ }
}

const LIVE_EVENTS = [
  ["precedent_found", "New precedent matched to an open case", "Consumer Commission order cited in the knowledge graph."],
  ["evidence_scored", "Evidence score updated", "Document relevance recalculated after re-indexing."],
  ["deadline_alert", "Statutory deadline approaching", "Institution reply window closes in 48 hours."],
  ["institution_pattern", "Institution pattern detected", "Similar complaints against this institution rose this week."],
  ["review_passed", "Review agent approved a draft", "All citations verified against retrieved sources."],
];

function tick(db: Db) {
  const now = Date.now();
  if (now - db.lastTick < 25000 || !db.cases.length) return;
  const n = Math.min(3, Math.floor((now - db.lastTick) / 25000));
  for (let i = 0; i < n; i++) {
    const c = db.cases[Math.floor(Math.random() * db.cases.length)];
    const [type, title, body] = LIVE_EVENTS[Math.floor(Math.random() * LIVE_EVENTS.length)];
    db.events.push({ id: uid(), case_id: c.id, event_type: type, title: `${title}: ${c.title}`, body, actor: "agent", created_at: iso(i * 1000) });
  }
  db.events = db.events.slice(-3000);
  db.lastTick = now;
}

function counts<T>(items: T[], key: (t: T) => string) {
  const m = new Map<string, number>();
  items.forEach((x) => m.set(key(x), (m.get(key(x)) ?? 0) + 1));
  return [...m.entries()].map(([k, count]) => ({ k, count }));
}

function summary(db: Db) {
  const resolved = db.cases.filter((c) => c.status === "resolved").length;
  return {
    totals: { cases: db.cases.length, appeals: db.appeals.length, documents: db.documents.length, domains_engaged: new Set(db.cases.map((c) => c.domain)).size },
    resolution_rate: db.cases.length ? Number((resolved / db.cases.length).toFixed(2)) : null,
    domain_breakdown: counts(db.cases, (c) => c.domain).map(({ k, count }) => ({ domain: k, count })),
    appeal_status_breakdown: counts(db.appeals, (a) => a.status).map(({ k, count }) => ({ status: k, count })),
    case_status_breakdown: counts(db.cases, (c) => c.status).map(({ k, count }) => ({ status: k, count })),
    recent_activity: [...db.events].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 15),
    generated_at: iso(),
  };
}

function graphFor(db: Db, caseId: string) {
  const c = db.cases.find((x) => x.id === caseId) ?? db.cases[0];
  const s = scenarioFor(c.domain);
  const nodes: Json[] = [
    { id: "you", kind: "you", label: "You", detail: { role: "Claimant" } },
    { id: `domain-${c.domain}`, kind: "domain", label: c.domain.replace("_", " ") },
    { id: `inst-${c.institution_name}`, kind: "institution", label: c.institution_name ?? "Institution" },
    { id: c.id, kind: "case", label: c.title, detail: { status: c.status, confidence: c.avg_confidence } },
  ];
  const edges: Json[] = [
    { source: "you", target: c.id }, { source: c.id, target: `domain-${c.domain}` }, { source: c.id, target: `inst-${c.institution_name}` },
  ];
  db.documents.filter((d) => d.case_id === c.id).forEach((d) => {
    nodes.push({ id: d.document_id, kind: "document", label: d.filename, detail: { chunks: d.chunks_indexed } });
    edges.push({ source: c.id, target: d.document_id });
  });
  db.appeals.filter((a) => a.case_id === c.id).forEach((a) => {
    nodes.push({ id: a.id, kind: "appeal", label: a.title, detail: { status: a.status } });
    edges.push({ source: c.id, target: a.id });
  });
  (s?.regulations ?? []).forEach((r, i) => {
    nodes.push({ id: `reg-${c.id}-${i}`, kind: "regulation", label: r });
    edges.push({ source: c.id, target: `reg-${c.id}-${i}` });
  });
  return { c, s, nodes, edges };
}

function chatAnswer(message: string) {
  const res = syntheticMultiDomain(message);
  const d = res.domains_analyzed[0];
  const s = scenarioFor(d)!;
  const answer = [
    `**${s.title}** (${d.replace("_", " ")})`,
    `Based on indexed evidence, ${s.story[2]}`,
    `**Rules:** ${s.regulations.join("; ")}.`,
    `**Next steps:** ${s.strategy.map((x, i) => `${i + 1}) ${x}`).join(" ")}`,
    `**Escalation:** ${s.escalation.join(" → ")}.`,
  ].join("\n\n");
  return {
    answer, question: message,
    citations: [s.citation.title],
    structured_citations: [{ title: s.citation.title, authority: s.citation.authority, url: null, retrieved_chunk: s.clauses[0], confidence: 0.9 }],
    graph_patterns: [{ pattern: `Repeated ${s.title.toLowerCase()} disputes at ${s.institution}`, confidence: 0.74 }],
    agent_trace: res.per_domain_results[d].agent_trace,
  };
}

function connectors() {
  return [
    {
      connector_id: "reclaim.connectors.aviation_refund", name: "Aviation Refund Connector", version: "1.2.0", domain: "airlines",
      description: "Files statutory refund claims with airlines under DGCA CAR Section 3 Series M Part IV.", execution_modes: ["sandbox", "live"],
      capabilities: [{ action_id: "submit_airline_claim", name: "Submit airline refund claim", description: "Prepares and files a refund claim.", is_write: true, requires_human_approval: true, is_reversible: false, risk_level: "medium" }],
    },
    {
      connector_id: "reclaim.connectors.email_delivery", name: "Email Delivery Connector", version: "1.0.3", domain: "general",
      description: "Dispatches formal complaint emails to nodal officers.", execution_modes: ["sandbox", "live"],
      capabilities: [{ action_id: "send_complaint_email", name: "Send complaint email", description: "Sends a formal dispute notice.", is_write: true, requires_human_approval: true, is_reversible: false, risk_level: "low" }],
    },
  ];
}

function route(method: string, path: string, body: Json, db: Db): { status: number; data: any } | null {
  const [p, qs = ""] = path.split("?");
  const q = new URLSearchParams(qs);
  const m = (re: RegExp) => p.match(re);
  let r: RegExpMatchArray | null;

  if (p === "/health" || p === "/health/live") {
    return { status: 200, data: p === "/health/live" ? { status: "ok" } : {
      status: "ok", service: "reclaim-api", environment: "demo",
      vector_store: { status: "ok", backend: "local-index", collections: 8, total_points: 1200 + db.documents.length * 14 },
      graph_store: { status: "ok", backend: "in-memory-graph", events: db.events.length },
      supabase: { status: "ok" }, gemini: { status: "ok" },
      llm: { provider: "demo", status: "ok", reasoning_model: "reasoning-v1", embedding_model: "embed-v1" },
      redis: { status: "ok" }, web_search: { status: "ok" },
    } };
  }
  if (p === "/cases/analyses" && method === "GET") return { status: 200, data: [...db.cases].sort((a, b) => b.created_at.localeCompare(a.created_at)) };
  if ((r = m(/^\/cases\/([^/]+)\/status$/)) && method === "PATCH") {
    const c = db.cases.find((x) => x.id === r![1]); if (!c) return { status: 404, data: { detail: "not found" } };
    c.status = body.status; c.updated_at = iso();
    db.events.push({ id: uid(), case_id: c.id, event_type: "status_changed", title: `Status changed to ${body.status}`, body: c.title, actor: "user", created_at: iso() });
    return { status: 200, data: c };
  }
  if (p === "/cases" && method === "POST") {
    const c: Json = { id: uid() + uid(), user_id: "device", status: "intake", created_at: iso(), updated_at: iso(), avg_confidence: null, run_count: 0, completed_runs: 0, domains_involved: [body.domain], ...body };
    db.cases.push(c);
    db.events.push({ id: uid(), case_id: c.id, event_type: "case_created", title: `Case opened: ${c.title}`, body: c.summary, actor: "user", created_at: iso() });
    return { status: 200, data: c };
  }
  if (p === "/cases/seed-demo") return { status: 200, data: { message: "Demo data ready", count: db.cases.length } };
  if (p === "/intelligence/classify") return { status: 200, data: syntheticClassify(body.query ?? "") };
  if (p === "/intelligence/cases/multi-domain" && method === "POST") {
    const res = syntheticMultiDomain(body.case_summary ?? "");
    const s = scenarioFor(res.primary_domain)!;
    const id = body.case_id ?? uid();
    if (!db.cases.some((c) => c.id === id)) {
      db.cases.push({ id, user_id: "device", domain: s.domain, title: s.title, institution_name: s.institution, summary: body.case_summary, jurisdiction: "IN", status: "ready_for_approval", created_at: iso(), updated_at: iso(), avg_confidence: s.probability, run_count: 1, completed_runs: 1, domains_involved: res.domains_analyzed });
      db.appeals.push({ id: uid(), case_id: id, user_id: "device", version: 1, title: s.letterSubject, content: res.per_domain_results[s.domain].final_report ?? "", status: "draft", document_type: "appeal_letter", domain: s.domain, created_at: iso() });
      db.events.push({ id: uid(), case_id: id, event_type: "analysis_completed", title: `Analysis completed: ${s.title}`, body: s.strategy[0], actor: "agent", created_at: iso() });
    }
    return { status: 200, data: res };
  }
  if (p === "/intelligence/search") {
    const text = String(body.query ?? "");
    const doms = syntheticClassify(text).candidates.map((c) => c.domain);
    const list = doms.length ? SYNTHETIC_SCENARIOS.filter((s) => doms.includes(s.domain)) : SYNTHETIC_SCENARIOS.slice(0, 4);
    const results = list.flatMap((s) => s.clauses.map((clause, i) => {
      const sim = Math.max(0.55, 0.93 - i * 0.07 - Math.random() * 0.04);
      return {
        id: `${s.domain}-${i}`, score: sim, text: `${clause}. Source: ${s.regulations[i % s.regulations.length]}.`, domain: s.domain,
        metadata: { title: s.citation.title, authority: s.citation.authority, section: s.citation.section },
        evidence_scores: { similarity_score: sim, authority_score: 0.9, legal_weight: 0.85, freshness_score: 0.7, confidence: 0.88, overall_evidence_score: Number(((sim + 0.9 + 0.85 + 0.7) / 4).toFixed(2)) },
      };
    })).sort((a, b) => b.score - a.score).slice(0, body.top_k_overall ?? 15);
    return { status: 200, data: { query: text, domains_searched: [...new Set(results.map((x) => x.domain))], results, total_hits: results.length } };
  }
  if (p === "/case/chat") return { status: 200, data: chatAnswer(body.message ?? "") };
  if (p === "/appeals" && method === "GET") return { status: 200, data: db.appeals };
  if ((r = m(/^\/appeals\/([^/]+)\/status$/)) && method === "PATCH") {
    const a = db.appeals.find((x) => x.id === r![1]); if (!a) return { status: 404, data: { detail: "not found" } };
    a.status = body.status;
    db.events.push({ id: uid(), case_id: a.case_id, event_type: "appeal_status", title: `Appeal marked ${body.status}`, body: a.title, actor: "user", created_at: iso() });
    return { status: 200, data: a };
  }
  if (p === "/upload/documents" && method === "GET") return { status: 200, data: [...db.documents].sort((a, b) => b.created_at.localeCompare(a.created_at)) };
  if ((r = m(/^\/upload\/documents\/([^/]+)$/)) && method === "DELETE") {
    db.documents = db.documents.filter((d) => d.document_id !== r![1]);
    return { status: 200, data: { deleted: true } };
  }
  if (m(/\/signed-url$/)) return { status: 200, data: { signed_url: "data:text/plain;charset=utf-8,Synthetic%20evidence%20document%20preview" } };
  if (p === "/reports/summary") return { status: 200, data: summary(db) };
  if (p === "/reports/events") {
    const limit = Number(q.get("limit") ?? 30), before = q.get("before");
    let ev = [...db.events].sort((a, b) => b.created_at.localeCompare(a.created_at));
    if (before) ev = ev.filter((e) => e.created_at < before);
    return { status: 200, data: ev.slice(0, limit) };
  }
  if ((r = m(/^\/reports\/case\/(.+)$/))) {
    const c = db.cases.find((x) => x.id === r![1]);
    const s = c && scenarioFor(c.domain);
    if (!c || !s) return { status: 200, data: { case: null, appeals: [], documents: [], events: [] } };
    const res = syntheticMultiDomain(c.summary, c.domain).per_domain_results[c.domain];
    return { status: 200, data: {
      case: { id: c.id, domain: c.domain, title: c.title, institution_name: c.institution_name, summary: c.summary, status: c.status },
      appeals: db.appeals.filter((a) => a.case_id === c.id), documents: db.documents.filter((d) => d.case_id === c.id),
      events: db.events.filter((e) => e.case_id === c.id).sort((a, b) => b.created_at.localeCompare(a.created_at)),
      agent_runs: res.agent_trace.map((t, i) => ({ id: `run-${i}`, workflow: t.split(":")[0], status: "completed", output: { summary: t }, created_at: iso(i * 60000) })),
      latest_analysis: {
        research_summary: s.story[2], evidence_summary: `Documents needed: ${s.missingDocs.join(", ")}`, strategy: s.strategy.join(" → "),
        appeal_draft: db.appeals.find((a) => a.case_id === c.id)?.content ?? "", final_report: res.final_report ?? "", review_notes: ["Citations verified", "Deadlines checked"],
        citations: [s.citation.title], agent_trace: res.agent_trace, llm_call_count: 14, embedding_mode: "demo",
      },
    } };
  }
  if (p === "/graph/institution-radar") {
    const byInst = new Map<string, Map<string, number>>();
    db.cases.forEach((c) => {
      const inst = c.institution_name ?? "Unknown";
      const dm = byInst.get(inst) ?? new Map<string, number>();
      dm.set(c.domain, (dm.get(c.domain) ?? 0) + 1);
      byInst.set(inst, dm);
    });
    const rows = [...byInst.entries()].map(([name, dm]) => ({
      institution_name: name,
      total_cases: [...dm.values()].reduce((a, b) => a + b, 0),
      by_domain: [...dm.entries()].map(([domain, case_count]) => ({ domain, case_count })),
    })).sort((a, b) => b.total_cases - a.total_cases);
    return { status: 200, data: rows.slice(0, Number(q.get("limit") ?? 25)) };
  }
  if (p === "/graph/patterns") {
    const s = scenarioFor(q.get("domain") ?? "") ?? SYNTHETIC_SCENARIOS[1];
    return { status: 200, data: s.clauses.map((c, i) => ({ pattern: c, domain: s.domain, institution: q.get("institution_name") ?? s.institution, confidence: 0.82 - i * 0.07 })) };
  }
  if (p === "/graph/similar-cases") {
    const s = scenarioFor(q.get("domain") ?? "") ?? SYNTHETIC_SCENARIOS[1];
    return { status: 200, data: s.story.slice(0, 3).map((t, i) => ({ case_id: `sim-${s.domain}-${i}`, title: `${s.title} (similar #${i + 1})`, summary: t })) };
  }
  if (p === "/graph/institution-graph") {
    const pair = [[q.get("domain"), q.get("institution_name")], [q.get("domain2"), q.get("institution_name2")]].filter(([d]) => d) as string[][];
    const institutions = pair.map(([d, n], index) => {
      const s = scenarioFor(d) ?? SYNTHETIC_SCENARIOS[1];
      return { index, domain: s.domain, institution_name: n || s.institution,
        patterns: s.clauses.map((c, i) => ({ pattern: c, domain: s.domain, institution: n || s.institution, confidence: 0.84 - i * 0.06 })),
        similar_cases: s.story.slice(0, 2).map((t, i) => ({ case_id: `sim-${s.domain}-${i}`, title: `${s.title} #${i + 1}`, summary: t })) };
    });
    const shared = institutions.length > 1 ? [{ type: "pattern", a_i: 0, b_i: 1, text: "Refund delays beyond the statutory window" }] : [];
    return { status: 200, data: { institutions, shared } };
  }
  if (p === "/graph/user/knowledge-footprint" || m(/^\/graph\/citizen\/[^/]+\/profile$/)) {
    const by = counts(db.cases, (c) => c.domain).map(({ k, count }) => ({
      domain: k, case_count: count,
      cases: db.cases.filter((c) => c.domain === k).map((c) => ({ case_id: c.id, title: c.title, created_at: c.created_at, avg_confidence: c.avg_confidence })),
      institutions: [...new Set(db.cases.filter((c) => c.domain === k).map((c) => c.institution_name))],
    }));
    const conf = db.cases.filter((c) => c.avg_confidence != null).map((c) => c.avg_confidence as number);
    const top = [...by].sort((a, b) => b.case_count - a.case_count)[0];
    return { status: 200, data: { user_id: "device", total_cases: db.cases.length, domains_active_in: by.map((x) => x.domain), by_domain: by,
      avg_confidence: conf.length ? Number((conf.reduce((a, b) => a + b, 0) / conf.length).toFixed(2)) : null, most_active_domain: top?.domain ?? null } };
  }
  if ((r = m(/^\/graph\/case\/([^/]+)\/graph$/))) {
    const g = graphFor(db, decodeURIComponent(r[1]));
    return { status: 200, data: { case_id: g.c.id, domain: g.c.domain, nodes: g.nodes, edges: g.edges } };
  }
  if ((r = m(/^\/graph\/case\/([^/]+)\/reasoning-trail$/))) {
    const g = graphFor(db, decodeURIComponent(r[1]));
    return { status: 200, data: { case_id: g.c.id, steps: g.nodes.map((n, index) => ({ index, token: `${n.kind}: ${n.label}`, node_id: n.id })) } };
  }
  if (p === "/connectors") return { status: 200, data: connectors() };
  if ((r = m(/^\/connectors\/([^/]+)\/prepare$/))) {
    const pl = body.payload ?? {};
    const claimed = pl.claim_package?.claimed_amount ?? pl.paid_amount ?? 0;
    return { status: 200, data: {
      prepared_action_id: `prep-${uid()}`, connector_id: r[1], action_id: body.action_id, case_id: body.case_id, requires_human_approval: true,
      approval_state: "pending", summary: `Prepared ${body.action_id} in sandbox mode`,
      summary_for_human: pl.pnr ? `Claim for PNR ${pl.pnr} (${pl.airline}, ${pl.flight_number}): refund plus statutory compensation of ₹${claimed}.` : `Formal complaint email to ${pl.recipient_email}.`,
      consequences: ["Submission is recorded in the audit log", "A copy is saved to the case dossier", "Cannot be recalled after dispatch"],
      payload: pl, reversibility: false, estimated_benefit: claimed } };
  }
  if (p === "/connectors/approve") return { status: 200, data: { approval_token: `appr-${uid()}${uid()}`, approved_at: iso() } };
  if ((r = m(/^\/connectors\/([^/]+)\/execute$/))) {
    db.events.push({ id: uid(), case_id: body.prepared_action?.case_id ?? "case-airlines", event_type: "action_executed", title: "Action Fabric executed an approved action", body: body.prepared_action?.summary_for_human ?? null, actor: "user", created_at: iso() });
    return { status: 200, data: { operation_id: `op-${uid()}`, state: "completed", provider_reference: `SBX-${Date.now().toString().slice(-7)}`, output_data: { acknowledged: true, mode: "sandbox", ticket: `GR-${uid().toUpperCase()}` }, executed_at: iso() } };
  }
  return null;
}

export function offlineUpload(domain: string, file: File, onProgress?: (p: number) => void): Promise<Json> {
  return new Promise((resolve) => {
    let pct = 0;
    const timer = window.setInterval(() => {
      pct = Math.min(100, pct + 25);
      onProgress?.(pct);
      if (pct < 100) return;
      window.clearInterval(timer);
      const db = load();
      const caseRow = db.cases.find((c) => c.domain === domain) ?? db.cases[0];
      const id = `doc-${uid()}`;
      const chunks = Math.max(2, Math.ceil(file.size / 3500));
      db.documents.push({
        id, document_id: id, case_id: caseRow?.id ?? "case-banking", filename: file.name, mime_type: file.type || "application/octet-stream",
        size_bytes: file.size, text_extract: `Extracted text preview of ${file.name} (${domain}).`, document_type: "evidence", domain, indexed: true,
        chunks_indexed: chunks, created_at: iso(),
      });
      db.events.push({ id: uid(), case_id: caseRow?.id ?? "", event_type: "document_indexed", title: `Document indexed: ${file.name}`, body: `${chunks} chunks added to the ${domain.replace("_", " ")} index`, actor: "user", created_at: iso() });
      save(db);
      resolve({ document_id: id, case_id: caseRow?.id ?? "", filename: file.name, storage_path: `vault/${domain}/${file.name}`, indexed: true, extraction_method: "text", ocr_applied: false, text_chars: file.size, text_preview: `Indexed ${chunks} chunks from ${file.name}.`, relevance_warning: null });
    }, 250);
  });
}

let installed = false;
export function installOfflineFetch() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const real = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const i = url.indexOf("/api/v1");
    const isHealth = /\/health(\/live)?$/.test(url.split("?")[0]);
    if (i === -1 && !isHealth) return real(input, init);
    try {
      const res = await real(input, init);
      // Failed / non-JSON answers (404 HTML, 5xx, auth wall) fall through to the demo backend.
      if (res.ok && (res.headers.get("content-type") ?? "").includes("json")) return res;
    } catch { /* network error: use demo backend */ }
    const path = i !== -1 ? url.slice(i + 7) : url.slice(url.indexOf("/health"));
    let body: Json = {};
    try { body = init?.body ? JSON.parse(String(init.body)) : {}; } catch { /* non-JSON body */ }
    const db = load();
    tick(db);
    const out = route((init?.method ?? "GET").toUpperCase(), path, body, db);
    save(db);
    await new Promise((resolve) => setTimeout(resolve, path.includes("multi-domain") ? 4500 : 180));
    // /split and /decision have their own computed in-page fallbacks: let them see a failure.
    const own = /^\/(split|decision)/.test(path);
    return new Response(JSON.stringify(out ? out.data : own ? { detail: "n/a" } : []), { status: out ? out.status : own ? 404 : 200, headers: { "content-type": "application/json" } });
  };
}
