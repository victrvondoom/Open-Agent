"use strict";
// PayProof Decision Room. All decisions, money and permissions come from the API;
// this UI only renders them. Disabled buttons are convenience, not enforcement.

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => (v === null || v === undefined ? "—" : (Number(v) < 0 ? "-$" : "$") + Math.abs(Number(v)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const signed = (v) => (v === null || v === undefined ? "—" : (Number(v) > 0 ? "+" : "") + money(v));
const pill = (s, label) => `<span class="pill s-${esc(s)}">${esc((label || s || "").replace(/_/g, " "))}</span>`;
const cite = (id, cls = "") => `<span class="cite ${cls}" data-rec="${esc(id)}">${esc(id)}</span>`;

const state = { user: localGet("pp-user") || "ana", caseId: null, data: null, sources: null, users: [] };

function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", "X-Demo-User": state.user, ...(opts.headers || {}) } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(body.message || body.error || res.statusText), { status: res.status, body });
  return body;
}

function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (bad ? " bad" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 4200);
}

async function boot() {
  state.users = await api("/api/users");
  const sel = $("#user");
  sel.innerHTML = state.users.map((u) => `<option value="${esc(u.token)}">${esc(u.name)} — ${esc(u.role)}</option>`).join("");
  sel.value = state.user;
  sel.onchange = async () => { state.user = sel.value; localSet("pp-user", state.user); await loadQueue(); if (state.caseId) openCase(state.caseId).catch(() => { $("#main").innerHTML = `<div class="empty">This user cannot view the selected case.</div>`; }); };
  $("#reset").onclick = async () => { await api("/api/demo/reset", { method: "POST" }); toast("Demo state reset"); await loadQueue(); if (state.caseId) openCase(state.caseId); };
  $("#drawer-close").onclick = () => $("#drawer").classList.add("hidden");
  document.addEventListener("click", (e) => { const c = e.target.closest("[data-rec]"); if (c) inspect(c.dataset.rec); });
  const integ = await api("/api/integrations");
  $("#integrations").innerHTML = integ.rows.filter((r) => r.mode !== "n/a at runtime").map((r) =>
    `<span class="chip ${r.mode === "live" ? "live" : "fallback"}" title="${esc(r.capability + " — " + r.detail)}">${esc(r.sponsor)}: ${esc(r.mode)}</span>`).join("");
  await loadQueue();
  const first = new URLSearchParams(location.search).get("case") || "CASE-1001";
  openCase(first).catch(() => {});
}

async function loadQueue() {
  const q = await api("/api/cases");
  $("#qcount").textContent = `${q.length} cases`;
  $("#queue").innerHTML = q.map((c) => `
    <div class="qitem ${c.case_id === state.caseId ? "active" : ""}" data-case="${esc(c.case_id)}">
      <div class="qrow"><span class="qtitle">${esc(c.title)}</span>${pill(c.proof_status)}</div>
      <div class="qrow qmeta"><span>${esc(c.case_id)} · ${esc(c.claimant)}</span><span class="mono">exposure ${money(c.exposure)}</span></div>
      <div class="qrow qmeta"><span>claim ${money(c.claimed)} · ${esc(c.verdict.replace(/_/g, " ").toLowerCase())}</span>
        <span>${c.action_state ? pill(c.action_state === "VERIFIED" ? "VERIFIED" : c.action_state, c.action_state) : ""}</span></div>
    </div>`).join("");
  document.querySelectorAll(".qitem").forEach((el) => (el.onclick = () => openCase(el.dataset.case)));
}

async function openCase(id) {
  state.caseId = id;
  document.querySelectorAll(".qitem").forEach((el) => el.classList.toggle("active", el.dataset.case === id));
  const [data, sources] = await Promise.all([api(`/api/cases/${id}`), api(`/api/cases/${id}/sources`)]);
  state.data = data; state.sources = sources;
  render();
}

function recordById(id) {
  for (const [sys, blk] of Object.entries(state.sources.sources)) {
    const r = blk.records.find((x) => x.id === id);
    if (r) return { sys, name: blk.system, r };
  }
  if (state.sources.dispute.id === id) return { sys: "disputes", name: "dispute-intake", r: state.sources.dispute };
  return null;
}

function inspect(id) {
  const hit = recordById(id);
  $("#drawer-title").textContent = id;
  if (!hit) {
    $("#drawer-body").innerHTML = `<p class="dim">${esc(id)} is a policy/plan reference or simulated ledger entry, not a source record.</p>
      <pre>${esc(JSON.stringify(state.data.calculation.steps.filter((s) => s.cites.includes(id)), null, 2))}</pre>`;
  } else {
    const uses = state.data.calculation.steps.filter((s) => s.cites.includes(id)).map((s) => s.label);
    const excl = state.data.calculation.steps.flatMap((s) => s.excluded).filter((e) => e.id === id);
    const finds = state.data.skeptic.findings.filter((f) => f.cites.includes(id));
    $("#drawer-body").innerHTML = `
      <div class="kv"><div class="k">Source system</div><div>${esc(hit.name)} <span class="dim">(${esc(hit.sys)})</span></div>
      <div class="k">Record type</div><div>${esc(hit.r.type || "dispute")}</div>
      <div class="k">Effective at</div><div class="mono">${esc(hit.r.effective_at)}</div>
      <div class="k">Recorded at</div><div class="mono">${esc(hit.r.recorded_at)}</div>
      <div class="k">Used in</div><div>${uses.map(esc).join(", ") || '<span class="dim">not used in calculation</span>'}</div>
      <div class="k">Excluded</div><div>${excl.map((e) => esc(e.reason)).join("; ") || "—"}</div>
      <div class="k">Skeptic</div><div>${finds.map((f) => pill(f.outcome) + " " + esc(f.title)).join("<br>") || "—"}</div></div>
      <h4>Original record (unmodified)</h4><pre>${esc(JSON.stringify(hit.r, null, 2))}</pre>`;
  }
  $("#drawer").classList.remove("hidden");
}

function render() {
  const d = state.data, c = d.calculation, a = d.proposed_action;
  const step = (k) => c.steps.find((s) => s.key === k);
  const strongest = d.skeptic.findings.find((f) => f.id === d.skeptic.strongest);
  $("#main").innerHTML = `
  <nav class="nav"><a href="#s-evidence">1 Evidence</a><a href="#s-reason">2 Hypothesis vs skeptic</a><a href="#s-calc">3 Calculation</a>
    <a href="#s-cf">4 Counterfactuals</a><a href="#s-proof">5 Proof bundle</a><a href="#s-action">6 Action</a><a href="#s-audit">7 Receipt & audit</a></nav>
  <section class="hero">
    <div class="card">
      <div class="dim mono">${esc(d.case_id)} · ${esc(d.dispute.id)} · filed ${esc(d.dispute.filed_at)} · period ${esc(d.dispute.period)}</div>
      <div class="case-title">${esc(d.title)}</div>
      <div>${pill(d.proof_status)} ${pill(d.verdict)} ${d.tags.map((t) => `<span class="chip">${esc(t)}</span>`).join(" ")}</div>
      <div class="narr">“${esc(d.dispute.narrative)}”</div>
      <div class="kpis">
        <div class="kpi"><div class="l">Claimed shortfall</div><div class="v">${money(d.dispute.claimed_shortfall)}</div></div>
        <div class="kpi"><div class="l">Verified due</div><div class="v">${money(c.due)}</div></div>
        <div class="kpi"><div class="l">Paid to date</div><div class="v">${money(c.paid)}</div></div>
        <div class="kpi"><div class="l">Variance</div><div class="v ${Number(c.delta) > 0 ? "pos" : Number(c.delta) < 0 ? "neg" : ""}">${signed(c.delta)}</div></div>
      </div>
    </div>
    <div class="card">
      <h3>Run provenance</h3>
      <div class="kv mono">
        <div class="k">run_id</div><div>${esc(d.run_id)}</div>
        <div class="k">proof_hash</div><div title="${esc(d.proof_hash)}">${esc(d.proof_hash.slice(0, 24))}…</div>
        <div class="k">source fingerprint</div><div title="${esc(d.source_fingerprint)}">${esc(d.source_fingerprint.slice(0, 24))}…</div>
        <div class="k">engine</div><div>${esc(d.engine_version)}</div>
        <div class="k">plan version</div><div>${esc(d.plan_version || "—")}</div>
        <div class="k">model</div><div>${esc(d.telemetry.model_identity)}</div>
        <div class="k">model calls</div><div>${d.telemetry.model_calls.map((m) => esc(m.role + ":" + m.status)).join(", ")}</div>
        <div class="k">scenario ranking</div><div>${esc("meterless " + d.telemetry.meterless.status)}</div>
        <div class="k">sources</div><div>${Object.entries(d.sources_meta.provenance).map(([k, v]) => esc(k + "=" + v)).join(", ")}</div>
        <div class="k">latency</div><div>${esc(d.telemetry.latency_ms)} ms</div>
      </div>
    </div>
  </section>

  <section class="card full" id="s-evidence">
    <h3><span><span class="n">1</span>Temporal evidence — timeline & graph</span><span class="dim" style="text-transform:none;letter-spacing:0">click any record to inspect the original</span></h3>
    <div class="timeline"><div class="tl">${d.timeline.map((e) => e.type === "cutoff"
      ? `<div class="ev cutoff"><div class="d">${esc(e.effective_at)}</div><div class="ty">CUTOFF</div></div>`
      : `<div class="ev" data-rec="${esc(e.record_id)}"><div class="d">eff ${esc(e.effective_at)}<br>rec ${esc(e.recorded_at)}</div>
         <div class="ty">${esc(e.type.replace("_", " "))}</div><div class="mono">${esc(e.record_id)}</div>
         <div class="mono dim">${e.amount ? money(e.amount) : ""}</div>${e.flags.map((f) => `<div class="flag">⚑ ${esc(f.replace(/_/g, " "))}</div>`).join("")}</div>`).join("")}</div></div>
    <div class="graph-wrap" id="graph"></div>
    <div class="legend"><span><i style="border-color:#60a5fa"></i>used in calculation</span><span><i style="border-color:#f87171"></i>skeptic: confirmed issue</span>
      <span><i style="border-color:#fbbf24"></i>skeptic: tested & ruled out</span><span><i style="border-color:#c4b5fd;border-style:dashed"></i>unresolved</span>
      <span><i style="border-color:#34d399"></i>identity link (resolved)</span></div>
    <h4>Identity resolution — ${pill(d.identity.status === "RESOLVED" ? "VERIFIED" : "NEEDS_EVIDENCE", d.identity.status)}</h4>
    <table><tr><th>HRIS employee</th><th>CRM candidate</th><th>Strength</th><th>Signals</th></tr>
      ${d.identity.candidates.map((x) => `<tr><td>${cite(d.identity.employee_id)}</td><td>${cite(x.crm_user_id)} ${esc(x.name)}</td><td>${pill(x.strength === "STRONG" ? "VERIFIED" : "UNDETERMINED", x.strength)}</td><td>${x.signals.map(esc).join("; ")}</td></tr>`).join("") || `<tr><td colspan="4" class="dim">No candidates</td></tr>`}
    </table>
  </section>

  <section class="grid2" id="s-reason">
    <div class="card"><h3><span><span class="n">2</span>Investigator — initial hypothesis</span></h3>
      ${d.hypothesis.claims.map((x) => `<div class="hyp">${esc(x.text)}<div>${x.cites.map((i) => cite(i)).join("")}</div></div>`).join("")}
      ${waterfallCard(d.hypothesis.waterfall)}
      ${d.narrative.length && d.narrative[0].origin === "model" ? `<h4>Model narration (${esc(d.telemetry.model_identity)}) — cite-checked</h4>${d.narrative.map((x) => `<div class="hyp">${esc(x.text)}<div>${x.cites.map((i) => cite(i)).join("")}</div></div>`).join("")}` : ""}
      ${d.validation.unsupported_claims.length ? `<h4>Dropped unsupported claims</h4>${d.validation.unsupported_claims.map((x) => `<div class="finding"><s>${esc(x.text)}</s><div class="dim">${esc(x.reason)}</div></div>`).join("")}` : ""}
    </div>
    <div class="card"><h3><span>Skeptic — attempts to falsify</span><span class="dim" style="text-transform:none">${d.skeptic.findings.length} tests</span></h3>
      ${strongest ? `<div class="vs">STRONGEST COUNTERARGUMENT</div>` : ""}
      ${d.skeptic.findings.slice().sort((x, y) => (y.id === d.skeptic.strongest) - (x.id === d.skeptic.strongest)).map((f) => `
        <div class="finding ${f.id === d.skeptic.strongest ? "strong" : ""}">
          <div class="qrow"><span class="t">${esc(f.title)}</span>${pill(f.outcome)}</div>
          <div class="dim">${esc(f.detail)}</div>
          <div>${f.cites.map((i) => cite(i)).join("")} ${f.rule ? `<span class="chip">${esc(f.rule)}</span>` : ""}
          ${f.impact !== null && f.impact !== undefined ? `<span class="chip">if true: variance ${signed(f.impact)}</span>` : ""}</div>
        </div>`).join("") || `<div class="dim">No falsifying evidence found.</div>`}
    </div>
  </section>

  <section class="card full" id="s-calc">
    <h3><span><span class="n">3</span>Deterministic calculation — ${esc(d.plan_version || "")}</span><span class="dim" style="text-transform:none">exact decimals · ROUND_HALF_UP once</span></h3>
    <table><tr><th>Step</th><th>Rule</th><th>Formula</th><th class="num">Value</th><th>Evidence</th></tr>
      ${c.steps.map((s) => `<tr><td>${esc(s.label)}</td><td><span class="chip">${esc(s.rule)}</span></td><td class="mono">${esc(s.formula)}
        ${s.excluded.map((e) => `<div class="excl">excluded ${cite(e.id, "x")} — ${esc(e.reason)}</div>`).join("")}</td>
        <td class="num">${MONEY_KEYS.has(s.key) ? money(s.value) : esc(s.value)}</td><td>${s.cites.map((i) => cite(i)).join("")}</td></tr>`).join("")}
    </table>
    ${c.blockers.length ? `<h4>Blockers</h4>${c.blockers.map((b) => `<div class="finding">${pill("NEEDS_EVIDENCE", b.code)} ${esc(b.detail)}</div>`).join("")}` : ""}
    ${d.verification.conflicts.length ? `<h4>Conflicts</h4>${d.verification.conflicts.map((x) => `<div class="finding">${pill(x.material ? "DISPUTED" : "VERIFIED", x.material ? "MATERIAL" : "IMMATERIAL")} ${esc(x.detail)} ${x.cites.map((i) => cite(i)).join("")}
      ${x.alternative_dues ? `<div class="dim">alternative dues: ${x.alternative_dues.map(money).join(" vs ")}</div>` : ""}</div>`).join("")}` : ""}
  </section>

  <section class="card full" id="s-cf">
    <h3><span><span class="n">4</span>Counterfactual payout replay</span>${pill("HYPOTHETICAL", "hypothetical — not financial events")}</h3>
    ${cfTable(d)}
  </section>

  <section class="grid2" id="s-proof">
    <div class="card"><h3><span><span class="n">5</span>Proof bundle</span></h3>
      ${d.bundle.map((b) => `<div class="claim" style="border-color:var(--${b.status === "VERIFIED" ? "verified" : b.status === "DISPUTED" ? "disputed" : b.status === "REJECTED" ? "rejected" : "needs"})">
        <div class="qrow"><span class="st">${esc(b.statement)}</span>${pill(b.status)}</div>
        <div class="dim">supporting</div><div>${b.supporting.map((i) => cite(i)).join("")}</div>
        ${b.contradicting.length ? `<div class="dim">contradicting / excluded</div><div>${b.contradicting.map((i) => cite(i, "x")).join("")}</div>` : ""}
        <div class="dim">policy: ${b.policy.map(esc).join(", ")}</div>
        ${b.assumptions.length ? `<div class="dim">assumptions: ${b.assumptions.map(esc).join("; ")}</div>` : ""}
        ${b.open_questions.length ? `<div style="color:var(--warn)">open: ${b.open_questions.map(esc).join("; ")}</div>` : ""}</div>`).join("")}
    </div>
    <div class="card"><h3><span>Policy verifier — invariants</span></h3>
      <table class="inv">${d.verification.invariants.map((i) => `<tr><td>${i.passed ? "✅" : "❌"}</td><td>${esc(i.invariant)}<div class="dim mono">${esc(i.detail)}</div></td></tr>`).join("")}</table>
      <h3 style="margin-top:14px"><span>Final validator</span>${pill(d.validation.passed ? "VERIFIED" : "REJECTED", d.validation.passed ? "PASSED" : "FAILED")}</h3>
      ${d.validation.errors.map((e) => `<div class="err">${esc(e)}</div>`).join("") || `<div class="dim">All claims cite real records; action is allowlisted and consistent with the proof.</div>`}
    </div>
  </section>

  <section class="card full" id="s-action">${actionPanel(d)}</section>
  <section class="card full" id="s-audit"><h3><span><span class="n">7</span>Execution receipt & audit trail</span><span id="chain"></span></h3><div id="receipt"></div><div class="audit" id="audit"></div></section>
  `;
  drawGraph(d.graph);
  wireActions();
  loadAudit();
}

function cfTable(d) {
  const rows = d.counterfactuals;
  if (!rows.length) return `<div class="dim">No applicable counterfactuals for this case.</div>`;
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r.delta_change || 0))));
  const c = d.calculation;
  return `<table><tr><th>Scenario (hypothetical)</th><th class="num">Due</th><th class="num">Paid</th><th class="num">Variance</th><th class="num">Change vs actual</th><th></th><th>Facts changed</th></tr>
    <tr style="background:#0c211b"><td><b>ACTUAL (observed evidence)</b></td><td class="num">${money(c.due)}</td><td class="num">${money(c.paid)}</td><td class="num">${signed(c.delta)}</td><td class="num">—</td><td></td><td></td></tr>
    ${rows.map((r) => {
      const v = Number(r.delta_change || 0), w = Math.abs(v) / max * 50;
      return `<tr><td><b>${esc(r.title)}</b><div class="dim">${esc(r.question)}</div></td><td class="num">${money(r.due)}</td><td class="num">${money(r.paid)}</td>
      <td class="num">${signed(r.delta)}</td><td class="num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}">${r.delta_change === null ? (r.blocked ? "blocked" : "—") : signed(r.delta_change)}</td>
      <td><div class="bar"><span style="left:${v >= 0 ? 50 : 50 - w}%;width:${w}%;background:${v >= 0 ? "var(--verified)" : "var(--bad)"}"></span></div></td>
      <td>${r.changed_facts.map((i) => cite(i)).join("")}</td></tr>`;
    }).join("")}</table>`;
}

const MONEY_KEYS = new Set(["eligible", "collected", "base", "due", "paid", "delta"]);

function waterfallCard(w) {
  if (!w) return "";
  return `<h4>Reconciliation: claimant expectation → verified variance</h4><table>${w.map((r) => `
    <tr style="${r.kind !== "step" ? "font-weight:700;background:#0f1623" : ""}"><td>${esc(r.label)} ${r.cites.map((i) => cite(i)).join("")}</td>
    <td class="num ${r.kind === "step" ? (Number(r.amount) < 0 ? "neg" : "pos") : ""}">${r.kind === "step" ? signed(r.amount) : money(r.amount)}</td></tr>`).join("")}</table>`;
}

const ORDER = ["PROPOSED", "VALIDATED", "AWAITING_APPROVAL", "APPROVED", "EXECUTED", "VERIFIED"];

function actionPanel(d) {
  const p = d.proposed_action;
  const act = d.actions.filter((x) => x.idempotency_key === p.idempotency_key).slice(-1)[0] || d.actions.slice(-1)[0];
  const cur = act ? act.state : null;
  const idx = cur ? ORDER.indexOf(cur) : -1;
  const bad = ["REJECTED", "FAILED", "EXPIRED"].includes(cur);
  const me = state.users.find((u) => u.token === state.user);
  return `<h3><span><span class="n">6</span>Proposed action — approval gated</span>${act ? pill(cur) : pill("UNDETERMINED", "not yet proposed")}</h3>
    <div class="steps">${ORDER.map((s, i) => `<span class="stp ${i < idx || cur === "VERIFIED" ? "done" : i === idx ? "cur" : ""}">${esc(s.replace(/_/g, " "))}</span>`).join("→")}
      ${bad ? `<span class="stp bad">${esc(cur)}</span>` : ""}</div>
    <div class="kv">
      <div class="k">Action</div><div><b>${esc(p.type.replace(/_/g, " "))}</b> ${p.amount ? `<span class="mono">${money(p.amount)}</span>` : ""} <span class="chip">simulated adapter</span></div>
      <div class="k">Justification</div><div>${esc(p.justification)}</div>
      <div class="k">Expected result</div><div>${esc(p.expected_result)}</div>
      <div class="k">Affected records</div><div>${p.affected_records.map((i) => cite(i)).join("")}</div>
      <div class="k">Preconditions</div><div class="mono">proof=${esc(p.preconditions.proof_status)} · paid_before=${esc(p.preconditions.expected_paid_before)} · fingerprint=${esc(p.preconditions.source_fingerprint.slice(0, 16))}…</div>
      <div class="k">Required permission</div><div><span class="chip">${esc(p.required_permission)}</span> · SoD: proposer ≠ approver, subject cannot approve</div>
      <div class="k">Idempotency key</div><div class="mono">${esc(p.idempotency_key)}</div>
      ${act ? `<div class="k">Action id</div><div class="mono">${esc(act.id)} · proposed by ${esc(act.proposed_by)}${act.approved_by ? " · approved by " + esc(act.approved_by) : ""}</div>` : ""}
      ${act && act.history.length ? `<div class="k">History</div><div class="mono">${act.history.map((h) => esc(`${h.at.slice(11)} ${h.to} by ${h.actor}${h.reason ? " (" + h.reason + ")" : ""}`)).join("<br>")}</div>` : ""}
    </div>
    <div class="btns">
      <button id="b-propose" class="primary">Propose action</button>
      <button id="b-approve" ${act ? "" : "disabled"}>Approve</button>
      <button id="b-reject" class="danger" ${act ? "" : "disabled"}>Reject</button>
      <button id="b-exec" class="primary" ${act ? "" : "disabled"}>Execute (simulated)</button>
      <span style="flex:1"></span>
      <button id="b-late" class="ghost" title="Inject a late-arriving credit note dated before the cutoff">⚡ Inject late credit note</button>
      <button id="b-fail" class="ghost" title="Make the next adapter call fail">⚡ Fail next execution</button>
    </div>
    <div class="dim" style="margin-top:8px">Acting as <b>${esc(me ? me.name + " (" + me.role + ")" : state.user)}</b>. Buttons are not hidden by role on purpose: the backend enforces authorization — try approving as the sales rep.</div>
    <div id="action-err" class="err"></div>`;
}

function wireActions() {
  const d = state.data;
  const act = () => d.actions.filter((x) => x.idempotency_key === d.proposed_action.idempotency_key).slice(-1)[0] || d.actions.slice(-1)[0];
  const run = async (fn, ok) => {
    $("#action-err").textContent = "";
    try { const r = await fn(); if (ok) toast(ok(r)); }
    catch (e) { $("#action-err").textContent = `${e.status || ""} ${e.body?.error || ""}: ${e.message}`; toast(`Rejected by backend: ${e.message}`, true); }
    await loadQueue(); await openCase(d.case_id);
  };
  $("#b-propose").onclick = () => run(() => api(`/api/cases/${d.case_id}/actions`, { method: "POST" }), (r) => `Action ${r.id}: ${r.state}`);
  $("#b-approve").onclick = () => run(() => api(`/api/actions/${act().id}/decision`, { method: "POST", body: JSON.stringify({ decision: "approve" }) }), (r) => `Action ${r.state}`);
  $("#b-reject").onclick = () => run(() => api(`/api/actions/${act().id}/decision`, { method: "POST", body: JSON.stringify({ decision: "reject" }) }), (r) => `Action ${r.state}`);
  $("#b-exec").onclick = () => run(() => api(`/api/actions/${act().id}/execute`, { method: "POST", headers: { "Idempotency-Key": act().idempotency_key } }), (r) => `Action ${r.state}`);
  $("#b-late").onclick = () => run(() => api(`/api/cases/${d.case_id}/simulate/late-event`, { method: "POST" }), (r) => `Injected ${r.injected.id} — evidence changed`);
  $("#b-fail").onclick = () => run(() => api(`/api/sim/fail-next`, { method: "POST" }), () => "Next adapter call will fail");
}

async function loadAudit() {
  try {
    const a = await api("/api/audit");
    const d = state.data;
    const act = d.actions.slice(-1)[0];
    $("#chain").innerHTML = pill(a.chain_valid ? "VERIFIED" : "REJECTED", a.chain_valid ? "hash chain valid" : "hash chain broken");
    $("#receipt").innerHTML = act && act.receipt ? `<h4>Receipt ${esc(act.receipt.receipt_id)} — postcondition ${pill(act.receipt.postcondition.passed ? "VERIFIED" : "FAILED", act.receipt.postcondition.passed ? "PASSED" : "FAILED")}</h4>
      <pre>${esc(JSON.stringify(act.receipt, null, 2))}</pre>` : `<div class="dim">No execution yet for this case.</div>`;
    $("#audit").innerHTML = a.entries.slice().reverse().map((e) => `<div>#${e.seq} ${esc(e.ts.slice(11, 19))} <b>${esc(e.event)}</b> ${esc(e.actor)} ${esc(JSON.stringify(e.details))} <span class="dim">${esc(e.hash.slice(0, 10))}</span></div>`).join("");
  } catch (e) { $("#audit").innerHTML = `<div class="dim">${esc(e.message)}</div>`; }
}

function drawGraph(g) {
  const cols = ["disputes", "hris", "crm", "clm", "billing", "comp", "payroll"];
  const names = { disputes: "dispute", hris: "HRIS", crm: "CRM", clm: "Contracts", billing: "Billing", comp: "Comp plan", payroll: "Payroll" };
  const W = 150, NW = 132, NH = 40, GAP = 10, TOP = 26;
  const pos = {};
  const byCol = {};
  g.nodes.forEach((n) => (byCol[n.system] = byCol[n.system] || []).push(n));
  let maxY = 0;
  cols.forEach((c, ci) => (byCol[c] || []).forEach((n, i) => { pos[n.id] = { x: 8 + ci * W, y: TOP + i * (NH + GAP) }; maxY = Math.max(maxY, pos[n.id].y + NH); }));
  const outcome = (n) => (n.flags.includes("UNRESOLVED") ? "UNRESOLVED" : n.flags.includes("CONFIRMED") ? "CONFIRMED" : n.flags.includes("RULED_OUT") ? "RULED_OUT" : "");
  const edges = g.edges.filter((e) => pos[e.from] && pos[e.to]).map((e) => {
    const a = pos[e.from], b = pos[e.to];
    let x1 = a.x + NW, x2 = b.x, y1 = a.y + NH / 2, y2 = b.y + NH / 2;
    if (a.x === b.x) { x1 = a.x + NW; x2 = b.x + NW; const mx = x1 + 14; return `<path class="edge ${e.status}" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"><title>${esc(e.rel)}</title></path>`; }
    if (a.x > b.x) { x1 = a.x; x2 = b.x + NW; }
    const mx = (x1 + x2) / 2;
    return `<path class="edge ${e.status}" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"><title>${esc(e.rel)} (${esc(e.status)})</title></path>`;
  }).join("");
  const nodes = g.nodes.filter((n) => pos[n.id]).map((n) => {
    const p = pos[n.id];
    return `<g class="node ${n.used_in_calculation ? "used" : ""} ${outcome(n)}" data-rec="${esc(n.id)}" transform="translate(${p.x},${p.y})">
      <rect width="${NW}" height="${NH}"></rect><text x="8" y="16" style="font-weight:600">${esc(n.id.length > 19 ? n.id.slice(0, 18) + "…" : n.id)}</text>
      <text x="8" y="31" style="fill:#8a96a8">${esc(n.type.replace("_", " "))}${n.amount ? " · " + esc(money(n.amount)) : ""}</text><title>${esc(n.id)} ${esc(n.label)}</title></g>`;
  }).join("");
  const heads = cols.map((c, ci) => `<text class="col" x="${8 + ci * W}" y="14">${esc(names[c])}</text>`).join("");
  $("#graph").innerHTML = `<svg width="${cols.length * W + 10}" height="${maxY + 10}">${heads}${edges}${nodes}</svg>`;
}

boot().catch((e) => { $("#main").innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`; });
