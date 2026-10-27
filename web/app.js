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

// ---------------------------------------------------------------- theme (cream / dark)
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const b = $("#theme");
  if (b) { b.textContent = dark ? "☀" : "☾"; b.title = dark ? "Switch to the cream light theme" : "Switch to the dark theme"; }
}
function toggleTheme() {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  localSet("pp-theme", next);
  applyTheme(next);
}

async function boot() {
  applyTheme(localGet("pp-theme"));
  $("#theme").onclick = toggleTheme;
  state.users = await api("/api/users");
  const sel = $("#user");
  sel.innerHTML = state.users.map((u) => `<option value="${esc(u.token)}">${esc(u.name)} — ${esc(u.role)}</option>`).join("");
  sel.value = state.user;
  sel.onchange = async () => { state.user = sel.value; localSet("pp-user", state.user); await loadQueue(); await openVisible(state.caseId); };
  $("#reset").onclick = async () => { await api("/api/demo/reset", { method: "POST" }); toast("Demo state reset"); await loadQueue(); await openVisible(state.caseId); };
  $("#new-case").onclick = () => openIntake().catch((e) => toast(e.message, true));
  $("#bench").onclick = () => openBenchmark().catch((e) => toast(e.message, true));
  $("#drawer-close").onclick = () => $("#drawer").classList.add("hidden");
  document.addEventListener("click", (e) => { const c = e.target.closest("[data-rec]"); if (c) inspect(c.dataset.rec); });
  await refreshIntegrations();
  await loadQueue();
  await openVisible(new URLSearchParams(location.search).get("case"));
}

async function refreshIntegrations() {
  const integ = await api("/api/integrations");
  state.integrations = integ;
  const tiles = $("#integ-grid");
  if (tiles) tiles.innerHTML = integrationTiles(integ);
  $("#integrations").innerHTML = integ.rows.filter((r) => r.state !== "N/A").map((r) =>
    `<button class="chip st-${esc(r.state)}" data-jump="s-integ" title="${esc(r.sponsor + ": " + r.state + " — " + r.capability)}">${esc(r.short || r.sponsor)}</button>`).join("");
  document.querySelectorAll("[data-jump]").forEach((el) => (el.onclick = () => { const t = document.getElementById(el.dataset.jump); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); }));
}

const STATE_HELP = { LIVE: "a real execution or request succeeded in this process", CONFIGURED_UNVERIFIED: "configured; no successful call yet",
  FALLBACK: "not configured; local / simulated path in use", UNAVAILABLE: "configured; the last attempt failed", "N/A": "not a runtime integration" };

const ago = (iso) => { if (!iso) return "never"; const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000); return s < 60 ? `${Math.round(s)}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`; };
const usedText = (u) => u === undefined || u === null ? "—" : u === false ? "no" : u === true ? "yes"
  : Array.isArray(u) ? `yes (${u.join(", ")})` : typeof u === "object" ? Object.entries(u).map(([k, v]) => `${k} ${v}`).join(" · ") : String(u);

function integrationTiles(integ) {
  return integ.rows.map((r) => `
    <div class="itile st-${esc(r.state)}">
      <div class="iname"><span>${esc(r.sponsor)}</span><span class="chip st-${esc(r.state)}" title="${esc(STATE_HELP[r.state] || "")}">${esc(r.state.replace(/_/g, " "))}</span></div>
      <div class="icap">${esc(r.capability)}</div>
      ${r.state === "N/A" ? `<div class="idet">${esc(r.detail)}</div>` : `
      <dl class="idl">
        <dt>Configured</dt><dd>${r.configured ? "yes" : "no"}</dd>
        <dt>Connectivity</dt><dd class="conn-${esc(String(r.connectivity).split(" ")[0])}">${esc(r.connectivity)}</dd>
        <dt>Provider</dt><dd title="${esc(r.provider || "")}">${esc(r.provider || "—")}</dd>
        <dt>Last success</dt><dd>${esc(ago(r.last_success))}</dd>
        <dt>Latency</dt><dd class="mono">${r.latency_ms === null || r.latency_ms === undefined ? "—" : esc(r.latency_ms) + " ms"}</dd>
        <dt>Last error</dt><dd class="${r.last_error ? "neg" : ""}">${esc(r.last_error || "none")}</dd>
        <dt>Used in latest run</dt><dd>${esc(usedText(r.used_in_latest))}</dd>
        <dt>Data</dt><dd>${esc(r.data)}</dd>
      </dl>
      <div class="idet" title="${esc(r.detail)}">${esc(r.detail)}</div>`}
    </div>`).join("");
}

function degradedBanner(integ) {
  const bad = (integ?.rows || []).filter((r) => r.state === "UNAVAILABLE");
  return bad.length ? `<div class="banner bad">Degraded: ${bad.map((r) => `${esc(r.sponsor)} (${esc(r.last_error || "unavailable")})`).join(", ")}. PayProof is using its fallback path and says so on every result.</div>` : "";
}

async function runIntegrationCheck() {
  const b = $("#integ-check");
  b.disabled = true; b.textContent = "Checking…";
  try {
    const r = await api("/api/integrations/check", { method: "POST" });
    state.integrations = r.status;
    $("#integ-grid").innerHTML = integrationTiles(r.status);
    $("#integ-last").innerHTML = `<b>Live check ${esc(r.checked_at)}</b><ul class="checks">${r.checks.map((c) =>
      `<li class="${c.ok ? "ok" : c.ran ? "bad" : "skip"}"><span>${c.ok ? "✓" : c.ran ? "✗" : "–"}</span> <b>${esc(c.integration)}</b> <span class="mono">${esc(c.latency_ms)} ms</span> — ${esc(c.detail)}</li>`).join("")}</ul>`;
    await refreshIntegrations();
    toast("Integration check complete");
  } catch (e) { toast(e.message, true); }
  b.disabled = false; b.textContent = "Run live check";
}

// Open `preferred` if this user can see it, otherwise the first case in their queue.
async function openVisible(preferred) {
  const ids = (state.queue || []).map((c) => c.case_id);
  const target = ids.includes(preferred) ? preferred : ids[0];
  if (!target) { $("#main").innerHTML = `<div class="empty">No cases visible to this user.</div>`; return; }
  await openCase(target);
}

async function loadQueue() {
  const q = await api("/api/cases");
  state.queue = q;
  $("#qcount").textContent = `${q.length} cases`;
  $("#queue").innerHTML = q.map((c) => `
    <div class="qitem ${c.case_id === state.caseId ? "active" : ""}" data-case="${esc(c.case_id)}">
      <div class="qrow"><span class="qtitle">${c.tags.includes("user-filed") ? '<span class="chip">new</span> ' : ""}${esc(c.title)}</span>${pill(c.proof_status)}</div>
      <div class="qrow qmeta"><span>${esc(c.case_id)} · ${esc(c.claimant)}</span><span class="mono">exposure ${money(c.exposure)}</span></div>
      <div class="qrow qmeta"><span>claim ${money(c.claimed)} · ${esc(c.verdict.replace(/_/g, " ").toLowerCase())}</span>
        <span>${c.action_state ? pill(c.action_state, "action " + c.action_state) : ""}</span></div>
    </div>`).join("");
  document.querySelectorAll(".qitem").forEach((el) => (el.onclick = () => openCase(el.dataset.case)));
}

async function openCase(id) {
  if (state.caseId !== id) state.lastErr = "";
  state.caseId = id;
  document.querySelectorAll(".qitem").forEach((el) => el.classList.toggle("active", el.dataset.case === id));
  const seq = (state.openSeq = (state.openSeq || 0) + 1);
  if (state.inflight) state.inflight.abort();  // cancel the superseded request instead of letting it race
  const ctl = (state.inflight = new AbortController());
  const main = $("#main");
  if (!state.data || state.data.case_id !== id) main.classList.add("loading");
  try {
    const [data, sources] = await Promise.all([api(`/api/cases/${id}`, { signal: ctl.signal }), api(`/api/cases/${id}/sources`, { signal: ctl.signal })]);
    if (seq !== state.openSeq) return;  // a newer case was opened while this one loaded; don't render stale data
    state.data = data; state.sources = sources;
    render();
    refreshIntegrations().catch(() => {});
  } catch (e) {
    if (e.name === "AbortError" || seq !== state.openSeq) return;
    main.innerHTML = `<div class="card errcard"><h3><span>Could not load ${esc(id)}</span></h3>
      <p>${esc(e.status ? `${e.status} ${e.body?.error || ""}: ${e.message}` : `Network error: ${e.message}`)}</p>
      <div class="btns"><button id="retry" class="primary">Retry</button></div></div>`;
    $("#retry").onclick = () => openCase(id);
  } finally {
    if (seq === state.openSeq) main.classList.remove("loading");
  }
}

function recordById(id) {
  for (const [sys, blk] of Object.entries(state.sources.sources)) {
    const r = blk.records.find((x) => x.id === id);
    if (r) return { sys, name: blk.system, r };
  }
  if (state.sources.dispute.id === id) return { sys: "disputes", name: "dispute-intake", r: state.sources.dispute };
  const sim = state.data.graph.nodes.find((n) => n.id === id && n.system === "sim_ledger");
  if (sim) return { sys: "sim_ledger", name: "payroll-sim ledger (SIMULATED execution, not a source system)", r: sim };
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
  ${degradedBanner(state.integrations)}
  <nav class="nav"><a href="#s-trace">Trace</a><a href="#s-integ">Integrations</a><a href="#s-evidence">1 Evidence</a><a href="#s-reason">2 Hypothesis vs skeptic</a><a href="#s-calc">3 Calculation</a>
    <a href="#s-cf">4 Counterfactuals</a><a href="#s-proof">5 Proof bundle</a><a href="#s-action">6 Action</a><a href="#s-memory">Precedents & security</a><a href="#s-audit">7 Receipt & audit</a></nav>
  <section class="hero">
    <div class="card">
      <div class="dim mono">${esc(d.case_id)} · ${esc(d.dispute.id)} · filed ${esc(d.dispute.filed_at)} · period ${esc(d.dispute.period)}</div>
      <div class="case-title">${esc(d.title)}</div>
      <div>${pill(d.proof_status)} ${pill(d.verdict)} ${d.tags.map((t) => `<span class="chip">${esc(t)}</span>`).join(" ")}</div>
      <div class="narr">“${esc(d.dispute.narrative)}”</div>
      <div class="kpis">
        <div class="kpi"><div class="l">Claimed shortfall</div><div class="v">${money(d.dispute.claimed_shortfall)}</div></div>
        <div class="kpi"><div class="l">Verified due</div><div class="v">${d.proof_status === "VERIFIED" ? money(c.due) : "—"}</div>${d.proof_status === "VERIFIED" ? "" : `<div class="dim" style="font-size:11px">not established (${esc(d.proof_status.replace("_", " ").toLowerCase())})</div>`}</div>
        <div class="kpi"><div class="l">Paid to date</div><div class="v">${money(c.paid)}</div></div>
        <div class="kpi"><div class="l">Variance</div><div class="v ${d.proof_status !== "VERIFIED" ? "" : Number(c.delta) > 0 ? "pos" : Number(c.delta) < 0 ? "neg" : ""}">${d.proof_status === "VERIFIED" ? signed(c.delta) : "—"}</div></div>
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
        <div class="k">Meterless World Model</div><div>${esc(d.world_model.entities)} entities · ${esc(d.world_model.relationships)} edges · ${esc(d.world_model.events)} events · state ${esc(d.world_model.state_hash)}</div>
        <div class="k">WM cross-check</div><div>${d.world_model.cross_check ? (d.world_model.cross_check.passed ? "✅ as-of-cutoff view = engine cash events" : "❌ mismatch") : "n/a"}</div>
        <div class="k">sources</div><div>${Object.entries(d.sources_meta.provenance).map(([k, v]) => esc(k + "=" + v)).join(", ")}</div>
        <div class="k">latency</div><div>${esc(d.telemetry.latency_ms)} ms</div>
      </div>
    </div>
  </section>

  <section class="card full" id="s-trace">
    <h3><span>Agent pipeline trace — this run</span><span class="dim" style="text-transform:none;letter-spacing:0;font-weight:500">${esc(d.run_id)} · ${esc(d.telemetry.latency_ms)} ms total · recorded by the backend, not animated</span></h3>
    <ol class="trace">${(d.trace || []).map((t, i) => `<li><span class="tn">${i + 1}</span><div><div class="tt"><b>${esc(t.agent)}</b><span class="mono dim">${esc(t.ms)} ms</span></div>
      <div class="ts">${esc(t.summary)}</div></div></li>`).join("")}
      <li><span class="tn">${(d.trace || []).length + 1}</span><div><div class="tt"><b>Human approval gate</b><span class="dim">required</span></div>
      <div class="ts">${esc(d.proposed_action.required_permission)} must approve; the system never executes a consequential action on its own${d.proposed_action.escalated ? " · <b>escalated</b>" : ""}.</div></div></li>
      <li><span class="tn">${(d.trace || []).length + 2}</span><div><div class="tt"><b>Meterless H-MEM</b><span class="dim">learning</span></div>
      <div class="ts">${d.precedents ? `${esc(d.precedents.precedents.length)} verified precedent(s) recalled for patterns ${esc(d.precedents.patterns.join(", ") || "none")}` : "—"}; this case is stored only after an approved, postcondition-verified action.</div></div></li></ol>
  </section>

  <section class="card integ" id="s-integ">
    <h3><span>Sponsor integrations</span><span class="dim" style="text-transform:none;letter-spacing:0;font-weight:500">status is runtime truth — a mock never reads LIVE</span></h3>
    <div class="integ-grid" id="integ-grid">${state.integrations ? integrationTiles(state.integrations) : ""}</div>
    <div class="integ-foot"><span class="dim" id="integ-last">Meterless World Model on this case: ${esc(d.world_model.entities)} entities · ${esc(d.world_model.relationships)} bitemporal edges · cross-check ${d.world_model.cross_check ? (d.world_model.cross_check.passed ? "passed" : "FAILED") : "n/a"}</span>
      <button id="integ-check" class="ghost">Run live check</button></div>
  </section>

  <section class="card full" id="s-evidence">
    <h3><span><span class="n">1</span>Temporal evidence — timeline & graph</span><span class="dim" style="text-transform:none;letter-spacing:0">click any record to inspect the original</span></h3>
    <div class="timeline"><div class="tl">${d.timeline.map((e) => e.type === "cutoff"
      ? `<div class="ev cutoff"><div class="d">${esc(e.effective_at)}</div><div class="ty">CUTOFF</div></div>`
      : `<div class="ev" data-rec="${esc(e.record_id)}"><div class="d">eff ${esc(e.effective_at)}<br>rec ${esc(e.recorded_at)}</div>
         <div class="ty">${esc(e.type.replace("_", " "))}</div><div class="mono">${esc(e.record_id)}</div>
         <div class="mono dim">${e.amount ? money(e.amount) : ""}</div>${e.flags.map((f) => `<div class="flag">⚑ ${esc(f.replace(/_/g, " "))}</div>`).join("")}</div>`).join("")}</div></div>
    <div class="graph-wrap" id="graph"></div>
    <div class="legend"><span><i class="l-used"></i>used in calculation</span><span><i class="l-conf"></i>skeptic: confirmed issue</span>
      <span><i class="l-ruled"></i>skeptic: tested & ruled out</span><span><i class="l-unres"></i>unresolved</span>
      <span><i class="l-id"></i>identity link (resolved)</span></div>
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
      ${d.bundle.map((b) => `<div class="claim c-${esc(b.status)}">
        <div class="qrow"><span class="st">${esc(b.statement)}</span>${pill(b.status)}</div>
        <div class="dim">supporting</div><div>${b.supporting.map((i) => cite(i)).join("")}</div>
        ${b.contradicting.length ? `<div class="dim">contradicting / excluded</div><div>${b.contradicting.map((i) => cite(i, "x")).join("")}</div>` : ""}
        <div class="dim">policy: ${b.policy.map(esc).join(", ")}</div>
        ${b.assumptions.length ? `<div class="dim">assumptions: ${b.assumptions.map(esc).join("; ")}</div>` : ""}
        ${b.open_questions.length ? `<div class="warn-text">open: ${b.open_questions.map(esc).join("; ")}</div>` : ""}</div>`).join("")}
    </div>
    <div class="card"><h3><span>Policy verifier — invariants</span></h3>
      <table class="inv">${d.verification.invariants.map((i) => `<tr><td>${i.passed ? "✅" : "❌"}</td><td>${esc(i.invariant)}<div class="dim mono">${esc(i.detail)}</div></td></tr>`).join("")}</table>
      <h3 style="margin-top:14px"><span>Final validator</span>${pill(d.validation.passed ? "VERIFIED" : "REJECTED", d.validation.passed ? "PASSED" : "FAILED")}</h3>
      ${d.validation.errors.map((e) => `<div class="err">${esc(e)}</div>`).join("") || `<div class="dim">All claims cite real records; action is allowlisted and consistent with the proof.</div>`}
    </div>
  </section>

  <section class="grid2" id="s-memory">
    <div class="card"><h3><span>Precedents — Meterless H-MEM</span><span class="dim" style="text-transform:none;letter-spacing:0;font-weight:500">verified outcomes only · never its own case · never alters the calculation</span></h3>
      ${precedentPanel(d)}</div>
    <div class="card"><h3><span>Security — Meterless Scout guard</span>${d.security.quarantined.length ? pill("UNRESOLVED", "quarantined") : pill("VERIFIED", "clean")}</h3>
      ${d.security.quarantined.length ? d.security.quarantined.map((q) => `<div class="finding"><div class="t">${cite(q.record_id)} <span class="mono">${esc(q.field)}</span></div>
        <div class="dim">Embedded instruction detected (${esc(q.kinds.join(", "))}, score ${esc(q.score)}). Text excluded from model context; action escalated to controller. Payload is not logged.</div></div>`).join("")
        : `<p class="dim">No embedded instructions in ${esc(Object.values(state.sources.sources).reduce((n, b) => n + b.records.length, 0))} retrieved records. Intake text is checked before a case is filed; every action carries a signed Scout execution contract.</p>`}
      ${d.security.malformed.length ? `<h4>Malformed records excluded</h4>${d.security.malformed.map((m) => `<div class="finding">${cite(m.record_id)} ${esc(m.field)} is not an exact decimal</div>`).join("")}` : ""}
    </div>
  </section>

  <section class="card full" id="s-action">${actionPanel(d)}</section>
  <section class="card full" id="s-audit"><h3><span><span class="n">7</span>Execution receipt & audit trail</span><span id="chain"></span></h3><div id="receipt"></div><div class="audit" id="audit"></div></section>
  `;
  drawGraph(d.graph);
  $("#integ-check").onclick = runIntegrationCheck;
  document.querySelectorAll("[data-compare]").forEach((el) => (el.onclick = () => openCompare(el.dataset.compare).catch((e) => toast(e.message, true))));
  document.querySelectorAll("[data-open]").forEach((el) => (el.onclick = () => openCase(el.dataset.open)));
  wireActions();
  loadAudit();
}

function cfTable(d) {
  const rows = d.counterfactuals;
  if (!rows.length) return `<div class="dim">No applicable counterfactuals for this case.</div>`;
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r.delta_change || 0))));
  const c = d.calculation;
  return `<table><tr><th>Scenario (hypothetical)</th><th class="num">Due</th><th class="num">Paid</th><th class="num">Variance</th><th class="num">Change vs actual</th><th></th><th>Facts changed</th></tr>
    <tr class="row-actual"><td><b>ACTUAL (observed evidence)</b></td><td class="num">${money(c.due)}</td><td class="num">${money(c.paid)}</td><td class="num">${signed(c.delta)}</td><td class="num">—</td><td></td><td></td></tr>
    ${rows.map((r) => {
      const v = Number(r.delta_change || 0), w = Math.abs(v) / max * 50;
      return `<tr><td><b>${esc(r.title)}</b><div class="dim">${esc(r.question)}</div></td><td class="num">${money(r.due)}</td><td class="num">${money(r.paid)}</td>
      <td class="num">${signed(r.delta)}</td><td class="num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}">${r.delta_change === null ? (r.blocked ? "blocked" : "—") : signed(r.delta_change)}</td>
      <td><div class="bar"><span class="${v >= 0 ? "up" : "down"}" style="left:${v >= 0 ? 50 : 50 - w}%;width:${w}%"></span></div></td>
      <td>${r.changed_facts.map((i) => cite(i)).join("")}</td></tr>`;
    }).join("")}</table>`;
}

const MONEY_KEYS = new Set(["eligible", "collected", "base", "due", "paid", "delta"]);

function waterfallCard(w) {
  if (!w) return "";
  return `<h4>Reconciliation: claimant expectation → verified variance</h4><table>${w.map((r) => `
    <tr class="${r.kind !== "step" ? "row-total" : ""}"><td>${esc(r.label)} ${r.cites.map((i) => cite(i)).join("")}</td>
    <td class="num ${r.kind === "step" ? (Number(r.amount) < 0 ? "neg" : "pos") : ""}">${r.kind === "step" ? signed(r.amount) : money(r.amount)}</td></tr>`).join("")}</table>`;
}

const ORDER = ["PROPOSED", "VALIDATED", "AWAITING_APPROVAL", "APPROVED", "EXECUTED", "VERIFIED"];

function precedentPanel(d) {
  const p = d.precedents;
  if (!p || !p.patterns.length) return `<p class="dim">No evidence patterns on this case, so there is nothing to match.</p>`;
  if (!p.precedents.length) return `<p class="dim">Patterns: ${p.patterns.map((x) => `<span class="chip">${esc(x)}</span>`).join(" ")}</p>
    <p class="dim">No verified precedents yet (cold memory). Settle a case with these patterns (approve + execute) and it becomes recallable here.</p>`;
  return `<p class="dim">Patterns: ${p.patterns.map((x) => `<span class="chip">${esc(x)}</span>`).join(" ")}</p>
    <table><tr><th>Precedent</th><th>Shared patterns</th><th>Outcome</th><th class="num">Relevance</th><th></th></tr>
    ${p.precedents.map((x) => `<tr><td><b>${esc(x.case_id)}</b><div class="dim mono">${esc(x.memory_id)} · ${x.refs.slice(1, 3).map(esc).join(" · ")}</div></td>
      <td>${x.shared_patterns.map((s) => `<span class="chip">${esc(s)}</span>`).join(" ") || "—"}</td>
      <td>${esc((x.verdict || "").replace(/_/g, " ").toLowerCase())} · ${esc((x.action || "").replace(/_/g, " ").toLowerCase())}
        ${x.consistent === null ? "" : x.consistent ? pill("VERIFIED", "consistent") : pill("DISPUTED", "differs")}</td>
      <td class="num">${esc(x.relevance)}</td>
      <td><button class="ghost" data-compare="${esc(x.case_id)}">Compare</button> <button class="ghost" data-open="${esc(x.case_id)}">Open</button></td></tr>`).join("")}</table>`;
}

async function openCompare(otherId) {
  const a = state.data, b = await api(`/api/cases/${otherId}`);
  const row = (k, f) => `<tr><td class="dim">${esc(k)}</td><td>${f(a)}</td><td>${f(b)}</td></tr>`;
  const due = (x) => x.proof_status === "VERIFIED" ? money(x.calculation.due) : "—";
  $("#drawer-title").textContent = `Compare ${a.case_id} ↔ ${otherId}`;
  $("#drawer-body").innerHTML = `<table><tr><th></th><th>${esc(a.case_id)}</th><th>${esc(otherId)}</th></tr>
    ${row("Title", (x) => esc(x.title))}${row("Proof", (x) => pill(x.proof_status))}${row("Verdict", (x) => pill(x.verdict))}
    ${row("Claimed", (x) => money(x.dispute.claimed_shortfall))}${row("Verified due", due)}${row("Paid", (x) => money(x.calculation.paid))}
    ${row("Action", (x) => esc(x.proposed_action.type.replace(/_/g, " ")))}${row("Approval", (x) => esc(x.proposed_action.required_permission))}
    ${row("Skeptic findings", (x) => x.skeptic.findings.map((f) => `<div>${pill(f.outcome)} ${esc(f.title)}</div>`).join(""))}
    ${row("Rules applied", (x) => esc([...new Set(x.calculation.steps.map((s) => s.rule))].join(", ")))}</table>
    <p class="dim">Both sides are live investigations of the current evidence; nothing here is copied from memory.</p>`;
  $("#drawer").classList.remove("hidden");
}

async function exportDossier(caseId) {
  const res = await fetch(`/api/cases/${caseId}/dossier`, { headers: { "X-Demo-User": state.user } });
  if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.message || res.statusText); }
  const url = URL.createObjectURL(await res.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: `payproof-dossier-${caseId}.json` });
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Dossier for ${caseId} downloaded (request ${res.headers.get("X-Request-ID") || "?"})`);
}

function actionPanel(d) {
  const last = d.actions.slice(-1)[0];
  const live = last && !["REJECTED", "EXPIRED"].includes(last.state) ? last : null;
  const p = live || d.proposed_action;
  const act = live;
  const cur = act ? act.state : null;
  const idx = cur ? ORDER.indexOf(cur) : -1;
  const bad = cur === "FAILED";
  const me = state.users.find((u) => u.token === state.user);
  const prev = last && !live ? `<div class="finding">${pill(last.state)} Previous action <span class="mono">${esc(last.id)}</span> ${esc(last.type)}:
      ${esc((last.history.slice(-1)[0] || {}).reason || (last.history.slice(-1)[0] || {}).note || "")}. A fresh investigation produced the proposal below.</div>` : "";
  const after = live && live.state === "VERIFIED" && d.proposed_action.idempotency_key !== live.idempotency_key
    ? `<div class="finding">${pill("VERIFIED", "re-investigated")} After execution the case re-investigates to variance ${esc(signed(d.calculation.delta))}; current recommendation: <b>${esc(d.proposed_action.type.replace(/_/g, " "))}</b>.</div>` : "";
  return `<h3><span><span class="n">6</span>Proposed action — approval gated</span>${act ? pill(cur) : pill("UNDETERMINED", "not yet proposed")}</h3>${prev}${after}
    <div class="steps">${ORDER.map((s, i) => `<span class="stp ${i < idx || cur === "VERIFIED" ? "done" : i === idx ? "cur" : ""}">${esc(s.replace(/_/g, " "))}</span>`).join("→")}
      ${bad ? `<span class="stp bad">${esc(cur)}</span>` : ""}</div>
    <div class="kv">
      <div class="k">Action</div><div><b>${esc(p.type.replace(/_/g, " "))}</b> ${p.amount ? `<span class="mono">${money(p.amount)}</span>` : ""} <span class="chip">simulated adapter</span></div>
      <div class="k">Justification</div><div>${esc(p.justification)}</div>
      <div class="k">Expected result</div><div>${esc(p.expected_result)}</div>
      <div class="k">Affected records</div><div>${p.affected_records.map((i) => cite(i)).join("")}</div>
      <div class="k">Preconditions</div><div class="mono">proof=${esc(p.preconditions.proof_status)} · paid_before=${esc(p.preconditions.expected_paid_before)} · fingerprint=${esc(p.preconditions.source_fingerprint.slice(0, 16))}…</div>
      <div class="k">Required permission</div><div><span class="chip">${esc(p.required_permission)}</span>${p.escalated ? ` ${pill("DISPUTED", "escalated")}` : ""} · SoD: proposer ≠ approver, subject cannot approve</div>
      ${act && act.contracts ? `<div class="k">Scout contracts</div><div class="mono">${act.contracts.map((c) => esc(`${c.contractId} (${c.risk})`)).join("<br>")}</div>` : ""}
      <div class="k">Idempotency key</div><div class="mono">${esc(p.idempotency_key)}</div>
      ${act ? `<div class="k">Action id</div><div class="mono">${esc(act.id)} · proposed by ${esc(act.proposed_by)}${act.approved_by ? " · approved by " + esc(act.approved_by) : ""}</div>` : ""}
      ${act && act.history.length ? `<div class="k">History</div><div class="mono">${act.history.map((h) => esc(`${h.at.slice(11)} ${h.to} by ${h.actor}${h.reason ? " (" + h.reason + ")" : ""}`)).join("<br>")}</div>` : ""}
    </div>
    <div class="btns">
      <button id="b-propose" class="primary">Propose action</button>
      <button id="b-approve" ${act ? "" : "disabled"}>Approve</button>
      <button id="b-reject" class="danger" ${act ? "" : "disabled"}>Reject</button>
      <button id="b-escalate" ${act && cur === "AWAITING_APPROVAL" && act.required_permission !== "controller" ? "" : "disabled"} title="Require controller approval">Escalate</button>
      <button id="b-exec" class="primary" ${act ? "" : "disabled"}>Execute (simulated)</button>
      <span style="flex:1"></span>
      <button id="b-late" class="ghost" title="Inject a late-arriving credit note dated before the cutoff">⚡ Inject late credit note</button>
      <button id="b-fail" class="ghost" title="Make the next adapter call fail">⚡ Fail next execution</button>
      <button id="b-export" class="ghost" title="Download the full decision dossier as JSON">⇩ Export dossier</button>
    </div>
    <div class="dim" style="margin-top:8px">Acting as <b>${esc(me ? me.name + " (" + me.role + ")" : state.user)}</b>. Buttons are not hidden by role on purpose: the backend enforces authorization — try approving as the sales rep.</div>
    <div id="action-err" class="err">${esc(state.lastErr || "")}</div>`;
}

function wireActions() {
  const d = state.data;
  const act = () => d.actions.slice(-1)[0];
  const run = async (fn, ok) => {
    state.lastErr = "";
    try { const r = await fn(); if (ok) toast(ok(r)); }
    catch (e) { state.lastErr = `Backend refused (${e.status || ""} ${e.body?.error || ""}): ${e.message}`; toast(`Rejected by backend: ${e.message}`, true); }
    await loadQueue(); await openCase(d.case_id);
  };
  $("#b-propose").onclick = () => run(() => api(`/api/cases/${d.case_id}/actions`, { method: "POST" }), (r) => `Action ${r.id}: ${r.state}`);
  $("#b-approve").onclick = () => run(() => api(`/api/actions/${act().id}/decision`, { method: "POST", body: JSON.stringify({ decision: "approve" }) }), (r) => `Action ${r.state}`);
  $("#b-reject").onclick = () => run(() => api(`/api/actions/${act().id}/decision`, { method: "POST", body: JSON.stringify({ decision: "reject" }) }), (r) => `Action ${r.state}`);
  $("#b-exec").onclick = () => run(() => api(`/api/actions/${act().id}/execute`, { method: "POST", headers: { "Idempotency-Key": act().idempotency_key } }), (r) => `Action ${r.state}`);
  $("#b-late").onclick = () => run(() => api(`/api/cases/${d.case_id}/simulate/late-event`, { method: "POST" }), (r) => `Injected ${r.injected.id} — evidence changed`);
  $("#b-fail").onclick = () => run(() => api(`/api/sim/fail-next`, { method: "POST" }), () => "Next adapter call will fail");
  $("#b-escalate").onclick = () => run(() => api(`/api/actions/${act().id}/escalate`, { method: "POST", body: JSON.stringify({ note: "escalated from Decision Room" }) }),
    () => "Escalated: controller approval now required");
  $("#b-export").onclick = () => exportDossier(d.case_id).catch((e) => toast(e.message, true));
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
  const cols = ["disputes", "hris", "crm", "clm", "billing", "comp", "payroll", "sim_ledger"];
  const names = { disputes: "dispute", hris: "HRIS", crm: "CRM", clm: "Contracts", billing: "Billing", comp: "Comp plan", payroll: "Payroll", sim_ledger: "Simulated ledger" };
  const W = 172, NW = 154, NH = 40, GAP = 10, TOP = 26;
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
      <rect width="${NW}" height="${NH}"></rect><text x="8" y="16" style="font-weight:600">${esc(n.id.length > 22 ? n.id.slice(0, 21) + "…" : n.id)}</text>
      <text x="8" y="31" class="sub">${esc(n.type.replace("_", " "))}${n.amount ? " · " + esc(money(n.amount)) : ""}</text><title>${esc(n.id)} ${esc(n.label)}</title></g>`;
  }).join("");
  const heads = cols.map((c, ci) => `<text class="col" x="${8 + ci * W}" y="14">${esc(names[c])}</text>`).join("");
  $("#graph").innerHTML = `<svg width="${cols.length * W + 10}" height="${maxY + 10}">${heads}${edges}${nodes}</svg>`;
}

// ---------------------------------------------------------------- dispute intake
const lines = (rows, cols) => (rows || []).map((r) => cols.map((c) => r[c] ?? "").filter((v, i) => v !== "" || i < cols.length - 1).join(", ")).join("\n");
const parseLines = (text, cols) => text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
  const parts = l.split(",").map((x) => x.trim());
  return Object.fromEntries(cols.map((c, i) => [c, parts[i] || ""]).filter(([, v]) => v !== ""));
});
const field = (id, label, value, type = "text", extra = "") =>
  `<label class="f"><span>${esc(label)}</span><input id="f-${id}" type="${type}" value="${esc(value ?? "")}" ${extra}></label>`;
const area = (id, label, value, hint) =>
  `<label class="f wide"><span>${esc(label)} <em class="dim">${esc(hint)}</em></span><textarea id="f-${id}" rows="3">${esc(value)}</textarea></label>`;

async function openIntake() {
  const t = await api(`/api/intake/template?from=${encodeURIComponent(state.caseId || "")}`);
  const f = t.form, am = f.amendment || {};
  $("#drawer-title").textContent = "File a new dispute";
  $("#drawer-body").innerHTML = `
    <p class="dim">Prefilled from the actual records of ${esc(t.from)}. Edit anything: the same deterministic pipeline, skeptic,
      World Model and approval gate run on the new case. Amounts are exact decimals; dates are YYYY-MM-DD.</p>
    <div class="form">
      ${field("account", "Account", f.account)}${field("title", "Case title (optional)", f.title)}
      ${field("rep_name", "Rep name (HRIS)", f.rep_name)}${field("rep_email", "Rep email (HRIS)", f.rep_email, "email")}
      ${field("crm_name", "CRM user name", f.crm_name)}${field("crm_email", "CRM user email", f.crm_email, "email")}
      ${field("crm_amount", "CRM amount", f.crm_amount)}${field("close_date", "Close date", f.close_date, "date")}
      <label class="f"><span>Stage</span><select id="f-stage">${["closed_won", "negotiation", "proposal", "closed_lost"].map((x) => `<option ${x === f.stage ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label class="f"><span>Commission period</span><select id="f-period">${["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"].map((x) => `<option ${x === f.period ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      ${field("split_pct", "Rep split %", f.split_pct)}${field("co_seller_name", "Co-seller (if split < 100)", "")}
      ${field("contract_tcv", "Contract TCV (blank = no contract)", f.contract_tcv)}${field("contract_signed", "Contract signed", f.contract_signed, "date")}
      ${field("am_new_tcv", "Amendment new TCV (optional)", am.new_tcv)}${field("am_effective", "Amendment effective", am.effective, "date")}
      ${field("am_signed", "Amendment signed", am.signed, "date")}${field("invoice_amount", "Invoice amount", f.invoice_amount)}
      ${field("invoice_date", "Invoice date", f.invoice_date, "date")}${field("claimed_shortfall", "Claimed shortfall", f.claimed_shortfall)}
      ${area("payments", "Payments", lines(f.payments, ["amount", "value_date", "recorded_date"]), "one per line: amount, value date[, recorded date]")}
      ${area("credit_notes", "Credit notes", lines(f.credit_notes, ["amount", "issued_date"]), "amount, issued date")}
      ${area("refunds", "Refunds", lines(f.refunds, ["amount", "value_date"]), "amount, value date")}
      ${area("payroll", "Payroll lines paid", lines(f.payroll, ["amount", "posted_date", "type"]), "amount, posted date, commission|clawback|adjustment")}
      ${field("ex_rate", "Rate exception (optional, e.g. 0.12)", "")}
      <label class="f"><span>Exception approved?</span><input id="f-ex_approved" type="checkbox"></label>
      <label class="f"><span>Payments feed available?</span><input id="f-feed" type="checkbox" ${f.payments_feed_available ? "checked" : ""}></label>
      <label class="f wide"><span>Rep's narrative</span><textarea id="f-narrative" rows="2">${esc(f.narrative)}</textarea></label>
    </div>
    <div class="btns"><button id="f-submit" class="primary">File dispute and investigate</button></div>
    <div id="f-err" class="err"></div>`;
  $("#drawer").classList.remove("hidden");
  $("#f-submit").onclick = submitIntake;
}

async function submitIntake() {
  const v = (id) => $(`#f-${id}`).value.trim();
  const form = {
    account: v("account"), title: v("title"), rep_name: v("rep_name"), rep_email: v("rep_email"), crm_name: v("crm_name"),
    crm_email: v("crm_email"), crm_amount: v("crm_amount"), close_date: v("close_date"), stage: v("stage"), period: v("period"),
    split_pct: v("split_pct") || "100", co_seller_name: v("co_seller_name"), contract_tcv: v("contract_tcv"),
    contract_signed: v("contract_signed"), invoice_amount: v("invoice_amount"), invoice_date: v("invoice_date"),
    claimed_shortfall: v("claimed_shortfall"), narrative: v("narrative"), payments_feed_available: $("#f-feed").checked,
    payments: parseLines(v("payments"), ["amount", "value_date", "recorded_date"]),
    credit_notes: parseLines(v("credit_notes"), ["amount", "issued_date"]),
    refunds: parseLines(v("refunds"), ["amount", "value_date"]),
    payroll: parseLines(v("payroll"), ["amount", "posted_date", "type"]),
  };
  if (v("am_new_tcv")) form.amendment = { new_tcv: v("am_new_tcv"), effective: v("am_effective"), signed: v("am_signed") };
  if (v("ex_rate")) form.exception = { rate: v("ex_rate"), approved: $("#f-ex_approved").checked };
  try {
    const r = await api("/api/cases", { method: "POST", body: JSON.stringify(form) });
    $("#drawer").classList.add("hidden");
    toast(`Filed ${r.case_id}: ${r.proof_status} → ${r.action.replace(/_/g, " ")}`);
    await loadQueue();
    await openCase(r.case_id);
  } catch (e) {
    $("#f-err").textContent = `${e.status || ""} ${e.message}`;
  }
}

// ---------------------------------------------------------------- live benchmark
async function openBenchmark() {
  $("#drawer-title").textContent = "Benchmark";
  $("#drawer").classList.remove("hidden");
  const renderReport = (r) => {
    const a = r.agent, b = r.baseline, s = r.safety;
    const row = (k, x, y) => `<tr><td>${esc(k)}</td><td class="num">${esc(x)}</td><td class="num">${esc(y)}</td></tr>`;
    $("#drawer-body").innerHTML = `
      <p class="dim">${esc(r.sample_size)} hand-labelled synthetic cases · generated ${esc(r.generated_at)}. Cases were authored alongside the engine.</p>
      <table><tr><th>Metric</th><th class="num">PayProof</th><th class="num">Baseline</th></tr>
        ${row("Decisions correct", `${a.decisions_correct}/${a.cases}`, `${b.decisions_correct}/${b.cases}`)}
        ${row("Exact due amount", `${a.money_exact}/${a.money_cases}`, `${b.money_exact}/${b.money_cases}`)}
        ${row("Mean abs. due error", "$" + a.money_mean_abs_error, "$" + b.money_mean_abs_error)}
        ${row("Wrong adjustments", a.adjustment_false_positives, b.adjustment_false_positives)}
        ${row("Correct abstentions", `${a.correct_abstentions}/${a.abstention_needed}`, `${b.correct_abstentions}/${b.abstention_needed}`)}
        ${row("Citation coverage", (a.citation_coverage * 100).toFixed(1) + "%", (b.citation_coverage * 100).toFixed(1) + "%")}
        ${row("Reproducibility", (a.reproducibility * 100).toFixed(1) + "%", "—")}
        ${row("Latency p50", a.latency_ms_p50 + " ms", "—")}
      </table>
      <h4>Safety suite</h4>
      <table>${row("Unauthorized succeeded", `${s.unauthorized_actions_succeeded} / ${s.unauthorized_attempts}`, "")}
        ${row("Duplicate actions", `${s.duplicate_actions_created} / ${s.duplicate_execution_requests} requests`, "")}
        ${row("Stale executions blocked", `${s.stale_executions_blocked} / ${s.stale_evidence_scenarios}`, "")}
        ${row("Receipts despite failed postcondition", `${s.receipts_issued_despite_failed_postcondition} / ${s.forced_postcondition_failures}`, "")}</table>
      <h4>Model usage</h4><pre>${esc(JSON.stringify(a.model_calls_by_model))}</pre>
      <div class="btns"><button id="bench-run" class="primary">Re-run benchmark now</button></div><div id="bench-err" class="err"></div>`;
    $("#bench-run").onclick = async () => {
      $("#bench-run").disabled = true; $("#bench-run").textContent = "Running…";
      try { renderReport(await api("/api/benchmark/run", { method: "POST" })); toast("Benchmark re-run complete"); }
      catch (e) { $("#bench-err").textContent = `${e.status || ""} ${e.message}`; $("#bench-run").disabled = false; $("#bench-run").textContent = "Re-run benchmark now"; }
    };
  };
  try { renderReport(await api("/api/benchmark")); }
  catch (e) { $("#drawer-body").innerHTML = `<p class="dim">No report yet.</p><div class="btns"><button id="bench-run" class="primary">Run benchmark</button></div><div id="bench-err" class="err"></div>`;
    $("#bench-run").onclick = async () => renderReport(await api("/api/benchmark/run", { method: "POST" })); }
}

boot().catch((e) => { $("#main").innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`; });
