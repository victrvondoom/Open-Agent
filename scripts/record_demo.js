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
  const open = async (id) => { await p.click(`[data-case="${id}"]`); await p.waitForFunction((cid) => ((document.querySelector(".hero .mono") || {}).textContent || "").startsWith(cid), id); await wait(1); };

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
  const all = {};
  for (const q of queue) all[q.case_id] = q.case_id === demoId ? d : await api(`/api/cases/${q.case_id}`);
  const quar = Object.values(all).find((x) => x.security.quarantined.length && x.proposed_action.type !== "REQUEST_EVIDENCE");
  const bench = await api("/api/benchmark");
  const usd = (v) => (Number(v) < 0 ? "−$" : "$") + Math.abs(Number(v)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sg = (v) => (Number(v) > 0 ? "+" : Number(v) < 0 ? "" : "±") + usd(v);
  const lc = (s) => String(s || "").replace(/_/g, " ").toLowerCase();
  const c = d.calculation, wf = d.hypothesis.waterfall || [];
  const late = d.timeline.find((e) => e.flags.includes("LATE_ARRIVING") && e.type === "payment");
  const dup = d.skeptic.findings.find((f) => f.id.startsWith("SK-DUP"));
  const strongest = d.skeptic.findings.find((f) => f.id === d.skeptic.strongest);
  const cfs = d.counterfactuals.slice(0, 3).map((x) => `${x.title}: ${sg(x.delta_change)}`).join(" · ");
  const steps = wf.filter((r) => r.kind === "step" && !r.label.startsWith("Paid")).map((r) => `${sg(r.amount)} ${r.label.split(" (")[0].toLowerCase()}`).join(", ");
  const a = bench.agent, b = bench.baseline, s = bench.safety, sys = (bench.evaluation || {}).systems || {};

  await open(demoId);
  await caption("Commission disputes: CRM, contracts, billing, comp plan and payroll all disagree. PayProof proves what SHOULD have been paid before anyone touches payroll.");
  await wait(9);
  await caption(`${d.title}: claimed ${usd(d.dispute.claimed_shortfall)}. Verified variance ${sg(c.delta)} (${lc(d.verdict)}, proof ${d.proof_status}).`);
  await wait(8);
  await scrollTo("#s-trace");
  const total = d.trace.reduce((t, x) => t + Number(x.ms), 0);
  await caption(`Agent pipeline, recorded on every run: ${d.trace.map((t) => t.stage).join(" → ")} (${total.toFixed(1)} ms). No loops. Then a human approval gate: nothing consequential runs on its own.`);
  await wait(10);
  await scrollTo("#s-evidence");
  await caption(`Raw source records on a timeline.${late ? ` ${late.record_id}: effective ${late.effective_at}, recorded ${late.recorded_at} (after the cutoff).` : ""}${dup ? ` ${dup.title}.` : ""}`);
  await wait(8);
  if (late) {
    await p.click(`.ev[data-rec="${late.record_id}"]`); await wait(1);
    await caption("Every record is inspectable: original, unmodified, with source system, effective time and recorded time.");
    await wait(6);
    await p.click("#drawer-close"); await wait(1);
  }
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await wait(1.2);
  await caption(`Meterless World Model: ${d.world_model.entities} entities, ${d.world_model.relationships} bitemporal edges, every write with provenance. Verifier cross-check against its as-of-cutoff view: ${d.world_model.cross_check && d.world_model.cross_check.passed ? "match" : "MISMATCH"}.`);
  await wait(9);
  await scrollTo("#s-reason");
  await caption(`Waterfall: ${usd(wf[0] ? wf[0].amount : 0)} expected, ${steps} = ${usd(c.due)} due, against ${usd(c.paid)} paid.`);
  await wait(9);
  if (strongest) {
    await caption(`Skeptic's strongest counterargument: ${strongest.title}. If true: variance ${sg(strongest.impact)}. Outcome: ${lc(strongest.outcome)}${strongest.rule ? ` (${strongest.rule})` : ""}.`);
    await wait(10);
  }
  await scrollTo("#s-calc");
  await caption("Deterministic Decimal calculation: every step cites its rule and source records; excluded records show the reason. The model never computes money.");
  await wait(8);
  await scrollTo("#s-cf");
  await caption(`Counterfactual replay (hypothetical, never treated as events): ${cfs}.`);
  await wait(10);
  await scrollTo("#s-action");
  await p.click("#b-propose"); await wait(1.5);
  const pa = d.proposed_action;
  await caption(`One typed, approval-gated action: ${lc(pa.type)}${pa.amount ? " " + usd(pa.amount) : ""}, ${pa.required_permission} required, idempotency key, evidence fingerprint and a signed Scout execution contract attached.`);
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
  await caption(`An authorized ${lc(pa.required_permission)} approves.`);
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

  // Meterless H-MEM: the verified outcome is now a precedent for other cases (never for itself).
  let prec = null;
  for (const q of queue) {
    if (q.case_id === demoId) continue;
    const x = await api(`/api/cases/${q.case_id}`);
    const hit = (x.precedents.precedents || []).find((m) => m.case_id === demoId);
    if (hit && (!prec || hit.relevance > prec.hit.relevance)) prec = { id: q.case_id, hit };
  }
  if (rc && rc.precedent_memory_id && prec) {
    await open(prec.id);
    await scrollTo("#s-memory");
    await caption(`Meterless H-MEM: ${demoId}'s verified outcome (receipt-backed) is now a precedent. ${prec.id} shares ${prec.hit.shared_patterns.join(", ")} and recalls it at relevance ${prec.hit.relevance}. Precedents inform the reviewer; they never enter the calculation.`);
    await wait(10);
    await p.click(`[data-compare="${demoId}"]`); await wait(1);
    await caption(`Side-by-side comparison: both sides are live investigations of current evidence.`);
    await wait(6);
    await p.click("#drawer-close"); await wait(1);
  }

  // Meterless Scout: an instruction planted in a retrieved record is quarantined and escalates approval.
  if (quar) {
    const q0 = quar.security.quarantined[0];
    await open(quar.case_id);
    await scrollTo("#s-memory");
    await caption(`Meterless Scout: ${q0.record_id}.${q0.field} in ${quar.case_id} carries an embedded instruction (${q0.kinds.join(", ")}). Quarantined: kept out of the model, flagged as a security finding. The numbers are still computed by code.`);
    await wait(10);
    await scrollTo("#s-action");
    await caption(`So the action is escalated: ${lc(quar.proposed_action.type)} now needs ${lc(quar.proposed_action.required_permission)} approval. Every step needs a signed, 5-minute Scout execution contract.`);
    await wait(8);
  }

  await open(negId);
  await caption(`Refusal case ${negId}: ${neg.calculation.blockers.map((x) => x.detail).join("; ") || neg.proof_status}. Status ${neg.proof_status}. The only action offered is ${lc(neg.proposed_action.type)}. No money moves; hypotheticals show what the evidence would establish.`);
  await wait(10);

  await scrollTo("#s-integ");
  await p.click("#integ-check");
  await p.waitForSelector("#integ-last .checks li", { timeout: 30000 }); await wait(1);
  const checks = await p.$$eval("#integ-last .checks li", (els) => els.map((e) => ({ cls: e.className, name: e.querySelector("b").textContent })));
  const short = (n) => n.replace("Meterless ", "").replace("NVIDIA ", "");
  await caption(`Run live check, real calls only: ${checks.map((x) => `${short(x.name)} ${x.cls === "ok" ? "✓" : x.cls === "bad" ? "FAILED" : "not configured, not called"}`).join(" · ")}. Nothing is simulated in place of a missing service.`);
  await wait(10);
  await caption(`Benchmark: ${bench.sample_size} hand-labelled synthetic cases, ${a.decisions_correct}/${a.cases} vs ${b.decisions_correct}/${b.cases} for a rules-only baseline${sys.no_critic ? `, ${sys.no_critic.correct}/${sys.no_critic.cases} without the skeptic` : ""}; ${s.unauthorized_actions_succeeded} unauthorized and ${s.duplicate_actions_created} duplicate actions. Cases were written alongside the engine.`);
  await wait(10);
  await p.click("#reset"); await wait(0.5);
  await ctx.close();
  await browser.close();
})();
