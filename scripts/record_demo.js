// Records the demo walkthrough from the REAL running app (no mocked UI).
// Prereq: `python3 run.py` serving http://127.0.0.1:8360 ; Playwright with Chromium.
// Usage:  node scripts/record_demo.js <out_dir>     -> <out_dir>/*.webm (convert with ffmpeg)
// Caption bars are narration overlays, visually separate from the product UI.
const { chromium } = require("playwright");

const BASE = process.env.PAYPROOF_URL || "http://127.0.0.1:8360/";
const out = process.argv[2] || "demo-out";

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: out, size: { width: 1440, height: 900 } } });
  const p = await ctx.newPage();
  const wait = (s) => p.waitForTimeout(s * 1000);
  const caption = async (text) => p.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText = "position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1100px;z-index:99;" +
        "background:rgba(4,8,14,.92);border:1px solid #6ee7b7;color:#e5e9f0;padding:12px 18px;border-radius:12px;" +
        "font:600 19px/1.4 Inter,system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.5);pointer-events:none";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  const scrollTo = async (sel) => { await p.evaluate((s) => document.querySelector(s).scrollIntoView({ behavior: "smooth", block: "start" }), sel); await wait(1.2); };
  const as = async (tok) => { await p.selectOption("#user", tok); await wait(1.2); };

  await p.goto(BASE);
  await p.waitForSelector(".case-title");
  await p.click("#reset"); await wait(1);

  // Every number, record id and status in the captions comes from the live API, not from this script.
  const api = (path) => p.evaluate(async (u) => (await fetch(u, { headers: { "X-Demo-User": "ana" } })).json(), path);
  const queue = await api("/api/cases");
  const demoId = (queue.find((c) => c.tags.includes("demo")) || queue[0]).case_id;
  const negId = (queue.find((c) => c.tags.includes("negative_demo")) || queue.find((c) => c.proof_status === "NEEDS_EVIDENCE")).case_id;
  const d = await api(`/api/cases/${demoId}`);
  const neg = await api(`/api/cases/${negId}`);
  const integ = await api("/api/integrations");
  const bench = await api("/api/benchmark");
  const usd = (v) => (Number(v) < 0 ? "−$" : "$") + Math.abs(Number(v)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sg = (v) => (Number(v) > 0 ? "+" : Number(v) < 0 ? "" : "±") + usd(v);
  const c = d.calculation, wf = d.hypothesis.waterfall || [];
  const late = d.timeline.find((e) => e.flags.includes("LATE_ARRIVING") && e.type === "payment");
  const dup = d.skeptic.findings.find((f) => f.id.startsWith("SK-DUP"));
  const strongest = d.skeptic.findings.find((f) => f.id === d.skeptic.strongest);
  const cfs = d.counterfactuals.slice(0, 3).map((x) => `${x.title}: ${sg(x.delta_change)}`).join(" · ");
  const steps = wf.filter((r) => r.kind === "step" && !r.label.startsWith("Paid")).map((r) => `${sg(r.amount)} ${r.label.split(" (")[0].toLowerCase()}`).join(", ");
  const states = integ.rows.filter((r) => r.state !== "N/A").map((r) => `${r.sponsor}: ${r.state.replace(/_/g, " ")}`).join(" · ");
  const a = bench.agent, b = bench.baseline, s = bench.safety;

  await p.click(`[data-case="${demoId}"]`); await wait(1);
  await caption("Commission disputes: CRM, contracts, billing, comp plan and payroll all disagree. PayProof proves what SHOULD have been paid before anyone touches payroll.");
  await wait(9);
  await caption(`${d.title}: claimed ${usd(d.dispute.claimed_shortfall)}. Verified variance ${sg(c.delta)} (${d.verdict.replace(/_/g, " ").toLowerCase()}, proof ${d.proof_status}).`);
  await wait(9);
  await scrollTo("#s-evidence");
  await caption(`Raw source records on a timeline.${late ? ` ${late.record_id}: effective ${late.effective_at}, recorded ${late.recorded_at} (after the cutoff).` : ""}${dup ? ` ${dup.title}.` : ""}`);
  await wait(8);
  if (late) {
    await p.click(`.ev[data-rec="${late.record_id}"]`); await wait(1);
    await caption("Every record is inspectable: original, unmodified, with source system, effective time and recorded time.");
    await wait(7);
    await p.click("#drawer-close"); await wait(1);
  }
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await wait(1.2);
  await caption(`Meterless World Model: ${d.world_model.entities} entities, ${d.world_model.relationships} bitemporal edges, every write with provenance. Verifier cross-check against its as-of-cutoff view: ${d.world_model.cross_check && d.world_model.cross_check.passed ? "match" : "MISMATCH"}.`);
  await wait(10);
  await scrollTo("#s-reason");
  await caption(`Waterfall: ${usd(wf[0] ? wf[0].amount : 0)} expected, ${steps} = ${usd(c.due)} due, against ${usd(c.paid)} paid.`);
  await wait(9);
  if (strongest) {
    await caption(`Skeptic's strongest counterargument: ${strongest.title}. If true: variance ${sg(strongest.impact)}. Outcome: ${strongest.outcome.replace("_", " ").toLowerCase()}${strongest.rule ? ` (${strongest.rule})` : ""}.`);
    await wait(10);
  }
  await scrollTo("#s-calc");
  await caption("Deterministic Decimal calculation: every step cites its rule and source records; excluded records show the reason. The model never computes money.");
  await wait(9);
  await scrollTo("#s-cf");
  await caption(`Counterfactual replay (hypothetical, never treated as events): ${cfs}.`);
  await wait(10);
  await scrollTo("#s-action");
  await p.click("#b-propose"); await wait(1.5);
  const pa = d.proposed_action;
  await caption(`One typed, approval-gated action: ${pa.type.replace(/_/g, " ").toLowerCase()}${pa.amount ? " " + usd(pa.amount) : ""}, ${pa.required_permission} required, idempotency key and evidence fingerprint attached.`);
  await wait(8);
  await as("rep");
  await scrollTo("#s-action");
  await p.click("#b-approve"); await wait(1.5);
  const refusal = (await p.textContent("#action-err")).trim();
  const said = refusal ? refusal.replace(/\.?$/, ".") : "Refused by the backend.";
  await caption(`The sales rep tries to approve their own adjustment. ${said} Authorization is enforced server-side.`);
  await wait(9);
  const approver = pa.required_permission === "controller" ? "ctl" : "fin";
  await as(approver);
  await scrollTo("#s-action");
  await p.click("#b-approve"); await wait(1.5);
  await caption(`An authorized ${pa.required_permission.replace("_", " ")} approves.`);
  await wait(4);
  await as("ops");
  await scrollTo("#s-action");
  await p.click("#b-exec"); await wait(2);
  await scrollTo("#s-audit");
  const after = await api(`/api/cases/${demoId}`);
  const rc = (after.actions.slice(-1)[0] || {}).receipt;
  await caption(rc ? `Executed once on the SIMULATED payroll ledger, then re-investigated: paid ${usd(rc.postcondition.observed_paid)}, variance ${usd(rc.postcondition.observed_delta)}, postcondition ${rc.postcondition.passed ? "passed" : "FAILED"}. Audit chain ${rc.audit_chain_valid ? "valid" : "BROKEN"}.`
    : `Execution state: ${(after.actions.slice(-1)[0] || {}).state || "unknown"} (no receipt).`);
  await wait(10);
  await p.click(`[data-case="${negId}"]`); await wait(1.5);
  await caption(`Refusal case ${negId}: ${neg.calculation.blockers.map((x) => x.detail).join("; ") || neg.proof_status}. Status ${neg.proof_status} — the only action offered is ${neg.proposed_action.type.replace(/_/g, " ").toLowerCase()}. No money moves.`);
  await wait(9);
  await scrollTo("#s-cf");
  await caption("Hypotheticals show what missing evidence would establish, without assuming it.");
  await wait(7);
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await wait(1.2);
  await caption(`Integration status is runtime truth — ${states}.`);
  await wait(9);
  await caption(`Benchmark: ${bench.sample_size} hand-labelled synthetic cases, ${a.decisions_correct}/${a.cases} vs ${b.decisions_correct}/${b.cases} for a rules-only baseline; ${s.unauthorized_actions_succeeded} unauthorized and ${s.duplicate_actions_created} duplicate actions. Cases were written alongside the engine.`);
  await wait(9);
  await p.click("#reset"); await wait(0.5);
  await ctx.close();
  await browser.close();
})();
