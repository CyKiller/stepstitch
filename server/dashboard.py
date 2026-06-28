"""Read-only operator dashboard for the StepStitch ingest host.

A single self-contained HTML page (no external assets, no build step) served at
``GET /dashboard``. It calls only the **read-only / draft** operator endpoints with the
admin bearer token the operator pastes in (kept in sessionStorage, never persisted). It can
preview drafts and run a **dry-run** deliver, but exposes no destructive action.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StepStitch — operator dashboard</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#272b35; --fg:#e6e8ec; --mut:#9aa3b2;
          --acc:#5b9dff; --ok:#3fb950; --warn:#d29922; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--fg); }
  header { display:flex; gap:10px; align-items:center; padding:12px 16px;
           border-bottom:1px solid var(--line); flex-wrap:wrap; }
  header h1 { font-size:15px; margin:0 12px 0 0; font-weight:600; }
  header .spacer { flex:1; }
  input, button, select { font:inherit; color:var(--fg); background:var(--panel);
           border:1px solid var(--line); border-radius:6px; padding:6px 10px; }
  button { cursor:pointer; }
  button.primary { background:var(--acc); color:#0b1020; border-color:var(--acc); font-weight:600; }
  .wrap { display:grid; grid-template-columns:340px 1fr; gap:0; height:calc(100vh - 53px); }
  .list { border-right:1px solid var(--line); overflow:auto; }
  .row { padding:10px 14px; border-bottom:1px solid var(--line); cursor:pointer; }
  .row:hover { background:var(--panel); }
  .row.sel { background:#1d2330; }
  .row .id { font-family:ui-monospace,monospace; font-size:12px; color:var(--acc); }
  .row .meta { color:var(--mut); font-size:12px; }
  .detail { overflow:auto; padding:16px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:12px 14px; margin-bottom:12px; }
  .card h3 { margin:0 0 8px; font-size:13px; color:var(--mut); text-transform:uppercase;
             letter-spacing:.04em; }
  .grade { font-weight:700; }
  pre { white-space:pre-wrap; word-break:break-word; background:#0b0d12; border:1px solid var(--line);
        border-radius:6px; padding:10px; font:12px/1.5 ui-monospace,monospace; max-height:340px;
        overflow:auto; }
  .pill { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px;
          border:1px solid var(--line); color:var(--mut); }
  .muted { color:var(--mut); }
  .err { color:#f85149; }
  .actions { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
  .flow { display:flex; flex-wrap:wrap; align-items:center; gap:6px; padding:8px 16px;
          border-bottom:1px solid var(--line); font-size:12px; color:var(--mut);
          background:var(--panel); }
  .flow b { color:var(--fg); font-weight:600; }
  .flow .arr { color:var(--acc); }
  .footer { padding:8px 16px; border-top:1px solid var(--line); font-size:11px;
            color:var(--mut); background:var(--panel); }
  .label { font-size:11px; color:var(--mut); margin-top:6px; font-style:italic; }
  .kv { color:var(--fg); }
</style>
</head>
<body>
<header>
  <h1>StepStitch</h1>
  <span class="pill">operator console</span>
  <span class="spacer"></span>
  <input id="token" type="password" placeholder="admin bearer token" size="28" autocomplete="off">
  <button id="save">Use token</button>
  <button id="reload" class="primary">Load traces</button>
  <button id="corpus">Show Corpus</button>
  <button id="audit">Show Audit</button>
  <button id="agents">Agents</button>
  <button id="scrub">Scrub policy</button>
</header>
<div class="flow">
  <b>Customer bug</b><span class="arr">→</span>
  <b>privacy scrub</b><span class="arr">→</span>
  <b>replayability score</b><span class="arr">→</span>
  <b>Playwright repro</b><span class="arr">→</span>
  <b>draft ticket/PR</b><span class="arr">→</span>
  <b>verified fix</b>
</div>
<div class="footer" id="statusbar" style="border-top:none">Paste the admin token, then “Use token”, to see host status.</div>
<div class="wrap">
  <div class="list" id="list"><div class="row muted">Paste the admin token, then “Load traces”.</div></div>
  <div class="detail" id="detail"><p class="muted">Select a trace to inspect its sanitized evidence.</p></div>
</div>
<div class="footer">Operator console · every read and config change is audited · records are scrubbed server-side before storage · drafts are previews, nothing is sent · evidence is never edited or deleted here.</div>
<script nonce="__CSP_NONCE__">
(function () {
  var API = "/api/stepstitch/v1";
  var tokenEl = document.getElementById("token");
  var listEl = document.getElementById("list");
  var detailEl = document.getElementById("detail");
  var selected = null;

  tokenEl.value = sessionStorage.getItem("ss_token") || "";
  document.getElementById("save").onclick = function () {
    sessionStorage.setItem("ss_token", tokenEl.value.trim());
    loadStatus();
  };

  async function loadStatus() {
    try {
      var s = await adminApi("/status");
      document.getElementById("statusbar").innerHTML =
        'Host status · profile <b class="kv">' + esc(s.profile) + '</b> · retention ' +
        esc(s.retention_days) + 'd · traces <b class="kv">' + esc(s.traces) +
        '</b> · agents <b class="kv">' + esc(s.agents_active) + '/' + esc(s.agents_total) +
        '</b> active · audit events <b class="kv">' + esc(s.audit_events) + '</b>';
    } catch (e) { /* leave the prompt text */ }
  }
  document.getElementById("reload").onclick = loadTraces;
  document.getElementById("corpus").onclick = loadCorpus;
  document.getElementById("audit").onclick = loadAudit;
  document.getElementById("agents").onclick = loadAgents;
  document.getElementById("scrub").onclick = loadScrub;

  // /admin/* routes (agent connections) live outside the service prefix.
  async function adminApi(path, opts) {
    var r = await fetch("/admin" + path, Object.assign({ headers: hdr() }, opts || {}));
    if (!r.ok) throw new Error("HTTP " + r.status + " on /admin" + path);
    return r.json();
  }

  function hdr() { return { "Authorization": "Bearer " + (tokenEl.value.trim()) }; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;" }[c]; }); }
  // esc() is HTML-text-only. Use escAttr() for any value placed inside a quoted attribute,
  // and safeUrl() to gate hrefs to http(s) so a javascript:/data: scheme can never execute.
  function escAttr(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]; }); }
  function safeUrl(u) { u = String(u == null ? "" : u).trim();
    return /^https?:\/\//i.test(u) ? u : ""; }

  async function api(path, opts) {
    var r = await fetch(API + path, Object.assign({ headers: hdr() }, opts || {}));
    if (!r.ok) throw new Error("HTTP " + r.status + " on " + path);
    return r.json();
  }

  async function loadTraces() {
    listEl.innerHTML = '<div class="row muted">Loading…</div>';
    try {
      var data = await api("/sessions?limit=100");
      var items = data.sessions || [];
      if (!items.length) { listEl.innerHTML = '<div class="row muted">No traces.</div>'; return; }
      listEl.innerHTML = "";
      items.forEach(function (it) {
        var d = document.createElement("div");
        d.className = "row";
        d.innerHTML = '<div class="id">' + esc(it.trace_id) + '</div>' +
          '<div class="meta">' + esc(it.app_id || "—") + ' · ' + esc(it.project_id || "—") +
          ' · ' + esc(it.created_at || "") + '</div>';
        d.onclick = function () { select(it.trace_id, d); };
        listEl.appendChild(d);
      });
    } catch (e) { listEl.innerHTML = '<div class="row err">' + esc(e.message) + '</div>'; }
  }

  async function loadCorpus() {
    listEl.innerHTML = '<div class="row muted">Loading Corpus…</div>';
    try {
      var data = await api("/corpus?limit=100");
      var items = data.entries || [];
      if (!items.length) { listEl.innerHTML = '<div class="row muted">No verified fixes in corpus.</div>'; return; }
      listEl.innerHTML = "";
      items.forEach(function (it) {
        var d = document.createElement("div");
        d.className = "row";
        var fixText = it.fix_ref ? ' · Fix: ' + it.fix_ref : '';
        d.innerHTML = '<div class="id">' + esc(it.trace_id) + '</div>' +
          '<div class="meta"><span style="color:var(--ok)">' + esc(it.verdict) + '</span>' + esc(fixText) + '</div>';
        d.onclick = function () { select(it.trace_id, d); };
        listEl.appendChild(d);
      });
    } catch (e) { listEl.innerHTML = '<div class="row err">' + esc(e.message) + '</div>'; }
  }

  async function loadAudit() {
    detailEl.innerHTML = '<p class="muted">Loading audit trail…</p>';
    try {
      var data = await api("/audit?limit=200");
      var entries = data.entries || [];
      if (!entries.length) { detailEl.innerHTML = '<div class="card"><p class="muted">No audit entries yet.</p></div>'; return; }
      var rows = entries.map(function (e) {
        var d = "";
        if (e.detail && typeof e.detail === "object") {
          d = e.detail.trace_id || e.detail.correlation_id || JSON.stringify(e.detail);
        }
        return '<tr>' +
          '<td class="muted" style="white-space:nowrap;padding:4px 10px 4px 0">' + esc(e.created_at || "") + '</td>' +
          '<td style="padding:4px 10px 4px 0"><span class="pill">' + esc(e.action) + '</span></td>' +
          '<td style="padding:4px 10px 4px 0">' + esc(e.actor) + '</td>' +
          '<td class="muted" style="padding:4px 0;font-family:ui-monospace,monospace;font-size:12px">' + esc(d) + '</td>' +
          '</tr>';
      }).join("");
      detailEl.innerHTML = '<div class="card"><h3>Audit trail — every operator read is recorded</h3>' +
        '<div class="muted" style="margin-bottom:8px">Newest first · ' + entries.length +
        ' entries · detail carries structural ids only, never PII.</div>' +
        '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
        '<thead><tr style="text-align:left;color:var(--mut)">' +
        '<th style="padding:4px 10px 4px 0">Time</th><th style="padding:4px 10px 4px 0">Action</th>' +
        '<th style="padding:4px 10px 4px 0">Actor</th><th style="padding:4px 0">Detail</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table></div>';
    } catch (e) { detailEl.innerHTML = '<div class="card"><p class="err">' + esc(e.message) + '</p></div>'; }
  }

  async function loadAgents() {
    detailEl.innerHTML = '<p class="muted">Loading agent connections…</p>';
    try {
      await refreshAgents(null);
    } catch (e) {
      detailEl.innerHTML = '<div class="card"><p class="err">' + esc(e.message) +
        '</p><p class="muted">Agent connections require the admin token and shared-token mode.</p></div>';
    }
  }

  async function refreshAgents(justIssued) {
    var data = await adminApi("/agents");
    renderAgents(data.agents || [], justIssued, await agentActivity());
  }

  // Roll up recent agent reads + denials per agent from the audit trail (best-effort).
  async function agentActivity() {
    var act = {};
    function bump(id, when, key) {
      if (!id) return;
      var a = act[id] || (act[id] = { reads: 0, denials: 0, last: "" });
      a[key] += 1; if (!a.last || (when || "") > a.last) a.last = when || "";
    }
    try {
      var acc = await api("/audit?action=stepstitch.agent_access&limit=500");
      (acc.entries || []).forEach(function (e) { bump((e.detail || {}).agent_id, e.created_at, "reads"); });
      var den = await api("/audit?action=stepstitch.agent_denied&limit=500");
      (den.entries || []).forEach(function (e) { bump((e.detail || {}).agent_id, e.created_at, "denials"); });
    } catch (e) { /* activity is best-effort */ }
    return act;
  }

  function renderAgents(agents, justIssued, activity) {
    var scopes = ["summaries", "repros", "drafts", "none"];
    var opts = scopes.map(function (s) {
      return '<option value="' + escAttr(s) + '">' + esc(s) + '</option>';
    }).join("");
    var tokenHtml = "";
    if (justIssued) {
      // Ready-to-paste MCP client config, carrying THIS agent's scoped token (not the
      // admin token) + this host's own origin. Connect any MCP client (Claude, Copilot,
      // OpenAI, Vertex, Bedrock, LangGraph) with no bespoke wiring.
      var mcpConfig = JSON.stringify({
        mcpServers: {
          stepstitch: {
            command: "python",
            args: ["-m", "stepstitch_service.mcp_cli"],
            env: {
              STEPSTITCH_BASE_URL: window.location.origin + "/api/stepstitch/v1",
              STEPSTITCH_TOKEN: justIssued.token
            }
          }
        }
      }, null, 2);
      tokenHtml =
        '<div class="card" style="border-color:var(--acc)">' +
        '<h3 style="color:var(--acc)">New token for ' + esc(justIssued.name) +
        ' (' + esc(justIssued.scope) + ')</h3>' +
        '<div class="muted" style="margin-bottom:6px">Copy now — shown once, stored only as a hash.</div>' +
        '<pre>' + esc(justIssued.token) + '</pre>' +
        '<div class="muted" style="margin:10px 0 6px">MCP client config — paste into Claude / Copilot / any MCP client:</div>' +
        '<button id="ag-copy-mcp" style="margin-bottom:6px">Copy config</button>' +
        '<pre id="ag-mcp">' + esc(mcpConfig) + '</pre></div>';
    }
    var rows = agents.map(function (a) {
      var act = (activity || {})[a.id] || { reads: 0, denials: 0, last: "" };
      var status = a.revoked
        ? '<span class="muted">revoked</span>'
        : '<span style="color:var(--ok)">active</span>';
      var denials = act.denials
        ? '<span style="color:var(--warn)">' + act.denials + '</span>' : '0';
      var btn = a.revoked ? ''
        : '<button class="ag-revoke" data-id="' + escAttr(a.id) + '">Revoke</button>';
      return '<tr>' +
        '<td style="padding:4px 10px 4px 0">' + esc(a.name) + '</td>' +
        '<td style="padding:4px 10px 4px 0"><span class="pill">' + esc(a.scope) + '</span></td>' +
        '<td style="padding:4px 10px 4px 0">' + status + '</td>' +
        '<td style="padding:4px 10px 4px 0">' + act.reads + '</td>' +
        '<td style="padding:4px 10px 4px 0">' + denials + '</td>' +
        '<td class="muted" style="padding:4px 10px 4px 0;font-size:11px">' + esc(act.last || "—") + '</td>' +
        '<td style="padding:4px 0">' + btn + '</td></tr>';
    }).join("");
    detailEl.innerHTML =
      '<div class="card"><h3>Connect an agent</h3>' +
      '<div class="muted" style="margin-bottom:8px">Each agent gets its own scoped token. ' +
      'Scope limits what it can read over MCP: summaries · repros · drafts · none.</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
      '<input id="ag-name" placeholder="agent name (e.g. Claude repro)" size="22">' +
      '<select id="ag-scope">' + opts + '</select>' +
      '<button id="ag-add" class="primary">Register</button></div></div>' +
      tokenHtml +
      '<div class="card"><h3>Registered agents</h3>' +
      (agents.length
        ? '<table style="width:100%;border-collapse:collapse;font-size:13px"><thead>' +
          '<tr style="text-align:left;color:var(--mut)">' +
          '<th style="padding:4px 10px 4px 0">Name</th><th style="padding:4px 10px 4px 0">Scope</th>' +
          '<th style="padding:4px 10px 4px 0">Status</th><th style="padding:4px 10px 4px 0">Reads</th>' +
          '<th style="padding:4px 10px 4px 0">Denials</th><th style="padding:4px 10px 4px 0">Last seen</th>' +
          '<th></th></tr></thead><tbody>' +
          rows + '</tbody></table>'
        : '<p class="muted">No agents registered yet.</p>') +
      '</div>';
    document.getElementById("ag-add").onclick = registerAgent;
    var cp = document.getElementById("ag-copy-mcp");
    if (cp) cp.onclick = function () {
      var t = document.getElementById("ag-mcp").textContent;
      if (navigator.clipboard) navigator.clipboard.writeText(t);
    };
    Array.prototype.forEach.call(document.querySelectorAll(".ag-revoke"), function (b) {
      b.onclick = function () { revokeAgent(b.getAttribute("data-id")); };
    });
  }

  async function registerAgent() {
    var name = document.getElementById("ag-name").value.trim();
    var scope = document.getElementById("ag-scope").value;
    if (!name) { return; }
    try {
      var res = await adminApi("/agents", { method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
        body: JSON.stringify({ name: name, scope: scope }) });
      await refreshAgents(res);
    } catch (e) { show("Could not register agent", e.message); }
  }

  async function revokeAgent(id) {
    try {
      await adminApi("/agents/" + encodeURIComponent(id) + "/revoke",
        { method: "POST", headers: hdr() });
      await refreshAgents(null);
    } catch (e) { show("Could not revoke agent", e.message); }
  }

  var scrubState = { patterns: [], keys: [] };
  async function loadScrub() {
    detailEl.innerHTML = '<p class="muted">Loading scrub policy…</p>';
    try {
      var cfg = await adminApi("/config/scrub");
      scrubState.patterns = (cfg.extra_redactions || []).map(function (p) { return [p[0], p[1]]; });
      scrubState.keys = (cfg.extra_forbidden_keys || []).slice();
      renderScrub(cfg.base_profile);
    } catch (e) { detailEl.innerHTML = '<div class="card"><p class="err">' + esc(e.message) + '</p></div>'; }
  }

  function renderScrub(baseProfile) {
    var patRows = scrubState.patterns.map(function (p, i) {
      return '<tr><td style="padding:3px 10px 3px 0">' + esc(p[0]) + '</td>' +
        '<td style="padding:3px 10px 3px 0"><code>' + esc(p[1]) + '</code></td>' +
        '<td><button class="sc-del-pat" data-i="' + i + '">Remove</button></td></tr>';
    }).join("");
    var keyRows = scrubState.keys.map(function (k, i) {
      return '<span class="pill" style="margin:0 6px 6px 0">' + esc(k) +
        ' <button class="sc-del-key" data-i="' + i + '" ' +
        'style="border:none;background:none;color:var(--mut);padding:0 0 0 4px">×</button></span>';
    }).join("");
    detailEl.innerHTML =
      '<div class="card"><h3>Scrub policy</h3><div class="muted">Base profile ' +
      '<b class="kv">' + esc(baseProfile) + '</b>. Additions below can only ' +
      '<strong>tighten</strong> — they add redaction, never remove the built-in PII rules.</div></div>' +
      '<div class="card"><h3>Custom redaction patterns</h3>' +
      (scrubState.patterns.length
        ? '<table style="font-size:13px;border-collapse:collapse"><thead><tr style="text-align:left;color:var(--mut)">' +
          '<th style="padding:3px 10px 3px 0">Label</th><th style="padding:3px 10px 3px 0">Regex</th><th></th></tr></thead><tbody>' +
          patRows + '</tbody></table>'
        : '<p class="muted">None yet.</p>') +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">' +
      '<input id="sc-label" placeholder="label (e.g. empid)" size="16">' +
      '<input id="sc-regex" placeholder="regex (e.g. EMP-\\d+)" size="22">' +
      '<button id="sc-add-pat">Add pattern</button></div></div>' +
      '<div class="card"><h3>Extra dropped metadata keys</h3>' +
      '<div style="margin-bottom:6px">' + (keyRows || '<span class="muted">None.</span>') + '</div>' +
      '<div style="display:flex;gap:8px"><input id="sc-key" placeholder="metadata key" size="16">' +
      '<button id="sc-add-key">Add key</button></div></div>' +
      '<div class="card"><h3>Redaction preview</h3>' +
      '<div class="muted" style="margin-bottom:6px">What the current (unsaved) patterns would redact:</div>' +
      '<textarea id="sc-pv-in" rows="2" placeholder="paste sample free text…" ' +
      'style="width:100%;box-sizing:border-box;background:#0b0d12;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px;font:inherit"></textarea>' +
      '<button id="sc-pv-btn" style="margin-top:6px">Preview</button>' +
      '<pre id="sc-pv-out"></pre></div>' +
      '<div class="actions"><button id="sc-save" class="primary">Save scrub policy</button></div>';

    document.getElementById("sc-add-pat").onclick = function () {
      var l = document.getElementById("sc-label").value.trim();
      var r = document.getElementById("sc-regex").value;
      if (l && r) { scrubState.patterns.push([l, r]); renderScrub(baseProfile); }
    };
    document.getElementById("sc-add-key").onclick = function () {
      var k = document.getElementById("sc-key").value.trim();
      if (k) { scrubState.keys.push(k); renderScrub(baseProfile); }
    };
    Array.prototype.forEach.call(document.querySelectorAll(".sc-del-pat"), function (b) {
      b.onclick = function () { scrubState.patterns.splice(+b.getAttribute("data-i"), 1); renderScrub(baseProfile); };
    });
    Array.prototype.forEach.call(document.querySelectorAll(".sc-del-key"), function (b) {
      b.onclick = function () { scrubState.keys.splice(+b.getAttribute("data-i"), 1); renderScrub(baseProfile); };
    });
    document.getElementById("sc-pv-btn").onclick = async function () {
      try {
        var res = await adminApi("/scrub/preview", { method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
          body: JSON.stringify({ text: document.getElementById("sc-pv-in").value,
                                 extra_redactions: scrubState.patterns }) });
        document.getElementById("sc-pv-out").textContent = res.redacted || "";
      } catch (e) { document.getElementById("sc-pv-out").textContent = e.message; }
    };
    document.getElementById("sc-save").onclick = async function () {
      try {
        await adminApi("/config/scrub", { method: "PUT",
          headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
          body: JSON.stringify({ extra_redactions: scrubState.patterns,
                                 extra_forbidden_keys: scrubState.keys }) });
        show("Saved", "Scrub policy updated. New traces are scrubbed with these rules.");
      } catch (e) { show("Could not save scrub policy", e.message); }
    };
  }

  function card(title, bodyHtml) {
    return '<div class="card"><h3>' + esc(title) + '</h3>' + bodyHtml + '</div>';
  }

  async function select(id, el) {
    if (selected) selected.classList.remove("sel");
    selected = el; el.classList.add("sel");
    detailEl.innerHTML = '<p class="muted">Loading ' + esc(id) + '…</p>';
    try {
      var s = await api("/session/" + id + "/summary");
      var rep = await api("/session/" + id + "/replayability");
      var pp = await api("/session/" + id + "/privacy-posture");
      var diag = await api("/session/" + id + "/diagnostic-summary");
      var verif = await api("/session/" + id + "/verifications").catch(function() { return { verifications: [] }; });
      var sm = s.summary || {};
      var rr = rep.replayability || {};
      var html = "";
      html += '<div class="actions">' +
        '<button id="act-modelview" class="primary">What the model sees</button>' +
        '<button id="act-repro">View Playwright repro</button>' +
        '<button id="act-drafts">Preview drafts</button>' +
        '<button id="act-github">Dry-run GitHub PR</button>' +
        '<button id="act-deliver">Dry-run deliver</button>' +
        '</div>';
      html += card("Summary",
        '<div>' + esc(sm.headline || "") + '</div>' +
        '<div class="muted">route ' + esc(sm.route) + ' · steps ' + esc(sm.step_count) +
        ' · ' + esc(sm.privacy_status || "") + '</div>');

      var vhtml = "";
      var vlist = verif.verifications || [];
      if (vlist.length) {
        var current = vlist[0];
        var color = current.verdict === "confirmed_fixed" ? "var(--ok)" : "var(--warn)";
        vhtml += '<div>Status: <span style="font-weight:700;color:' + color + '">' + esc(current.verdict) + '</span></div>';
        vhtml += '<ul style="margin:8px 0 0;padding-left:20px;font-size:12px;color:var(--mut)">';
        vlist.forEach(function (v) {
          var ref = v.fix_ref ? ' (Fix: ' + v.fix_ref + ')' : '';
          var runUrl = safeUrl(v.run_url);
          var link = runUrl ? ' · <a href="' + escAttr(runUrl) + '" target="_blank" rel="noopener noreferrer" style="color:var(--acc)">CI Run</a>' : '';
          vhtml += '<li style="margin-bottom:4px"><strong>' + esc(v.verdict) + '</strong>' + esc(ref) + link + ' · ' + esc(v.created_at || "") + '</li>';
        });
        vhtml += '</ul>';
      } else {
        vhtml += '<div class="muted">No verification runs recorded yet. Run the Playwright test in CI to report results.</div>';
      }
      html += card("Verification & Fix Status", vhtml);

      html += card("Replayability",
        '<span class="grade">' + esc(rr.grade) + '</span> · score ' + esc(rr.score) +
        (rr.warnings && rr.warnings.length ? '<pre>' + esc(JSON.stringify(rr.warnings, null, 2)) + '</pre>' : ''));
      var diagBits = [];
      if (sm.failing_status != null) diagBits.push('HTTP <span class="kv">' + esc(sm.failing_status) + '</span>');
      if (sm.exception_type) diagBits.push('exception <span class="kv">' + esc(sm.exception_type) + '</span>');
      if (sm.diagnostic_endpoint) diagBits.push('endpoint <span class="kv">' + esc(sm.diagnostic_endpoint) + '</span>');
      html += card("Diagnostic — sanitized",
        (diagBits.length ? '<div class="muted">' + diagBits.join(' · ') + '</div>' : '') +
        '<div style="margin-top:6px">' + esc((diag.diagnostic || {}).recommended_next_step || "") + '</div>');

      var scrub = pp.scrub || {};
      var fields = scrub.scrubbed_fields || [];
      var scrubStatus = scrub.scrub_status || "—";
      var fieldsHtml = fields.length
        ? '<div class="muted" style="margin-top:6px">Fields scrubbed before storage:</div><pre>' + esc(JSON.stringify(fields, null, 2)) + '</pre>'
        : '<div class="muted" style="margin-top:6px">No fields required scrubbing on this trace.</div>';
      html += card("Privacy posture",
        '<div>Scrub status: <span class="grade" style="color:var(--ok)">' + esc(scrubStatus) + '</span></div>' +
        fieldsHtml +
        '<div class="muted" style="margin-top:8px">Never captured:</div>' +
        '<pre>' + esc(JSON.stringify(pp.never_captured || [], null, 2)) + '</pre>' +
        '<div class="label">All records are scrubbed server-side before storage — only field names are kept, never the values.</div>');
      detailEl.innerHTML = html;
      // Wire actions via closures (no trace_id interpolated into inline onclick markup).
      document.getElementById("act-modelview").onclick = function () { ssModelView(id); };
      document.getElementById("act-repro").onclick = function () { ssRepro(id); };
      document.getElementById("act-drafts").onclick = function () { ssDrafts(id); };
      document.getElementById("act-github").onclick = function () { ssGithub(id); };
      document.getElementById("act-deliver").onclick = function () { ssDeliver(id); };
    } catch (e) { detailEl.innerHTML = '<p class="err">' + esc(e.message) + '</p>'; }
  }

  window.ssRepro = async function (id) {
    try { var r = await api("/session/" + id + "/playwright");
      show("Playwright reproduction", r.playwright_code || "", true);
    } catch (e) { show("Error", e.message); }
  };
  window.ssDrafts = async function (id) {
    try { var r = await api("/session/" + id + "/export-preview", { method: "POST" });
      show("Export preview (drafts — nothing sent)", JSON.stringify(r.drafts || {}, null, 2));
    } catch (e) { show("Error", e.message); }
  };
  window.ssGithub = async function (id) {
    try { var r = await api("/session/" + id + "/github/pr?dry_run=true",
        { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
          body: JSON.stringify({ approved_by: "dashboard-preview", idempotency_key: "preview-pr-" + id, dry_run: true }) });
      show("Dry-run GitHub PR (nothing opened)", JSON.stringify(r.would_open || r, null, 2));
    } catch (e) { show("Dry-run GitHub PR", e.message + "  (GitHub bridge not configured — that is expected)"); }
  };
  window.ssDeliver = async function (id) {
    try { var r = await api("/session/" + id + "/deliver?dry_run=true",
        { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
          body: JSON.stringify({ approved_by: "dashboard-preview", idempotency_key: "preview-" + id }) });
      show("Dry-run deliver (nothing sent)", JSON.stringify(r, null, 2));
    } catch (e) { show("Dry-run deliver", e.message + "  (direct-write may be disabled — that is expected)"); }
  };

  // The model's-eye view: compose the exact MCP read-only tool outputs an agent receives
  // for this trace, so an operator can see — and prove — precisely what reaches an LLM
  // before approving a connection. Every tool here maps 1:1 to a Copilot-safe MCP tool
  // (mcp_server.COPILOT_SAFE_OPERATIONS); nothing else is exposed to an agent.
  window.ssModelView = async function (id) {
    show("What an AI agent receives (MCP payload)", "Composing the model's-eye view…");
    var tools = [
      ["get_trace_summary", "/session/" + id + "/summary"],
      ["get_replayability_score", "/session/" + id + "/replayability"],
      ["get_privacy_posture", "/session/" + id + "/privacy-posture"],
      ["get_diagnostic_summary", "/session/" + id + "/diagnostic-summary"],
      ["generate_playwright_repro", "/session/" + id + "/playwright"]
    ];
    var results = await Promise.all(tools.map(function (t) {
      return api(t[1]).catch(function (e) { return { error: String(e.message) }; });
    }));
    var pp = results[2] || {};
    var never = pp.never_captured || [];
    var body = '<div class="label" style="font-style:normal;margin:0 0 10px">This is the ' +
      '<strong>entire</strong> payload any connected LLM or agent can receive for this trace, ' +
      'over the read-only MCP tools. Nothing outside this leaves your boundary.</div>';
    tools.forEach(function (t, i) {
      body += '<div style="margin-top:10px">' +
        '<span class="pill" style="color:var(--acc);border-color:var(--acc)">' + esc(t[0]) + '</span> ' +
        '<span class="muted" style="font-size:11px">' + esc(t[1].replace(id, "{trace_id}")) + '</span></div>';
      body += '<pre>' + esc(JSON.stringify(results[i], null, 2)) + '</pre>';
    });
    if (never.length) {
      body += '<div class="card" style="margin-top:12px;border-color:var(--ok)">' +
        '<h3 style="color:var(--ok)">Never reaches the model</h3>' +
        '<pre>' + esc(JSON.stringify(never, null, 2)) + '</pre></div>';
    }
    showHtml("What an AI agent receives (MCP payload)", body);
  };

  // Insert a popout whose body is already-built, esc()-sanitized HTML (vs show(), which
  // treats its body as plain text). Every dynamic value above passes through esc().
  function showHtml(title, bodyHtml) {
    var top = detailEl.querySelector("#popout");
    if (top) top.remove();
    var div = document.createElement("div");
    div.id = "popout"; div.className = "card";
    div.innerHTML = '<h3>' + esc(title) + '</h3>' + bodyHtml;
    detailEl.insertBefore(div, detailEl.firstChild);
  }

  function show(title, body, copyable) {
    var top = detailEl.querySelector("#popout");
    if (top) top.remove();
    var div = document.createElement("div");
    div.id = "popout"; div.className = "card";
    div.innerHTML = '<h3>' + esc(title) + '</h3>' +
      (copyable ? '<button id="cp" style="margin-bottom:8px">Copy</button>' : '') +
      '<pre>' + esc(body) + '</pre>';
    detailEl.insertBefore(div, detailEl.firstChild);
    if (copyable) document.getElementById("cp").onclick = function () {
      navigator.clipboard && navigator.clipboard.writeText(body); };
  }
})();
</script>
</body>
</html>
"""
