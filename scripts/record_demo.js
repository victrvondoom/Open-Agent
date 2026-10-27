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
  await p.click('[data-case="CASE-1001"]'); await wait(1);

  await caption("Commission disputes: CRM, contracts, billing, comp plan and payroll all disagree. PayProof proves what SHOULD have been paid before anyone touches payroll.");
  await wait(9);
  await caption("Maya claims a $3,000 shortfall on a $60,000 deal. Verified answer: $1,100 underpaid — claim partially supported, proof VERIFIED.");
  await wait(9);
  await scrollTo("#s-evidence");
  await caption("Raw source records on a timeline. PAY-44987: value date in June, but recorded in July (after the cutoff). The CN-0077 clawback was posted twice.");
  await wait(8);
  await p.click('.ev[data-rec="PAY-44987"]'); await wait(1);
  await caption("Every record is inspectable: original, unmodified, with source system, effective time and recorded time.");
  await wait(7);
  await p.click("#drawer-close"); await wait(1);
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await wait(1.2);
  await caption("Meterless World Model: every record ingested with provenance and bitemporal edges. The verifier cross-checks the engine against the World Model's as-of-cutoff view — they match.");
  await wait(10);
  await scrollTo("#s-reason");
  await caption("Investigator's waterfall: $6,000 expected − $1,000 amendment − $700 uncollected = $4,300 due, against $3,200 paid.");
  await wait(9);
  await caption("Skeptic's strongest counterargument: exclude the late-recorded payment → only $200 owed. Tested by replay, ruled out by plan clause P-4.2 (value date governs).");
  await wait(10);
  await scrollTo("#s-calc");
  await caption("Deterministic Decimal calculation: every step cites its rule and source records; excluded records show the reason. The model never computes money.");
  await wait(9);
  await scrollTo("#s-cf");
  await caption("Counterfactual replay — hypothetical, never treated as events: recorded-date timing −$900, no duplicate −$200, amendment void: no change (collections cap the base).");
  await wait(10);
  await scrollTo("#s-action");
  await p.click("#b-propose"); await wait(1.5);
  await caption("One typed, approval-gated action: $1,100 payroll adjustment, finance_approver required, idempotency key and evidence fingerprint attached.");
  await wait(8);
  await as("rep");
  await scrollTo("#s-action");
  await p.click("#b-approve"); await wait(1.5);
  await caption("The sales rep tries to approve her own adjustment: the BACKEND refuses (403, conflict of interest). Buttons are not hidden — authorization is enforced server-side.");
  await wait(9);
  await as("fin");
  await scrollTo("#s-action");
  await p.click("#b-approve"); await wait(1.5);
  await caption("An authorized finance approver approves.");
  await wait(4);
  await as("ops");
  await scrollTo("#s-action");
  await p.click("#b-exec"); await wait(2);
  await scrollTo("#s-audit");
  await caption("Executed once on the SIMULATED payroll ledger, then independently re-investigated: paid $4,300, variance $0, postcondition passed. Hash-chained audit valid.");
  await wait(10);
  await p.click("#b-exec").catch(() => {}); await wait(1);
  await p.click('[data-case="CASE-1015"]'); await wait(1.5);
  await caption("Refusal case: no signed contract in CLM. Status NEEDS_EVIDENCE — the only action offered is a request for evidence. No money moves.");
  await wait(9);
  await scrollTo("#s-cf");
  await caption("The hypothetical shows what the missing contract would establish, without assuming it.");
  await wait(7);
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await wait(1.2);
  await caption("Integration status is runtime truth: Meterless World Model LIVE in-process; Zetaris and Nemotron in FALLBACK in this recording — and labelled so.");
  await wait(9);
  await caption("Benchmark: 25 hand-labelled synthetic cases — 25/25 vs 11/25 for a rules-only baseline; 0 unauthorized or duplicate actions. Cases were written alongside the engine.");
  await wait(9);
  await p.click("#reset"); await wait(0.5);
  await ctx.close();
  await browser.close();
})();
