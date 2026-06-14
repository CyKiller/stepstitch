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
</style>
</head>
<body>
<header>
  <h1>StepStitch</h1>
  <span class="pill">read-only operator view</span>
  <span class="spacer"></span>
  <input id="token" type="password" placeholder="admin bearer token" size="28" autocomplete="off">
  <button id="save">Use token</button>
  <button id="reload" class="primary">Load traces</button>
</header>
<div class="wrap">
  <div class="list" id="list"><div class="row muted">Paste the admin token, then “Load traces”.</div></div>
  <div class="detail" id="detail"><p class="muted">Select a trace to inspect its sanitized evidence.</p></div>
</div>
<script>
(function () {
  var API = "/api/stepstitch/v1";
  var tokenEl = document.getElementById("token");
  var listEl = document.getElementById("list");
  var detailEl = document.getElementById("detail");
  var selected = null;

  tokenEl.value = sessionStorage.getItem("ss_token") || "";
  document.getElementById("save").onclick = function () {
    sessionStorage.setItem("ss_token", tokenEl.value.trim());
  };
  document.getElementById("reload").onclick = loadTraces;

  function hdr() { return { "Authorization": "Bearer " + (tokenEl.value.trim()) }; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;" }[c]; }); }

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
      var sm = s.summary || {};
      var rr = rep.replayability || {};
      var html = "";
      html += '<div class="actions">' +
        '<button onclick="ssRepro(\'' + id + '\')">View Playwright repro</button>' +
        '<button onclick="ssDrafts(\'' + id + '\')">Preview drafts</button>' +
        '<button onclick="ssDeliver(\'' + id + '\')">Dry-run deliver</button>' +
        '</div>';
      html += card("Summary",
        '<div>' + esc(sm.headline || "") + '</div>' +
        '<div class="muted">route ' + esc(sm.route) + ' · steps ' + esc(sm.step_count) +
        ' · ' + esc(sm.privacy_status || "") + '</div>');
      html += card("Replayability",
        '<span class="grade">' + esc(rr.grade) + '</span> · score ' + esc(rr.score) +
        (rr.warnings && rr.warnings.length ? '<pre>' + esc(JSON.stringify(rr.warnings, null, 2)) + '</pre>' : ''));
      html += card("Diagnostic — recommended next step",
        '<div>' + esc((diag.diagnostic || {}).recommended_next_step || "") + '</div>');
      html += card("Privacy posture",
        '<pre>' + esc(JSON.stringify(pp.never_captured || [], null, 2)) + '</pre>');
      detailEl.innerHTML = html;
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
  window.ssDeliver = async function (id) {
    try { var r = await api("/session/" + id + "/deliver?dry_run=true",
        { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, hdr()),
          body: JSON.stringify({ approved_by: "dashboard-preview", idempotency_key: "preview-" + id }) });
      show("Dry-run deliver (nothing sent)", JSON.stringify(r, null, 2));
    } catch (e) { show("Dry-run deliver", e.message + "  (direct-write may be disabled — that is expected)"); }
  };

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
