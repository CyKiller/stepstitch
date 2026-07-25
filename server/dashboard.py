"""Operator console for the StepStitch ingest host.

A single self-contained HTML page (no external assets, no build step) served at
``GET /dashboard`` under ``default-src 'none'`` with a per-request script nonce. It calls only
the **read-only / draft** operator endpoints with the admin bearer token the operator pastes in
(kept in sessionStorage, never persisted). It can preview drafts and run a **dry-run** deliver,
but exposes no destructive action.

Organised around the **failure shape**, not the trace: traces that broke the same way collapse
into one card on a pipeline board whose columns are derived from the verdict state machine in
``stepstitch_service.verification.verdict``. Forty reports of one bug is one decision.

All markup is built through ``el()``, which escapes by construction — there is no string
concatenation into ``innerHTML`` anywhere in this file, which is what the XSS-guard tests in
``server/tests/test_host.py`` exist to keep true.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StepStitch — operator console</title>
<style>
  /* Tokens mirror web/src/app/globals.css (dark) so the console reads as the same product as
     the site. Density and calm only — none of the marketing motion. */
  :root {
    --bg:#09090b; --surface:#101013; --surface-2:#18181b; --line:#27272a;
    --fg:#fafafa; --muted:#a1a1aa; --accent:#34d399; --accent-2:#2dd4bf;
    --accent-fg:#04241a; --ok:#34d399; --bad:#f87171; --warn:#fbbf24;
    --r-sm:6px; --r:10px; --r-lg:14px;
    --ease:cubic-bezier(0.32,0.72,0,1);
  }
  * { box-sizing:border-box; }
  /* `display:flex` on a component beats the [hidden] attribute's UA default of display:none,
     so hiding anything flex-based silently fails without this. */
  [hidden] { display:none !important; }
  html, body { height:100%; }
  body {
    margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    -webkit-font-smoothing:antialiased;
    display:flex; flex-direction:column;
  }
  code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  ::selection { background:color-mix(in oklab, var(--accent) 28%, transparent); }

  /* Keyboard users get a visible ring on everything focusable. This was missing entirely —
     an accessibility defect, not a polish item. :focus-visible so pointer users see nothing. */
  :focus-visible {
    outline:2px solid var(--accent);
    outline-offset:2px;
    border-radius:var(--r-sm);
  }

  /* Fixed grain layer: breaks the digital flatness without touching any scroller. A data: URI,
     which the page CSP already permits via `img-src 'self' data:` — no external asset. */
  .grain {
    position:fixed; inset:0; z-index:5; pointer-events:none;
    opacity:.035; mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }

  /* Skeletons mirror the shape of what is loading, so the layout does not jump when it lands. */
  @media (prefers-reduced-motion: no-preference) {
    .skel { animation:pulse 1.4s ease-in-out infinite; }
  }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }
  .skel {
    background:var(--surface-2); border:1px solid var(--line);
    border-radius:var(--r-lg); height:82px;
  }
  .skel.line { height:12px; border-radius:999px; border:none; }

  .search {
    width:210px; padding:5px 10px; font-size:13px; border-radius:999px;
    background:var(--bg); transition:width .25s var(--ease), border-color .25s var(--ease);
  }
  .search:focus { width:280px; border-color:color-mix(in oklab, var(--accent) 45%, transparent); }
  .search::placeholder { color:var(--muted); }

  /* Technical-detail switch. Off by default: the operator who needs plain language is the one
     who does not know to go looking for a toggle. */
  .switch { display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:var(--muted); cursor:pointer; white-space:nowrap; }
  .switch input { appearance:none; width:32px; height:18px; border-radius:999px; background:var(--surface-2); border:1px solid var(--line); position:relative; cursor:pointer; transition:background-color .25s var(--ease), border-color .25s var(--ease); }
  .switch input::after { content:""; position:absolute; top:2px; left:2px; width:12px; height:12px; border-radius:50%; background:var(--muted); transition:transform .25s var(--ease), background-color .25s var(--ease); }
  .switch input:checked { background:color-mix(in oklab, var(--accent) 22%, transparent); border-color:color-mix(in oklab, var(--accent) 50%, transparent); }
  .switch input:checked::after { transform:translateX(14px); background:var(--accent); }
  .switch:hover { color:var(--fg); }

  /* Teaching notes + setup checklist. */
  .teach {
    display:flex; gap:9px; align-items:flex-start;
    border-left:2px solid color-mix(in oklab, var(--accent) 55%, transparent);
    background:color-mix(in oklab, var(--accent) 6%, transparent);
    border-radius:0 var(--r) var(--r) 0; padding:9px 11px; font-size:12px;
    color:var(--muted); line-height:1.5;
  }
  .teach button { background:none; border:none; color:var(--muted); padding:0 2px; font-size:15px; line-height:1; cursor:pointer; }
  .teach button:hover { color:var(--fg); }

  .setup { max-width:620px; }
  .setup ol { list-style:none; margin:14px 0 0; padding:0; }
  .setup li { display:flex; gap:12px; padding:13px 0; border-top:1px solid var(--line); }
  .setup li:first-child { border-top:none; }
  .setup .tick {
    flex:0 0 auto; width:21px; height:21px; border-radius:50%; display:grid; place-items:center;
    border:1px solid var(--line); color:var(--muted); font-size:11px; margin-top:1px;
  }
  .setup li.done .tick { border-color:var(--ok); color:var(--ok); }
  .setup li.done .st { color:var(--muted); }
  .setup .st { font-size:14px; color:var(--fg); font-weight:550; }
  .setup .sd { font-size:12.5px; color:var(--muted); margin-top:3px; line-height:1.5; }
  .setup-mini { font-size:11.5px; color:var(--muted); }
  .setup-mini b { color:var(--accent); font-weight:600; }
  .boardbar {
    display:flex; align-items:center; gap:12px; flex-wrap:wrap;
    padding:9px 18px; border-bottom:1px solid var(--line);
    font-size:12px; color:var(--muted); background:var(--surface);
  }

  /* ---- chrome ---- */
  header.top {
    display:flex; align-items:center; gap:14px; padding:0 18px; height:54px;
    border-bottom:1px solid var(--line); background:var(--surface); flex:0 0 auto;
  }
  .brand { font-size:15px; font-weight:650; letter-spacing:-0.01em; }
  .brand .dot { color:var(--accent); }
  nav.main { display:flex; gap:2px; margin-left:10px; }
  nav.main button {
    background:none; border:none; color:var(--muted); font:inherit; font-size:13.5px;
    padding:7px 13px; border-radius:999px; cursor:pointer;
    transition:color .25s var(--ease), background-color .25s var(--ease);
  }
  nav.main button:hover { color:var(--fg); }
  nav.main button[aria-current="page"] { color:var(--accent); background:color-mix(in oklab, var(--accent) 12%, transparent); }
  .spacer { flex:1; }

  /* Ambient privacy: the product's central claim, always on screen. */
  .privacy {
    display:flex; align-items:center; gap:8px; flex-wrap:wrap;
    padding:7px 18px; font-size:12px; color:var(--muted);
    background:color-mix(in oklab, var(--accent) 5%, var(--bg));
    border-bottom:1px solid var(--line); flex:0 0 auto;
  }
  .privacy strong { color:var(--fg); font-weight:600; }
  .privacy .never { text-decoration:line-through; text-decoration-color:color-mix(in oklab, var(--bad) 60%, transparent); }

  .flow {
    display:flex; flex-wrap:wrap; align-items:center; gap:6px;
    padding:7px 18px; font-size:11.5px; color:var(--muted);
    border-bottom:1px solid var(--line); background:var(--surface); flex:0 0 auto;
  }
  .flow b { color:var(--fg); font-weight:600; }
  .flow .arr { color:var(--accent); }

  main.view { flex:1 1 auto; overflow:auto; min-height:0; }
  footer.bottom {
    padding:9px 18px; font-size:11px; color:var(--muted);
    border-top:1px solid var(--line); background:var(--surface); flex:0 0 auto;
  }
  .status { font-size:11.5px; color:var(--muted); }
  .status b { color:var(--fg); font-weight:600; }

  /* ---- controls ---- */
  button, input, select, textarea {
    font:inherit; color:var(--fg); background:var(--surface-2);
    border:1px solid var(--line); border-radius:var(--r-sm); padding:6px 10px;
  }
  button { cursor:pointer; transition:border-color .25s var(--ease), transform .25s var(--ease); }
  button:hover { border-color:color-mix(in oklab, var(--fg) 30%, transparent); }
  button:active { transform:scale(0.98); }
  button.primary {
    background:var(--accent); border-color:var(--accent); color:var(--accent-fg); font-weight:600;
  }
  button.ghost { background:none; }
  button.link { background:none; border:none; color:var(--accent); padding:0; text-decoration:underline; }
  a { color:var(--accent); }

  .pill {
    display:inline-block; padding:1px 8px; border-radius:999px; font-size:11.5px;
    border:1px solid var(--line); color:var(--muted); white-space:nowrap;
  }
  .pill.ok { color:var(--ok); border-color:color-mix(in oklab, var(--ok) 40%, transparent); }
  .pill.bad { color:var(--bad); border-color:color-mix(in oklab, var(--bad) 40%, transparent); }
  .pill.warn { color:var(--warn); border-color:color-mix(in oklab, var(--warn) 40%, transparent); }
  .pill.acc { color:var(--accent); border-color:color-mix(in oklab, var(--accent) 40%, transparent); }
  .muted { color:var(--muted); }
  .err { color:var(--bad); }

  /* ---- board ---- */
  /* Columns share the width so the whole pipeline — including the Fixed win state — is on
     screen at once. They only start scrolling below ~1300px. */
  .board { display:flex; gap:14px; padding:18px; align-items:flex-start; min-height:100%; }
  /* Plain column names ("Waiting for a test run") are far longer than the technical ones
     ("Untriaged"), so the header wraps and the columns need more floor width. */
  .col { flex:1 1 0; min-width:236px; max-width:360px; display:flex; flex-direction:column; gap:10px; }
  .col-head { display:flex; align-items:baseline; gap:6px; padding:0 2px; flex-wrap:wrap; }
  .col-head h2 {
    margin:0; font-size:12px; font-weight:650; letter-spacing:.06em; text-transform:uppercase;
    line-height:1.35; min-width:0;
  }
  .col-head .n {
    font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums;
    flex:0 0 auto; margin-left:auto;
  }
  .col-head .why { flex:1 1 100%; font-size:11.5px; color:var(--muted); margin-top:1px; line-height:1.4; }
  .col.s-known h2 { color:var(--accent); }
  .col.s-fixed h2 { color:var(--ok); }
  .col.s-repro_invalid h2, .col.s-fix_failed h2 { color:var(--warn); }

  /* Elevation carries the accent hue rather than black, so cards sit in the palette instead of
     on top of it. Radius is concentric with the column gutter, not uniform everywhere. */
  .card {
    background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg);
    padding:13px 14px; text-align:left; width:100%; display:block;
    box-shadow:0 1px 2px color-mix(in oklab, var(--bg) 80%, black),
               0 8px 24px -18px color-mix(in oklab, var(--accent) 40%, transparent);
    transition:border-color .25s var(--ease), transform .25s var(--ease),
               box-shadow .25s var(--ease);
  }
  button.card:hover {
    border-color:color-mix(in oklab, var(--accent) 45%, transparent);
    transform:translateY(-1px);
    box-shadow:0 2px 4px color-mix(in oklab, var(--bg) 80%, black),
               0 14px 34px -18px color-mix(in oklab, var(--accent) 55%, transparent);
  }
  .card-top { display:flex; align-items:center; gap:10px; }
  .card .headline { font-size:13px; color:var(--fg); font-weight:550; line-height:1.4; text-wrap:pretty; }
  .card .route { font-size:12.5px; color:var(--fg); word-break:break-all; font-weight:550; }
  .card .sub { margin-top:6px; font-size:11.5px; color:var(--muted); display:flex; flex-wrap:wrap; gap:4px 8px; }
  .card .known { margin-top:9px; font-size:11.5px; color:var(--accent); }
  .count { font-variant-numeric:tabular-nums; font-weight:650; }

  .empty {
    border:1px dashed var(--line); border-radius:var(--r-lg); padding:16px;
    font-size:12.5px; color:var(--muted);
  }
  .empty p { margin:0 0 10px; }

  /* ---- detail ---- */
  .detail { padding:22px 26px 40px; max-width:1180px; }
  .crumb { background:none; border:none; color:var(--muted); padding:0; font-size:12.5px; cursor:pointer; }
  .crumb:hover { color:var(--fg); }
  .verdict { display:flex; gap:20px; align-items:flex-start; flex-wrap:wrap; margin-top:14px; }
  .verdict .grade { font-size:44px; font-weight:680; line-height:1; letter-spacing:-0.03em; }
  .verdict h1 { margin:0; font-size:23px; font-weight:640; letter-spacing:-0.015em; word-break:break-all; }
  .verdict .facts { display:flex; flex-wrap:wrap; gap:6px 10px; margin-top:9px; font-size:12.5px; color:var(--muted); }
  .next {
    margin-top:16px; padding:12px 14px; border-radius:var(--r);
    border:1px solid color-mix(in oklab, var(--accent) 32%, transparent);
    background:color-mix(in oklab, var(--accent) 7%, transparent); font-size:13.5px;
  }
  .next .lab { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }

  .tabs { display:flex; gap:2px; margin:22px 0 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .tabs button {
    background:none; border:none; border-bottom:2px solid transparent; border-radius:0;
    color:var(--muted); font-size:13px; padding:9px 13px; cursor:pointer;
    transition:color .25s var(--ease), border-color .25s var(--ease);
  }
  .tabs button:hover { color:var(--fg); }
  .tabs button[aria-selected="true"] { color:var(--fg); border-bottom-color:var(--accent); }
  .panel { padding-top:18px; }

  .box { background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg); padding:15px 16px; margin-bottom:12px; }
  .box h3 { margin:0 0 10px; font-size:11.5px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
  .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
  pre {
    white-space:pre-wrap; word-break:break-word; margin:0;
    background:var(--surface-2); border:1px solid var(--line); border-radius:var(--r);
    padding:12px; font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
    max-height:420px; overflow:auto; color:color-mix(in oklab, var(--fg) 92%, transparent);
  }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th { text-align:left; color:var(--muted); font-weight:600; padding:4px 12px 6px 0; }
  td { padding:4px 12px 4px 0; vertical-align:top; }
  td.k { color:var(--muted); white-space:nowrap; }
  ul.tight { margin:6px 0 0; padding-left:18px; font-size:12.5px; color:var(--muted); }
  ul.tight li { margin-bottom:3px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .chip { border:1px solid var(--line); background:var(--surface-2); border-radius:var(--r-sm); padding:2px 7px; font-size:11.5px; color:var(--muted); }
  .chip.strike { text-decoration:line-through; text-decoration-color:color-mix(in oklab, var(--bad) 55%, transparent); }
  .row-actions { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
  .glyph { flex:0 0 auto; }
  .note { font-size:11.5px; color:var(--muted); margin-top:9px; }
  .gate { max-width:520px; margin:70px auto; }
  .gate h1 { font-size:20px; margin:0 0 8px; font-weight:640; }
  .gate p { color:var(--muted); font-size:13.5px; margin:0 0 16px; }
  .gate .field { display:flex; gap:8px; }
  .gate input { flex:1; }
</style>
</head>
<body>
<header class="top">
  <span class="brand">StepStitch<span class="dot">.</span></span>
  <span class="pill">operator console</span>
  <nav class="main" id="nav" aria-label="Sections"></nav>
  <span class="spacer"></span>
  <input id="search" type="search" class="search" placeholder="Search failures…"
         aria-label="Search failures" autocomplete="off">
  <label class="switch" for="techtoggle">
    <input type="checkbox" id="techtoggle">
    <span>Technical detail</span>
  </label>
  <span class="status" id="statusbar" aria-live="polite"></span>
  <button id="tokenbtn" class="ghost">Disconnect</button>
</header>

<div class="privacy" id="privacy">
  <strong>Structural evidence only.</strong>
  <span>StepStitch never captures, ever:</span>
  <span class="never">screens</span>
  <span class="never">input values</span>
  <span class="never">page text</span>
  <span class="never">raw URLs</span>
  <span class="never">request bodies</span>
  <span class="never">cookies &amp; headers</span>
</div>

<!-- The pipeline, stated twice. Both registers ship in the document — the technical one names
     the real artefacts for an engineer, the plain one is what everyone else can follow — and
     the technical-detail toggle decides which is shown. -->
<div class="flow" id="flow-tech" hidden>
  <b>Customer bug</b><span class="arr">&rarr;</span>
  <b>privacy scrub</b><span class="arr">&rarr;</span>
  <b>replayability score</b><span class="arr">&rarr;</span>
  <b>Playwright repro</b><span class="arr">&rarr;</span>
  <b>draft ticket/PR</b><span class="arr">&rarr;</span>
  <b>verified fix</b>
</div>
<div class="flow" id="flow-plain">
  <b>Someone reports a bug</b><span class="arr">&rarr;</span>
  <b>personal details stripped</b><span class="arr">&rarr;</span>
  <b>we check it can be reproduced</b><span class="arr">&rarr;</span>
  <b>a test is written for it</b><span class="arr">&rarr;</span>
  <b>a ticket is drafted</b><span class="arr">&rarr;</span>
  <b>the fix is proven</b>
</div>

<div class="grain" aria-hidden="true"></div>
<main class="view" id="view" aria-live="polite" aria-busy="false"></main>

<footer class="bottom">Operator console &middot; every read and config change is audited &middot; records are scrubbed server-side before storage &middot; drafts are previews, nothing is sent &middot; evidence is never edited or deleted here.</footer>

<script nonce="__CSP_NONCE__">
(function () {
  "use strict";

  var API = "/api/stepstitch/v1";
  var viewEl = document.getElementById("view");
  var navEl = document.getElementById("nav");
  var token = sessionStorage.getItem("ss_token") || "";

  // ---- operator preferences -------------------------------------------------------------
  // Persisted in localStorage (preferences, not credentials — the token stays in
  // sessionStorage). `tech` defaults to FALSE: the operator who most needs plain language is
  // exactly the one who would not think to go looking for a toggle.
  function pref(key, fallback) {
    try { var v = localStorage.getItem("ss_" + key); return v === null ? fallback : v === "1"; }
    catch (e) { return fallback; }
  }
  function setPref(key, on) {
    try { localStorage.setItem("ss_" + key, on ? "1" : "0"); } catch (e) { /* private mode */ }
  }
  var tech = pref("tech", false);
  var query = "";
  var lastStatus = null;

  // ---- DOM construction -----------------------------------------------------------------
  // Everything is built through el(). Text is set via textContent and attributes via
  // setAttribute, so values escape by construction and no markup string is ever concatenated.
  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "text") node.textContent = String(v);
        else if (k === "class") node.className = v;
        else if (k.slice(0, 2) === "on") node[k] = v;
        else node.setAttribute(k, String(v));
      });
    }
    (kids || []).forEach(function (kid) {
      if (kid === null || kid === undefined || kid === false) return;
      node.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    });
    return node;
  }
  function svg(tag, attrs, kids) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { node.setAttribute(k, String(attrs[k])); });
    (kids || []).forEach(function (kid) { node.appendChild(kid); });
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function esc(s) { return String(s === null || s === undefined ? "" : s); }
  function escAttr(s) { return esc(s); }
  // Only http(s) links are ever rendered; anything else (javascript:, data:) becomes null.
  function safeUrl(u) {
    if (!u) return null;
    var s = String(u).trim();
    return (/^https?:\/\//i).test(s) ? s : null;
  }
  // The rendered href is the value safeUrl() returned, never the caller's raw input — so the
  // scheme gate cannot be bypassed by a later edit that drops the early return.
  function extLink(rawUrl, label) {
    var runUrl = safeUrl(rawUrl);
    if (!runUrl) return null;
    return el("a", { href: escAttr(runUrl), target: "_blank", rel: "noopener noreferrer",
                     text: label || "CI run" });
  }

  // ---- fingerprint glyph ----------------------------------------------------------------
  // Six fingerprint fields become a 3x2 mark. Same shape, same glyph, always — so "these two
  // bugs are the same failure" is an eyeball operation across the whole board. A null field
  // renders hollow, which makes a thin fingerprint visibly thin.
  var FP_KEYS = ["route", "diagnostic_type", "failing_status", "exception_type",
                 "diagnostic_endpoint", "terminal_selector"];
  function hash32(str) {           // FNV-1a, deterministic and dependency-free
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
    }
    return h >>> 0;
  }
  function glyph(fp, size) {
    var s = size || 30, cell = s / 3, pad = cell * 0.18, r = cell / 2 - pad;
    var root = svg("svg", { width: s, height: s * 2 / 3, viewBox: "0 0 " + s + " " + (s * 2 / 3),
                            class: "glyph", "aria-hidden": "true" });
    FP_KEYS.forEach(function (key, i) {
      var cx = (i % 3) * cell + cell / 2, cy = Math.floor(i / 3) * cell + cell / 2;
      var raw = (fp || {})[key];
      if (raw === null || raw === undefined || raw === "") {
        root.appendChild(svg("circle", { cx: cx, cy: cy, r: r * 0.55,
          fill: "none", stroke: "var(--line)", "stroke-width": 1 }));
        return;
      }
      var h = hash32(key + ":" + String(raw));
      var shade = ["var(--accent)", "var(--accent-2)", "color-mix(in oklab, var(--accent) 55%, var(--fg))"][h % 3];
      var form = (h >> 3) % 4;
      if (form === 0) {
        root.appendChild(svg("circle", { cx: cx, cy: cy, r: r, fill: shade }));
      } else if (form === 1) {
        root.appendChild(svg("rect", { x: cx - r, y: cy - r, width: r * 2, height: r * 2,
          rx: r * 0.32, fill: shade }));
      } else if (form === 2) {
        root.appendChild(svg("polygon", {
          points: [cx, cy - r, cx + r, cy + r, cx - r, cy + r].join(" "), fill: shade }));
      } else {
        root.appendChild(svg("rect", { x: cx - r, y: cy - r * 0.42, width: r * 2,
          height: r * 0.84, rx: r * 0.42, fill: shade }));
      }
    });
    return root;
  }

  // ---- transport ------------------------------------------------------------------------
  function hdr() { return { "Authorization": "Bearer " + token }; }
  async function req(base, path, opts) {
    var o = opts || {};
    var res = await fetch(base + path, {
      method: o.method || "GET",
      headers: Object.assign({}, hdr(), o.headers || {}),
      body: o.body
    });
    if (!res.ok) throw new Error("HTTP " + res.status + " on " + path);
    return res.json();
  }
  function api(path, opts) { return req(API, path, opts); }
  function adminApi(path, opts) { return req("/admin", path, opts); }
  function jsonPost(body) {
    return { method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(body) };
  }

  // ---- shared pieces --------------------------------------------------------------------
  function box(title, kids) {
    return el("div", { class: "box" }, [title ? el("h3", { text: title }) : null].concat(kids || []));
  }
  function kvTable(obj) {
    var body = el("tbody", {}, Object.keys(obj || {}).map(function (k) {
      var v = obj[k];
      return el("tr", {}, [
        el("td", { class: "k", text: k }),
        el("td", { text: v === null || v === undefined ? "—" : String(v) })
      ]);
    }));
    return el("table", {}, [body]);
  }
  function copyBtn(getText, label) {
    var b = el("button", { class: "ghost", text: label || "Copy" });
    b.onclick = function () {
      if (navigator.clipboard) navigator.clipboard.writeText(getText());
      b.textContent = "Copied";
      setTimeout(function () { b.textContent = label || "Copy"; }, 1500);
    };
    return b;
  }
  function emptyState(message, actionLabel, onAction) {
    var kids = [el("p", { text: message })];
    if (actionLabel) kids.push(el("button", { class: "primary", text: actionLabel, onclick: onAction }));
    return el("div", { class: "empty" }, kids);
  }
  // Skeletons shaped like what is arriving, so the layout does not jump when it lands.
  function skeleton(kind) {
    if (kind === "board") {
      return el("div", { class: "board" }, [0, 1, 2, 3, 4].map(function (i) {
        return el("div", { class: "col" }, [
          el("div", { class: "skel line", style: "width:60%" }),
          el("div", { class: "skel" }),
          i % 2 ? el("div", { class: "skel", style: "height:64px" }) : null
        ]);
      }));
    }
    return el("div", { class: "detail" }, [
      el("div", { class: "skel line", style: "width:34%;margin-bottom:14px" }),
      el("div", { class: "skel", style: "height:56px;margin-bottom:16px" }),
      el("div", { class: "grid2" }, [
        el("div", { class: "skel", style: "height:180px" }),
        el("div", { class: "skel", style: "height:180px" })
      ])
    ]);
  }
  function spinner(label) { return el("p", { class: "muted", text: label || "Loading…" }); }

  // A one-sentence explainer shown the first time a concept actually matters, then dismissed
  // for good. Teaching in place beats a tour nobody finishes.
  function teach(id, message) {
    if (pref("seen_" + id, false)) return null;
    var node = el("div", { class: "teach" }, [
      el("span", { text: message }),
      el("button", { text: "×", "aria-label": "Dismiss", onclick: function () {
        setPref("seen_" + id, true);
        if (node.parentNode) node.parentNode.removeChild(node);
      } })
    ]);
    return node;
  }

  // ---- plain language -------------------------------------------------------------------
  // The sentence itself comes from the service (humanize.py) and travels on the shape, so the
  // console never invents wording. These only decide WHICH of the two registers to show.
  function headlineFor(shape) {
    if (tech) return (shape.fingerprint || {}).route || "(no route)";
    return shape.plain_summary || (shape.fingerprint || {}).route || "Unknown failure";
  }
  function stageNameFor(shape, stage) {
    return tech ? stage.label : (shape.stage_label || stage.label);
  }
  var CONFIDENCE = [
    [0.85, "Reliably reproducible"], [0.70, "Likely reproducible"],
    [0.55, "Might be reproducible"], [0.40, "Hard to reproduce"]
  ];
  function confidenceBand(score) {
    if (score === null || score === undefined) return "Not yet assessed";
    for (var i = 0; i < CONFIDENCE.length; i++) {
      if (score >= CONFIDENCE[i][0]) return CONFIDENCE[i][1];
    }
    return "Very hard to reproduce";
  }
  // Replayability warning codes, in the reader's terms. Mirrors humanize._WARNING_TEXT; an
  // unknown code falls back to the server's own detail string rather than disappearing.
  var WARNINGS = {
    templated_route_needs_fixture:
      "the page address contains an ID, so the test needs a real account to run against",
    unstable_selector:
      "some buttons are identified by their position or styling, which changes when the page " +
      "is redesigned — the test may break for the wrong reason",
    missing_selector: "we could not tell which control was used, so the test has to guess",
    no_terminal_action:
      "the report does not end on a clear action, so there is nothing obvious to assert on",
    long_trace: "the report is long, so the test covers a lot of ground and may be slow or brittle",
    empty_trace: "nothing was captured for this report, so there is nothing to rebuild"
  };
  function fail(e) { return el("p", { class: "err", text: e && e.message ? e.message : String(e) }); }

  // The ambient privacy strip is static markup in <head>'s sibling chrome, not built here:
  // it never varies, so it should survive a JS failure and be readable to anything that can
  // read HTML.

  // ---- routing --------------------------------------------------------------------------
  var ROUTES = [
    { id: "board", label: "Board", render: renderBoard },
    { id: "agents", label: "Agents", render: renderAgents },
    { id: "governance", label: "Governance", render: renderGovernance }
  ];
  var current = "board";

  function renderNav() {
    clear(navEl);
    ROUTES.forEach(function (r) {
      var b = el("button", { text: r.label, onclick: function () { go(r.id); } });
      if (r.id === current) b.setAttribute("aria-current", "page");
      navEl.appendChild(b);
    });
  }
  var currentShapeId = null;   // set while a shape detail is open, so re-renders return to it

  function go(id) {
    current = id;
    currentShapeId = null;
    renderNav();
    syncChrome();
    if (!token) return renderGate();
    loadStatus();   // counts move as you work — refresh them on every navigation
    var route = ROUTES.filter(function (r) { return r.id === id; })[0] || ROUTES[0];
    route.render();
  }
  function mount(node) {
    clear(viewEl);
    viewEl.appendChild(node);
    viewEl.scrollTop = 0;
    viewEl.setAttribute("aria-busy", "false");
    syncChrome();
  }
  function mountLoading(node) {
    clear(viewEl);
    viewEl.appendChild(node);
    viewEl.setAttribute("aria-busy", "true");
  }

  // ---- token gate -----------------------------------------------------------------------
  function renderGate() {
    var input = el("input", { type: "password", placeholder: "admin bearer token",
                              autocomplete: "off", "aria-label": "admin bearer token" });
    function submit() {
      var v = input.value.trim();
      if (!v) return;
      token = v;
      sessionStorage.setItem("ss_token", v);
      loadStatus();
      go(current);
    }
    input.onkeydown = function (e) { if (e.key === "Enter") submit(); };
    mount(el("div", { class: "gate" }, [
      el("h1", { text: "Connect to your host" }),
      el("p", { text: "Paste the admin bearer token this host was started with " +
                      "(STEPSTITCH_ADMIN_TOKEN). It is kept in sessionStorage for this tab only " +
                      "and is never sent anywhere but your own host." }),
      el("div", { class: "field" }, [input, el("button", { class: "primary", text: "Connect",
                                                           onclick: submit })]),
      el("p", { class: "note", text: "No agent ever receives this credential — agents get their " +
                                     "own scoped, revocable tokens from the Agents tab." })
    ]));
    input.focus();
  }
  document.getElementById("tokenbtn").onclick = function () {
    token = "";
    sessionStorage.removeItem("ss_token");
    document.getElementById("statusbar").textContent = "";
    renderGate();
  };

  // Technical detail: re-renders in place, so the operator sees the same screen re-worded
  // rather than being bounced back to the board.
  var techEl = document.getElementById("techtoggle");
  techEl.checked = tech;
  techEl.onchange = function () {
    tech = techEl.checked;
    setPref("tech", tech);
    syncChrome();
    if (currentShapeId) openShape(currentShapeId); else go(current);
  };

  var searchEl = document.getElementById("search");
  var searchTimer = null;
  searchEl.oninput = function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      query = searchEl.value.trim().toLowerCase();
      if (current === "board" && !currentShapeId) renderBoard();
    }, 160);
  };

  // Search only means anything on the board; hide it elsewhere rather than leave it inert.
  // The flow banner swaps register with the toggle rather than being rewritten.
  function syncChrome() {
    searchEl.style.display = (current === "board" && !currentShapeId) ? "" : "none";
    document.getElementById("flow-tech").hidden = !tech;
    document.getElementById("flow-plain").hidden = tech;
  }

  async function loadStatus() {
    var bar = document.getElementById("statusbar");
    try {
      var s = await adminApi("/status");
      clear(bar);
      [["profile", s.profile], ["retention", s.retention_days + "d"],
       ["traces", s.traces], ["agents", s.agents_active + "/" + s.agents_total],
       ["audit", s.audit_events]].forEach(function (pair, i) {
        if (i) bar.appendChild(document.createTextNode(" · "));
        bar.appendChild(document.createTextNode(pair[0] + " "));
        bar.appendChild(el("b", { text: String(pair[1]) }));
      });
    } catch (e) { clear(bar); }
  }

  // "today" / "yesterday" / "3 days ago" — dates mean nothing at a glance.
  function relativeDay(iso) {
    if (!iso) return "";
    var then = new Date(String(iso).replace(" ", "T"));
    if (isNaN(then.getTime())) return "";
    var days = Math.floor((Date.now() - then.getTime()) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 30) return days + " days ago";
    return then.toISOString().slice(0, 10);
  }

  // ---- setup ------------------------------------------------------------------------------
  // Four steps, each DETECTED rather than ticked by hand, so the checklist can never claim
  // something that is not true.
  function setupSteps(status) {
    var s = status || {};
    return [
      { done: !!token, title: "Connect to your host",
        detail: "You are connected. This token stays in this browser tab and is never shared " +
                "with an agent." },
      { done: (s.traces || 0) > 0, title: "Receive your first report",
        detail: "Install @stepstitch/tracker in your app, or send a sample below to see the " +
                "console with real evidence in it." },
      { done: (s.verifications || 0) > 0, title: "Let CI report results",
        detail: "Your CI runs the generated test before and after a fix and posts the outcome " +
                "back. Until it does, nothing can be proven fixed and there is no memory to " +
                "match new bugs against. Open any failure and use the Verify tab for the snippet." },
      { done: (s.agents_total || 0) > 0, title: "Connect an AI agent (optional)",
        detail: "Give an assistant a scoped, revocable token so it can read safe evidence — " +
                "never raw data. Set this up in Agents." }
    ];
  }
  function setupComplete(status) {
    return setupSteps(status).every(function (st) { return st.done; });
  }

  async function sendSampleReport() {
    // A one-click first trace. Structural and synthetic — the same shape the SDK would send,
    // so the board fills with something real rather than telling an operator to open a shell.
    return api("/session", jsonPost({
      app_id: "console-sample",
      metadata: { sdk_version: "console-sample" },
      footsteps: [
        { timestamp: new Date().toISOString(), type: "navigation", route: "/orders/:id",
          label: "[masked]" },
        { timestamp: new Date().toISOString(), type: "click", route: "/orders/:id",
          target: "[data-testid=place-order]", label: "[masked]" },
        { timestamp: new Date().toISOString(), type: "api_error", route: "/orders/:id",
          label: "[masked]",
          metadata: { status: 500, method: "POST", endpoint: "/api/orders/:id/submit" } }
      ]
    }));
  }

  function setupView(status) {
    var steps = setupSteps(status);
    var sampleBtn = el("button", { class: "primary", text: "Send a sample report" });
    var out = el("div", {});
    sampleBtn.onclick = async function () {
      sampleBtn.disabled = true;
      sampleBtn.textContent = "Sending…";
      try { await sendSampleReport(); renderBoard(); }
      catch (e) {
        clear(out); out.appendChild(fail(e));
        sampleBtn.disabled = false; sampleBtn.textContent = "Send a sample report";
      }
    };

    return el("div", { class: "detail setup" }, [
      el("h1", { style: "font-size:21px;margin:0 0 6px;font-weight:640",
                 text: "Let's get this working" }),
      el("p", { class: "muted", style: "margin:0;font-size:13.5px",
                text: "StepStitch turns a bug report into evidence a developer can act on — " +
                      "without ever capturing anyone's screen, typing, or personal details. " +
                      "Four steps, and you only need the first two to see it work." }),
      el("ol", {}, steps.map(function (st) {
        return el("li", { class: st.done ? "done" : "" }, [
          el("span", { class: "tick", text: st.done ? "✓" : "", "aria-hidden": "true" }),
          el("div", {}, [
            el("div", { class: "st", text: st.title }),
            el("div", { class: "sd", text: st.detail })
          ])
        ]);
      })),
      el("div", { class: "row-actions", style: "margin-top:18px" }, [
        sampleBtn,
        el("button", { class: "ghost", text: "Check again", onclick: renderBoard })
      ]),
      out,
      el("div", { class: "note", text: "Everything here is read-only. Nothing in this console " +
                                       "can delete evidence or send anything to another system." })
    ]);
  }

  // Once past the empty board, setup shrinks to a single line rather than nagging.
  function setupMini(status) {
    var steps = setupSteps(status);
    var left = steps.filter(function (st) { return !st.done; });
    var next = left[0];
    return el("div", { class: "boardbar" }, [
      el("span", { class: "setup-mini" }, [
        el("b", { text: (steps.length - left.length) + "/" + steps.length + " set up" }),
        document.createTextNode(" · next: " + next.title)
      ]),
      el("button", { class: "link", text: "Show me", onclick: function () {
        mount(setupView(status));
      } })
    ]);
  }

  // ---- board ----------------------------------------------------------------------------
  // An empty column is information too: "nothing invalid" is a different sentence from
  // "nothing fixed yet", so each says its own.
  // `label` is the technical name; `plain` is what a support lead or QA engineer reads. The
  // stage IDs are the contract — only the wording changes with the toggle.
  var STAGES = [
    { id: "untriaged", label: "Untriaged", plain: "Waiting for a test run",
      why: "no CI result reported yet",
      teach: "Nobody has run the generated test against these yet, so we cannot say whether " +
             "they are reproducible.",
      blank: "Nothing waiting — everything here has been tested." },
    { id: "known_shape", label: "Known shape", plain: "Seen before",
      why: "you have fixed this before",
      teach: "These broke the same way as something you already fixed. Start from that fix " +
             "rather than from scratch.",
      blank: "No repeats. Everything here is new to you." },
    { id: "repro_invalid", label: "Repro invalid", plain: "Test needs fixing",
      why: "the test passed before the fix",
      teach: "The test we generated passed even before the fix — so it is not catching this " +
             "bug and needs adjusting.",
      blank: "Every test caught the bug it was written for." },
    { id: "reproduced", label: "Reproduced", plain: "Confirmed broken",
      why: "reproduced, awaiting a fix",
      teach: "The test fails exactly as reported, so the bug is real and reproducible. It is " +
             "waiting on a fix.",
      blank: "Nothing confirmed-broken is waiting on a fix." },
    { id: "fix_failed", label: "Fix failed", plain: "Still broken",
      why: "still failing after a fix",
      teach: "Someone shipped a fix, but the test still fails. The bug is not gone.",
      blank: "No fix has regressed." },
    { id: "fixed", label: "Fixed", plain: "Fixed and proven",
      why: "failed before the fix, passed after",
      teach: "The test failed before the fix and passed after it. That is the only thing we " +
             "accept as proof — and it is what fills the memory this console matches against.",
      blank: "Nothing proven fixed yet — connect CI so results get reported." }
  ];
  var ALWAYS_SHOWN = { untriaged: 1, known_shape: 1, reproduced: 1, fixed: 1 };

  function shapeCard(shape) {
    var fp = shape.fingerprint || {};
    var kids = [
      el("div", { class: "card-top" }, [
        glyph(fp, 30),
        el("div", { class: tech ? "route mono" : "headline", text: headlineFor(shape) })
      ])
    ];

    // Plain view answers "how many people, and can we reproduce it?". Technical view keeps the
    // status codes and diagnostic types an engineer triages on.
    var facts = [];
    if (tech) {
      if (fp.failing_status) facts.push("HTTP " + fp.failing_status);
      if (fp.exception_type) facts.push(fp.exception_type);
      if (fp.diagnostic_type) facts.push(fp.diagnostic_type);
    }
    facts.push(shape.occurrences === 1 ? "1 person affected"
                                       : shape.occurrences + " people affected");
    // Recency is what tells a non-engineer whether this is live or historical. The board has
    // no replayability score to show here — that needs the trace body, so it lives on the
    // detail view where we actually fetch one.
    var seen = relativeDay(shape.last_seen);
    if (seen) facts.push("last seen " + seen);
    kids.push(el("div", { class: "sub" }, facts.map(function (f) {
      return el("span", { text: f });
    })));

    if (shape.prior_fixes && shape.prior_fixes.length) {
      var top = shape.prior_fixes[0];
      kids.push(el("div", { class: "known", text: tech
        ? "Seen before · " + (top.fix_ref || top.trace_id) + " · " +
          Math.round((top.similarity || 0) * 100) + "% match"
        : "You fixed this before — see " + (top.fix_ref || top.trace_id) }));
    }
    return el("button", { class: "card", onclick: function () { openShape(shape.shape_id); } }, kids);
  }

  // Free-text filter across everything a person might search by, in either register.
  function matchesQuery(shape) {
    if (!query) return true;
    var fp = shape.fingerprint || {};
    return [shape.plain_summary, shape.stage_label, fp.route, fp.diagnostic_type,
            fp.exception_type, fp.failing_status, fp.terminal_selector]
      .filter(Boolean).join(" ").toLowerCase().indexOf(query) >= 0;
  }

  async function renderBoard() {
    mountLoading(skeleton("board"));
    var data, status;
    try {
      data = await api("/shapes");
      status = await adminApi("/status").catch(function () { return lastStatus || {}; });
      lastStatus = status;
    } catch (e) { return mount(fail(e)); }

    var shapes = data.shapes || [];

    // Nothing to show yet is not an error — it means setup is unfinished. Say what to do next.
    if (!shapes.length) return mount(setupView(status));

    var visible = shapes.filter(matchesQuery);
    var wrap = el("div", {});

    if (query) {
      wrap.appendChild(el("div", { class: "boardbar" }, [
        el("span", { text: "Showing " + visible.length + " of " + shapes.length +
                           (shapes.length === 1 ? " failure" : " failures") }),
        el("button", { class: "link", text: "Clear", onclick: function () {
          searchEl.value = ""; query = ""; renderBoard();
        } })
      ]));
    } else if (status && !setupComplete(status)) {
      wrap.appendChild(setupMini(status));
    }

    var board = el("div", { class: "board" });
    STAGES.forEach(function (stage) {
      var items = visible.filter(function (s) { return s.stage === stage.id; });
      if (!items.length && !ALWAYS_SHOWN[stage.id]) return;   // noise columns collapse
      var col = el("div", { class: "col s-" + stage.id }, [
        el("div", { class: "col-head" }, [
          el("h2", { text: tech ? stage.label : stage.plain }),
          el("span", { class: "n", text: String(items.length) }),
          el("span", { class: "why", text: stage.why })
        ])
      ]);
      // A column explains itself the first time it actually has something in it — the moment
      // the concept becomes relevant, rather than in a tour up front.
      if (items.length) {
        var note = teach("col_" + stage.id, stage.teach);
        if (note) col.appendChild(note);
      }
      if (!items.length) {
        col.appendChild(el("div", { class: "empty" }, [
          el("p", { text: query ? "No matches here." : stage.blank })
        ]));
      } else {
        items.forEach(function (s) { col.appendChild(shapeCard(s)); });
      }
      board.appendChild(col);
    });
    wrap.appendChild(board);
    mount(wrap);
  }

  // ---- shape detail ---------------------------------------------------------------------
  // Sections render IN PLACE. Nothing is ever injected above what the operator is reading.
  var GRADE_TONE = { A: "ok", B: "ok", C: "warn", D: "warn", E: "bad", F: "bad" };

  async function openShape(shapeId) {
    currentShapeId = shapeId;
    mountLoading(skeleton("detail"));
    var shape, trace;
    try {
      shape = (await api("/shapes/" + encodeURIComponent(shapeId))).shape;
      trace = await loadTrace(shape.representative_trace_id);
    } catch (e) { return mount(fail(e)); }
    mount(shapeDetail(shape, trace));
  }

  // One parallel burst, not six serial round-trips.
  async function loadTrace(id) {
    var paths = ["/summary", "/replayability", "/privacy-posture", "/diagnostic-summary",
                 "/verifications"];
    var results = await Promise.all(paths.map(function (p) {
      return api("/session/" + id + p).catch(function () { return {}; });
    }));
    return {
      id: id,
      summary: results[0].summary || {},
      replayability: results[1].replayability || {},
      privacy: results[2] || {},
      diagnostic: (results[3].diagnostic || {}),
      verifications: results[4].verifications || []
    };
  }

  function shapeDetail(shape, trace) {
    var fp = shape.fingerprint || {};
    var rep = trace.replayability || {};
    var grade = rep.grade || "—";
    var root = el("div", { class: "detail" });

    root.appendChild(el("button", { class: "crumb", text: "← Board", onclick: renderBoard }));

    // Verdict: the decision, above the fold — in whichever register the operator reads in.
    var facts = [];
    facts.push(shape.occurrences === 1 ? "1 person affected"
                                       : shape.occurrences + " people affected");
    if (tech) {
      if (rep.score !== undefined) facts.push("score " + rep.score);
      if (fp.failing_status) facts.push("HTTP " + fp.failing_status);
      if (fp.diagnostic_endpoint) facts.push(fp.diagnostic_endpoint);
    }
    var seen = relativeDay(shape.last_seen);
    if (seen) facts.push("last seen " + seen);

    var stageMeta = STAGES.filter(function (s) { return s.id === shape.stage; })[0] || STAGES[0];
    root.appendChild(el("div", { class: "verdict" }, [
      glyph(fp, 58),
      el("div", {}, [
        el("h1", { class: tech ? "mono" : "", text: headlineFor(shape) }),
        el("div", { class: "facts" }, [
          el("span", { class: "pill " + (shape.stage === "fixed" ? "ok" : "acc"),
                       text: tech ? stageMeta.label : stageMeta.plain })
        ].concat(facts.map(function (f) { return el("span", { text: f }); })))
      ]),
      el("div", { class: "grade" }, [
        tech
          ? el("span", { class: "pill " + (GRADE_TONE[grade] || ""), text: "grade " + grade })
          : el("span", { class: "pill " + (GRADE_TONE[grade] || ""),
                         text: confidenceBand(rep.score) })
      ])
    ]));

    // What this stage means, taught once.
    var stageNote = teach("stage_" + shape.stage, stageMeta.teach);
    if (stageNote) root.appendChild(el("div", { style: "margin-top:14px" }, [stageNote]));

    if (shape.prior_fixes && shape.prior_fixes.length) {
      var pf = shape.prior_fixes[0];
      root.appendChild(el("div", { class: "next" }, [
        el("div", { class: "lab", text: "You have fixed this before" }),
        el("div", {}, [
          el("span", { text: tech
            ? (pf.fix_ref || pf.trace_id) + " — " +
              Math.round((pf.similarity || 0) * 100) + "% structural match (" +
              (pf.reasons || []).join(", ") + "). "
            : "Something that broke this same way was fixed in " +
              (pf.fix_ref || pf.trace_id) + ". Start there. " }),
          extLink(pf.run_url, "See the CI run")
        ])
      ]));
    } else if (trace.diagnostic.recommended_next_step) {
      root.appendChild(el("div", { class: "next" }, [
        el("div", { class: "lab", text: "Recommended next step" }),
        el("div", { text: trace.diagnostic.recommended_next_step })
      ]));
    }

    // Sections
    // Tab wording follows the toggle too — "Repro" means nothing outside engineering.
    var TABS = [
      { id: "evidence", label: "Evidence", plain: "What happened",
        render: function () { return panelEvidence(shape, trace); } },
      { id: "repro", label: "Repro", plain: "The test",
        render: function () { return panelRepro(trace); } },
      { id: "verify", label: "Verify", plain: "Proof it's fixed",
        render: function () { return panelVerify(shape, trace); } },
      { id: "drafts", label: "Drafts", plain: "Ticket drafts",
        render: function () { return panelDrafts(trace); } },
      { id: "agent", label: "Agent view", plain: "What an AI sees",
        render: function () { return panelAgent(trace); } },
      { id: "attest", label: "Attestation", plain: "Signed record",
        render: function () { return panelAttest(trace); } }
    ];
    var tabs = el("div", { class: "tabs", role: "tablist", "aria-label": "Evidence sections" });
    var panel = el("div", { class: "panel", id: "tabpanel", role: "tabpanel",
                            "aria-live": "polite" });
    var active = "evidence";
    function select(id) {
      active = id;
      Array.prototype.forEach.call(tabs.children, function (btn) {
        btn.setAttribute("aria-selected", btn.dataset.tab === id ? "true" : "false");
        btn.setAttribute("tabindex", btn.dataset.tab === id ? "0" : "-1");
      });
      clear(panel);
      var out = TABS.filter(function (t) { return t.id === id; })[0].render();
      if (out instanceof Promise) {
        panel.appendChild(spinner());
        out.then(function (node) { clear(panel); panel.appendChild(node); })
           .catch(function (e) { clear(panel); panel.appendChild(fail(e)); });
      } else {
        panel.appendChild(out);
      }
    }
    TABS.forEach(function (t) {
      var b = el("button", { text: tech ? t.label : t.plain, role: "tab",
                             "aria-controls": "tabpanel",
                             onclick: function () { select(t.id); } });
      b.dataset.tab = t.id;
      tabs.appendChild(b);
    });
    root.appendChild(tabs);
    root.appendChild(panel);
    select(active);
    return root;
  }

  function panelEvidence(shape, trace) {
    var rep = trace.replayability || {};
    var wrap = el("div", {});

    // Replayability warnings, grouped. Six identical "templated route" warnings is one line,
    // not a thirty-line JSON array.
    var byCode = {};
    (rep.warnings || []).forEach(function (w) {
      (byCode[w.code] = byCode[w.code] || []).push(w);
    });
    var warnRows = Object.keys(byCode).map(function (code) {
      var group = byCode[code];
      var steps = group.map(function (w) { return w.step_index; })
                       .filter(function (s) { return s !== undefined && s !== null; });
      var body = tech
        ? (group[0].detail || "") + (steps.length ? "  (steps " + steps.join(", ") + ")" : "")
        : (WARNINGS[code] || group[0].detail || code.replace(/_/g, " "));
      return el("div", { style: "margin-bottom:8px" }, [
        el("div", {}, [
          el("span", { class: "pill warn",
                       text: group.length + (tech ? "×" : (group.length === 1 ? " step" : " steps")) }),
          tech ? el("span", { text: " " + code.replace(/_/g, " ") }) : null
        ]),
        el("div", { class: "note", text: body })
      ]);
    });

    var signals = rep.signals || {};
    wrap.appendChild(el("div", { class: "grid2" }, [
      box(tech ? "Replayability" : "Can a developer reproduce this?", [
        tech
          ? el("div", {}, [
              el("span", { class: "pill " + (GRADE_TONE[rep.grade] || ""),
                           text: "grade " + (rep.grade || "—") }),
              el("span", { class: "muted",
                           text: "  score " + (rep.score !== undefined ? rep.score : "—") })
            ])
          : el("div", {}, [
              el("span", { class: "pill " + (GRADE_TONE[rep.grade] || ""),
                           text: confidenceBand(rep.score) })
            ]),
        el("div", { class: "note", text: tech
          ? [signals.steps + " steps", signals.interactive + " interactive",
             signals.stable_selectors + " stable selectors"].join(" · ")
          : signals.steps + " steps were recorded, " + signals.interactive +
            " of them things the person clicked or typed into." }),
        warnRows.length
          ? el("div", { style: "margin-top:12px" }, [
              el("div", { class: "note", style: "margin-top:0",
                          text: tech ? "" : "What could make the test unreliable:" })
            ].concat(warnRows))
          : null
      ]),
      privacyProof(trace)
    ]));

    wrap.appendChild(box(tech ? "Fingerprint — how this shape is identified"
                              : "How we know these reports are the same bug", [
      el("div", { style: "display:flex;gap:14px;align-items:center" }, [
        glyph(shape.fingerprint, 44),
        el("div", { class: "note", text: tech
          ? "Templated routes and structural selectors only. Nothing here can identify a " +
            "person, which is why the shape — and its fix — stay matchable after retention " +
            "purges the trace body."
          : "We match on the structure of the failure — which page, which control, what went " +
            "wrong — never on anything about the person who hit it. That is also why this " +
            "keeps working after the report itself is deleted." })
      ]),
      tech ? kvTable(shape.fingerprint) : null
    ]));

    if (shape.trace_ids && shape.trace_ids.length > 1) {
      wrap.appendChild(box(tech ? shape.occurrences + " traces share this shape"
                                : shape.occurrences + " people reported this", [
        el("ul", { class: "tight mono" }, shape.trace_ids.map(function (t) {
          return el("li", { text: t });
        }))
      ]));
    }
    return wrap;
  }

  // Privacy proof — plain-language narrative, backed by the same scrubbed_fields data the
  // server reports. Never a raw JSON dump: this is the panel a compliance reviewer reads.
  function privacyProof(trace) {
    var scrub = (trace.privacy || {}).scrub || {};
    var fields = scrub.scrubbed_fields || [];
    var never = (trace.privacy || {}).never_captured || [];
    var narrative = fields.length
      ? "Before this report was stored, StepStitch stripped " + fields.length + " field" +
        (fields.length === 1 ? "" : "s") + " that could have carried sensitive information — " +
        "the original values were never written to disk."
      : "Nothing in this report needed scrubbing — no SSNs, account numbers, emails, or other " +
        "sensitive patterns were found in the text StepStitch kept.";
    return box("Privacy proof", [
      el("div", { text: narrative }),
      fields.length ? el("div", { class: "note", text: "What was scrubbed:" }) : null,
      fields.length ? el("ul", { class: "tight mono" }, fields.map(function (f) {
        return el("li", { text: f });
      })) : null,
      never.length ? el("div", { class: "note", text: "Regardless of this trace, StepStitch never captures, ever:" }) : null,
      never.length ? el("div", { class: "chips" }, never.map(function (n) {
        return el("span", { class: "chip strike", text: n });
      })) : null,
      el("div", { class: "note", text: "Verified by the server-side scrubber — independent of " +
        "the SDK — on every ingest." })
    ]);
  }

  async function panelRepro(trace) {
    var wrap = el("div", {});
    var full = await api("/session/" + trace.id + "/playwright").catch(function () { return {}; });
    var code = full.playwright_code || "";
    wrap.appendChild(box("Deterministic Playwright reproduction", [
      el("div", { class: "row-actions" }, [copyBtn(function () { return code; }, "Copy test")]),
      el("pre", { text: code }),
      el("div", { class: "note", text: "Text only. StepStitch never runs this — your CI does." })
    ]));
    var min = await api("/session/" + trace.id + "/minimal-repro").catch(function () { return null; });
    if (min && min.playwright_code) {
      wrap.appendChild(box("Minimal repro", [
        el("div", { class: "muted", text: "Reduced from " + min.original_steps + " to " +
                                          min.reduced_steps + " steps (the failing path)." }),
        el("div", { class: "row-actions", style: "margin-top:10px" },
           [copyBtn(function () { return min.playwright_code; }, "Copy minimal test")]),
        el("pre", { text: min.playwright_code })
      ]));
    }
    var frag = await api("/session/" + trace.id + "/fragility").catch(function () { return null; });
    if (frag && (frag.fragility || []).length) {
      var rows = frag.fragility.map(function (f) {
        var pct = Math.round((f.risk || 0) * 100);
        var tone = pct >= 70 ? "bad" : (pct >= 40 ? "warn" : "ok");
        return el("tr", {}, [
          el("td", { class: "k", text: "step " + f.step_index }),
          el("td", {}, [el("span", { class: "pill " + tone, text: pct + "%" })]),
          el("td", { text: f.stability }),
          el("td", { class: "muted", text: f.recommendation })
        ]);
      });
      wrap.appendChild(box("Fragility — what is most likely to break", [
        el("table", {}, [el("tbody", {}, rows)])
      ]));
    }
    return wrap;
  }

  // Closing the loop: the console used to dead-end here. Fix Memory stays empty until CI
  // reports a pre/post result, so the snippet that does it is generated inline.
  async function panelVerify(shape, trace) {
    var wrap = el("div", {});
    // Verification is a property of the SHAPE, not of one trace: the header can read "Fixed"
    // because a sibling trace went red->green. Gather every member's runs so the panel agrees
    // with the column the card is sitting in.
    var perTrace = await Promise.all((shape.trace_ids || [trace.id]).map(function (tid) {
      return api("/session/" + tid + "/verifications")
        .then(function (r) { return (r.verifications || []); })
        .catch(function () { return []; });
    }));
    var list = [].concat.apply([], perTrace).sort(function (a, b) {
      return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });
    var origin = window.location.origin;
    var snippet =
      "# StepStitch: report the repro outcome so the fix is provable.\n" +
      "# Run the generated test BEFORE the fix (expect fail) and AFTER (expect pass).\n" +
      "curl -sS -X POST \\\n" +
      "  " + origin + API + "/session/" + trace.id + "/verify \\\n" +
      "  -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n" +
      "  -H 'Content-Type: application/json' \\\n" +
      "  -d '{\"pre_passed\": false, \"post_passed\": true,\n" +
      "       \"fix_ref\": \"'\"$GIT_COMMIT\"'\", \"run_url\": \"'\"$CI_RUN_URL\"'\"}'\n" +
      "\n# Only pre=fail -> post=pass is recorded as confirmed_fixed.";

    if (list.length) {
      var rows = list.map(function (v) {
        var tone = v.verdict === "confirmed_fixed" ? "ok"
                 : (v.verdict === "not_reproduced" ? "warn" : "bad");
        return el("tr", {}, [
          el("td", {}, [el("span", { class: "pill " + tone, text: v.verdict })]),
          el("td", { class: "k mono", text: v.trace_id || "—" }),
          el("td", { class: "k", text: v.fix_ref || "—" }),
          el("td", {}, [extLink(v.run_url, "CI run") || el("span", { class: "muted", text: "—" })]),
          el("td", { class: "muted", text: String(v.created_at || "").slice(0, 19) })
        ]);
      });
      wrap.appendChild(box("Verification history for this shape", [
        el("table", {}, [
          el("thead", {}, [el("tr", {}, ["Verdict", "Trace", "Fix", "Run", "When"]
            .map(function (h) { return el("th", { text: h }); }))]),
          el("tbody", {}, rows)
        ]),
        el("div", { class: "note", text: "confirmed_fixed derives only from pre_passed=false " +
                                         "plus post_passed=true. StepStitch never runs code and " +
                                         "never merges." })
      ]));
    } else {
      wrap.appendChild(box("No CI result reported yet", [
        el("div", { class: "muted", text: "This shape stays untriaged — and the verified-fix " +
          "corpus stays empty — until your CI reports whether the repro failed before the fix " +
          "and passed after it. Wire this once:" })
      ]));
    }
    wrap.appendChild(box("Report from CI", [
      el("div", { class: "row-actions" }, [copyBtn(function () { return snippet; }, "Copy snippet")]),
      el("pre", { text: snippet })
    ]));
    return wrap;
  }

  var CONNECTORS = { servicenow: "ServiceNow", salesforce: "Salesforce", genesys: "Genesys",
                     jira: "Jira", zendesk: "Zendesk", github_issues: "GitHub Issues",
                     linear: "Linear", slack: "Slack" };

  async function panelDrafts(trace) {
    var wrap = el("div", {});
    var r = await api("/session/" + trace.id + "/export-preview", { method: "POST" })
      .catch(function () { return { drafts: {} }; });
    var drafts = r.drafts || {};
    var names = Object.keys(drafts);
    wrap.appendChild(el("div", { class: "note", style: "margin-bottom:12px",
      text: "Draft-only — every field below is flat and sanitized; drafts are previews, " +
            "nothing is sent to the connector." }));
    if (!names.length) {
      wrap.appendChild(emptyState("No draft adapters are configured on this host."));
    } else {
      var grid = el("div", { class: "grid2" }, names.map(function (n) {
        return box(CONNECTORS[n] || n, [kvTable(drafts[n])]);
      }));
      wrap.appendChild(grid);
    }

    var prBtn = el("button", { class: "ghost", text: "Preview regression PR (dry run)" });
    var prOut = el("div", {});
    prBtn.onclick = async function () {
      clear(prOut); prOut.appendChild(spinner());
      try {
        var pr = await api("/session/" + trace.id + "/github/pr?dry_run=true",
          jsonPost({ approved_by: "console-preview", idempotency_key: "preview-pr-" + trace.id,
                     dry_run: true }));
        clear(prOut);
        prOut.appendChild(kvTable(pr.would_open || pr));
      } catch (e) {
        clear(prOut);
        prOut.appendChild(el("div", { class: "muted", text: e.message +
          " — the GitHub bridge is not configured on this host, which is expected." }));
      }
    };
    var delBtn = el("button", { class: "ghost", text: "Preview delivery (dry run)" });
    var delOut = el("div", {});
    delBtn.onclick = async function () {
      clear(delOut); delOut.appendChild(spinner());
      try {
        var d = await api("/session/" + trace.id + "/deliver?dry_run=true",
          jsonPost({ approved_by: "console-preview", idempotency_key: "preview-" + trace.id }));
        clear(delOut);
        delOut.appendChild(kvTable(d));
      } catch (e) {
        clear(delOut);
        delOut.appendChild(el("div", { class: "muted", text: e.message +
          " — direct-write may be disabled on this host, which is expected." }));
      }
    };
    wrap.appendChild(box("Dry runs", [
      el("div", { class: "row-actions" }, [prBtn, delBtn]), prOut, delOut,
      el("div", { class: "note", text: "A human reviews and merges. StepStitch never does." })
    ]));
    return wrap;
  }

  // The model's-eye view: the literal payload an agent receives. This is the one place raw JSON
  // is the right rendering — the bytes ARE the claim.
  async function panelAgent(trace) {
    var tools = [
      ["get_trace_summary", "/summary"],
      ["get_replayability_score", "/replayability"],
      ["get_privacy_posture", "/privacy-posture"],
      ["get_diagnostic_summary", "/diagnostic-summary"],
      ["generate_playwright_repro", "/playwright"]
    ];
    var results = await Promise.all(tools.map(function (t) {
      return api("/session/" + trace.id + t[1]).catch(function (e) { return { error: e.message }; });
    }));
    var wrap = el("div", {});
    wrap.appendChild(el("div", { class: "note", style: "margin-bottom:12px",
      text: "This is the entire payload any connected LLM or agent can receive for this trace, " +
            "over the read-only MCP tools. Nothing outside this leaves your boundary." }));
    tools.forEach(function (t, i) {
      wrap.appendChild(box(null, [
        el("div", {}, [
          el("span", { class: "pill acc mono", text: t[0] }),
          el("span", { class: "muted mono", text: "  /session/{trace_id}" + t[1] })
        ]),
        el("pre", { style: "margin-top:10px", text: JSON.stringify(results[i], null, 2) })
      ]));
    });
    var never = (trace.privacy || {}).never_captured || [];
    if (never.length) {
      wrap.appendChild(box("Never reaches the model", [
        el("div", { class: "chips" }, never.map(function (n) {
          return el("span", { class: "chip strike", text: n });
        }))
      ]));
    }
    return wrap;
  }

  async function panelAttest(trace) {
    var r = await api("/session/" + trace.id + "/attestation");
    return el("div", {}, [
      box("Signed evidence attestation", [
        el("div", { text: "A canonical, tamper-evident evidence bundle" +
          (r.signed ? " signed with the tenant key." : " (unsigned — hash only).") +
          " Anyone can verify it independently; StepStitch holds no key." }),
        el("div", { style: "margin-top:10px" },
           [el("span", { class: "pill ok mono", text: r.bundle_sha256 || "" })]),
        el("pre", { style: "margin-top:10px", text: JSON.stringify(r.bundle, null, 2) }),
        r.signature ? el("div", { class: "note", text: "signature" }) : null,
        r.signature ? el("pre", { text: r.signature }) : null,
        el("div", { class: "note", text: r.verify_recipe || "" })
      ])
    ]);
  }

  // ---- agents ---------------------------------------------------------------------------
  var SCOPES = [
    ["none", "registered, no access"],
    ["summaries", "summaries · score · privacy posture"],
    ["repros", "+ the Playwright reproduction"],
    ["drafts", "+ sanitized ticket drafts"]
  ];

  async function renderAgents(justIssued) {
    mount(spinner("Loading agents…"));
    var agents = [], activity = {};
    try {
      agents = (await adminApi("/agents")).agents || [];
      var audit = await api("/audit?limit=500").catch(function () { return { entries: [] }; });
      (audit.entries || []).forEach(function (e) {
        var d = e.detail || {};
        var id = d.agent_id || d.actor_id;
        if (!id) return;
        var a = activity[id] = activity[id] || { reads: 0, denials: 0, last: null };
        if (String(e.action).indexOf("denied") >= 0) a.denials++; else a.reads++;
        if (!a.last) a.last = e.created_at;
      });
    } catch (e) { return mount(fail(e)); }

    var root = el("div", { class: "detail" });
    var name = el("input", { placeholder: "agent name (e.g. Claude Desktop)",
                             "aria-label": "agent name" });
    var scope = el("select", { "aria-label": "scope" }, SCOPES.map(function (s) {
      return el("option", { value: s[0], text: s[0] + " — " + s[1] });
    }));
    scope.value = "summaries";
    var issued = el("div", {});

    var register = el("button", { class: "primary", text: "Issue token" });
    register.onclick = async function () {
      if (!name.value.trim()) return;
      try {
        var r = await adminApi("/agents", jsonPost({ name: name.value.trim(), scope: scope.value }));
        loadStatus();
        renderAgents(r);
      } catch (e) { clear(issued); issued.appendChild(fail(e)); }
    };

    root.appendChild(box("Connect an agent", [
      el("div", { class: "muted", text: "Each agent gets its own scoped, revocable token. " +
        "The scope is the ceiling on what it can read over MCP — the host refuses an " +
        "out-of-scope call rather than silently allowing it. Your admin credential is never shared." }),
      el("div", { class: "row-actions", style: "margin-top:12px" }, [name, scope, register]),
      issued
    ]));

    if (justIssued && justIssued.token) {
      var cfg = JSON.stringify({
        mcpServers: {
          stepstitch: {
            command: "python", args: ["-m", "stepstitch_service.mcp_cli"],
            env: { STEPSTITCH_BASE_URL: window.location.origin + API,
                   STEPSTITCH_TOKEN: justIssued.token }
          }
        }
      }, null, 2);
      root.appendChild(box("New token — shown once, stored only as a hash", [
        el("pre", { text: justIssued.token }),
        el("div", { class: "row-actions" }, [copyBtn(function () { return justIssued.token; }, "Copy token")]),
        el("div", { class: "note", text: "MCP client config — paste into Claude, Copilot, or any MCP client:" }),
        el("pre", { text: cfg }),
        el("div", { class: "row-actions" }, [copyBtn(function () { return cfg; }, "Copy config")])
      ]));
    }

    if (!agents.length) {
      root.appendChild(box("No agents connected", [
        el("div", { class: "muted", text: "Nothing can read this host over MCP until you issue " +
          "a scoped token above. That is the point: access is granted per agent, not per host." })
      ]));
    } else {
      var rows = agents.map(function (a) {
        var act = activity[a.id] || { reads: 0, denials: 0, last: null };
        var revoke = el("button", { class: "link", text: a.revoked ? "revoked" : "Revoke" });
        revoke.disabled = !!a.revoked;
        revoke.onclick = async function () {
          try { await adminApi("/agents/" + encodeURIComponent(a.id) + "/revoke", { method: "POST" }); }
          finally { renderAgents(); }
        };
        return el("tr", {}, [
          el("td", { text: a.name }),
          el("td", {}, [el("span", { class: "pill acc", text: a.scope })]),
          el("td", {}, [el("span", { class: "pill " + (a.revoked ? "bad" : "ok"),
                                     text: a.revoked ? "revoked" : "active" })]),
          el("td", { class: "mono", text: String(act.reads) }),
          el("td", { class: "mono", text: String(act.denials) }),
          el("td", { class: "muted", text: act.last ? String(act.last).slice(0, 19) : "—" }),
          el("td", {}, [revoke])
        ]);
      });
      root.appendChild(box("Connected agents", [
        el("table", {}, [
          el("thead", {}, [el("tr", {}, ["Name", "Scope", "Status", "Reads", "Denials", "Last seen", ""]
            .map(function (h) { return el("th", { text: h }); }))]),
          el("tbody", {}, rows)
        ])
      ]));
    }

    root.appendChild(box("What no agent can ever do", [
      el("div", { class: "chips" }, ["delete or purge traces", "change retention",
        "trigger the kill switch", "read raw traces or user identity", "write to a system of record",
        "open, approve, or merge a pull request"].map(function (t) {
          return el("span", { class: "chip strike", text: t });
        }))
    ]));
    mount(root);
  }

  // ---- governance -----------------------------------------------------------------------
  async function renderGovernance() {
    mount(spinner("Loading governance…"));
    var cfg, audit;
    try {
      cfg = await adminApi("/config/scrub");
      audit = await api("/audit?limit=200");
    } catch (e) { return mount(fail(e)); }

    var root = el("div", { class: "detail" });
    var overrides = cfg.overrides || {};
    var patterns = overrides.patterns || [];
    var keys = overrides.forbidden_keys || [];

    // Scrub policy
    var label = el("input", { placeholder: "label (e.g. empid)", "aria-label": "pattern label" });
    var regex = el("input", { placeholder: "regex (e.g. EMP-\\d+)", "aria-label": "pattern regex" });
    var keyIn = el("input", { placeholder: "metadata key", "aria-label": "metadata key" });
    var pending = { patterns: patterns.slice(), forbidden_keys: keys.slice() };
    var listNode = el("div", {});

    function drawLists() {
      clear(listNode);
      listNode.appendChild(el("div", { class: "note", text: "Custom redaction patterns" }));
      listNode.appendChild(pending.patterns.length
        ? el("div", { class: "chips" }, pending.patterns.map(function (p) {
            return el("span", { class: "chip mono", text: (p.label || "?") + " · " + (p.regex || "") });
          }))
        : el("div", { class: "muted", text: "None yet." }));
      listNode.appendChild(el("div", { class: "note", text: "Extra dropped metadata keys" }));
      listNode.appendChild(pending.forbidden_keys.length
        ? el("div", { class: "chips" }, pending.forbidden_keys.map(function (k) {
            return el("span", { class: "chip mono", text: k });
          }))
        : el("div", { class: "muted", text: "None yet." }));
    }
    drawLists();

    var addPat = el("button", { class: "ghost", text: "Add pattern", onclick: function () {
      if (!label.value.trim() || !regex.value.trim()) return;
      pending.patterns.push({ label: label.value.trim(), regex: regex.value.trim() });
      label.value = ""; regex.value = ""; drawLists();
    } });
    var addKey = el("button", { class: "ghost", text: "Add key", onclick: function () {
      if (!keyIn.value.trim()) return;
      pending.forbidden_keys.push(keyIn.value.trim()); keyIn.value = ""; drawLists();
    } });

    var previewIn = el("textarea", { rows: 3, style: "width:100%",
      "aria-label": "text to preview", placeholder: "Paste sample text to see what would be redacted…" });
    var previewOut = el("pre", { text: "" });
    var previewBtn = el("button", { class: "ghost", text: "Preview redaction",
      onclick: async function () {
        try {
          var r = await adminApi("/scrub/preview", jsonPost({ text: previewIn.value,
            overrides: pending }));
          previewOut.textContent = r.redacted || "";
        } catch (e) { previewOut.textContent = e.message; }
      } });
    var saveBtn = el("button", { class: "primary", text: "Save scrub policy",
      onclick: async function () {
        try { await adminApi("/config/scrub", jsonPost(pending)); renderGovernance(); }
        catch (e) { previewOut.textContent = e.message; }
      } });

    root.appendChild(box("Scrub policy", [
      el("div", { class: "muted", text: "Base profile " + (cfg.profile || cfg.base_profile || "—") +
        ". Additions can only TIGHTEN the boundary — they add redaction and can never remove a " +
        "built-in PII rule." }),
      el("div", { class: "row-actions", style: "margin-top:12px" }, [label, regex, addPat]),
      el("div", { class: "row-actions" }, [keyIn, addKey]),
      listNode,
      el("div", { style: "margin-top:14px" }, [previewIn]),
      el("div", { class: "row-actions" }, [previewBtn, saveBtn]),
      previewOut
    ]));

    // Audit
    var entries = audit.entries || [];
    if (!entries.length) {
      root.appendChild(box("Audit trail", [
        el("div", { class: "muted", text: "No entries yet — the trail fills as soon as anyone " +
          "reads evidence. Open a shape and come back." }),
        el("div", { class: "row-actions", style: "margin-top:10px" },
           [el("button", { class: "primary", text: "Open the board", onclick: function () { go("board"); } })])
      ]));
    } else {
      var arows = entries.map(function (e) {
        var d = e.detail || {};
        var ref = d.trace_id || d.correlation_id || d.shape_id || d.agent_id || "";
        return el("tr", {}, [
          el("td", { class: "k mono", text: String(e.created_at || "").slice(0, 19) }),
          el("td", {}, [el("span", { class: "pill", text: e.action })]),
          el("td", { text: e.actor }),
          el("td", { class: "muted mono", text: ref })
        ]);
      });
      root.appendChild(box("Audit trail — every operator read is recorded", [
        el("div", { class: "muted", text: "Newest first · " + entries.length +
          " entries · detail carries structural ids only, never PII." }),
        el("table", { style: "margin-top:10px" }, [
          el("thead", {}, [el("tr", {}, ["Time", "Action", "Actor", "Reference"].map(function (h) {
            return el("th", { text: h });
          }))]),
          el("tbody", {}, arows)
        ])
      ]));
    }
    mount(root);
  }

  // ---- boot -----------------------------------------------------------------------------
  renderNav();
  syncChrome();
  if (token) { loadStatus(); go("board"); } else { renderGate(); }
})();
</script>
</body>
</html>
"""
