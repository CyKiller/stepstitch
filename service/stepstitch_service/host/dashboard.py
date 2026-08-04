"""Operator console for the StepStitch ingest host.

A single self-contained HTML page (no external assets, no build step) served at
``GET /dashboard`` under ``default-src 'none'`` with a per-request script nonce. It calls only
the **read-only / draft** operator endpoints with the admin bearer token the operator pastes in
(kept in sessionStorage, never persisted). It can preview drafts and run a **dry-run** deliver,
but exposes no destructive action.

Typography ships inside the page: ``__FONT_SANS_B64__`` is substituted with the base64 woff2
from :mod:`server.fonts` at render time. That is why the CSP carries ``font-src data:`` — the
bytes are already in the document and the directive grants no network reach. A system font stack
is the single clearest tell that an interface is an internal tool rather than a product.

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
  /* Geist Variable, embedded as a data: URI — the console cannot fetch a font under
     `default-src 'none'`, and a system stack is the clearest tell that something is an internal
     tool rather than a product. One variable file covers every weight. See server/fonts.py. */
  @font-face {
    font-family: "GeistConsole";
    src: url("data:font/woff2;base64,__FONT_SANS_B64__") format("woff2");
    font-weight: 100 900;
    font-style: normal;
    font-display: block;
  }

  :root {
    /* Near-black with a hint of blue, layered rather than flat. Borders are alpha so they sit
       ON the surface instead of fighting it. */
    --bg:#08090a;
    --panel:#0c0d0f;
    --surface:#101114;
    --raised:#16171b;
    --line:rgba(255,255,255,.07);
    --line-strong:rgba(255,255,255,.12);
    --fg:#eceef1;
    --muted:#8a8f98;
    --faint:#5c616a;
    --accent:#34d399;
    --accent-dim:rgba(52,211,153,.13);
    --ok:#34d399; --bad:#f87171; --warn:#fbbf24; --info:#7aa2f7;
    --r:6px; --r-lg:9px;
    --ease:cubic-bezier(.32,.72,0,1);
    --sidebar:244px;
  }
  * { box-sizing:border-box; }
  [hidden] { display:none !important; }
  html, body { height:100%; }
  body {
    margin:0; background:var(--bg); color:var(--fg);
    font:400 13px/1.5 "GeistConsole", ui-sans-serif, system-ui, -apple-system, sans-serif;
    letter-spacing:-.01em;
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
    display:flex; overflow:hidden;
  }
  .mono, code, pre { font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace; letter-spacing:0; }
  ::selection { background:rgba(52,211,153,.26); }
  :focus-visible { outline:2px solid var(--accent); outline-offset:1px; border-radius:var(--r); }
  ::-webkit-scrollbar { width:9px; height:9px; }
  ::-webkit-scrollbar-thumb { background:rgba(255,255,255,.09); border-radius:9px; }
  ::-webkit-scrollbar-thumb:hover { background:rgba(255,255,255,.16); }
  ::-webkit-scrollbar-track { background:transparent; }

  .grain {
    position:fixed; inset:0; z-index:60; pointer-events:none; opacity:.022; mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }

  /* ---- sidebar ---- */
  aside.sidebar {
    width:var(--sidebar); flex:0 0 var(--sidebar); height:100vh;
    background:var(--panel); border-right:1px solid var(--line);
    display:flex; flex-direction:column; padding:12px 10px 10px;
  }
  .brandrow { display:flex; align-items:center; gap:8px; padding:4px 8px 14px; }
  .mark {
    width:20px; height:20px; border-radius:5px; flex:0 0 auto;
    background:linear-gradient(150deg, var(--accent), #2dd4bf);
    box-shadow:0 0 0 1px rgba(52,211,153,.25), 0 4px 14px -6px rgba(52,211,153,.6);
  }
  .brandrow b { font-size:13.5px; font-weight:600; letter-spacing:-.02em; }
  .brandrow .env { font-size:10.5px; color:var(--faint); margin-left:auto; }

  .sgroup { margin-bottom:2px; }
  .slabel {
    font-size:10.5px; font-weight:550; letter-spacing:.06em; text-transform:uppercase;
    color:var(--faint); padding:12px 8px 5px;
  }
  .snav { display:flex; align-items:center; gap:9px; width:100%;
    padding:6px 8px; border:none; background:none; color:var(--muted);
    font:inherit; font-size:13px; border-radius:var(--r); cursor:pointer; text-align:left;
    transition:background-color .12s var(--ease), color .12s var(--ease); }
  .snav:hover { background:rgba(255,255,255,.045); color:var(--fg); }
  .snav[aria-current="page"] { background:rgba(255,255,255,.07); color:var(--fg); font-weight:500; }
  .snav .dot { width:7px; height:7px; border-radius:2px; flex:0 0 auto; background:var(--faint); }
  .snav .ct { margin-left:auto; font-size:11.5px; color:var(--faint); font-variant-numeric:tabular-nums; }
  .snav.on .ct { color:var(--muted); }
  /* Sidebar dots reuse the stage tokens defined with the overview, so the donut, the legend
     and the nav can never disagree about what colour a stage is. */
  .d-untriaged { background:var(--s-untriaged) !important; }
  .d-known_shape { background:var(--s-known_shape) !important; }
  .d-repro_invalid { background:var(--s-repro_invalid) !important; }
  .d-reproduced { background:var(--s-reproduced) !important; }
  .d-fix_failed { background:var(--s-fix_failed) !important; }
  .d-fixed { background:var(--s-fixed) !important; }

  /* A stepped list, not a wrapped sentence: at 244px the inline arrows stranded themselves on
     their own lines and the whole legend read as broken. */
  .legend { margin:0; padding:0 8px; font-size:11px; line-height:1.5; color:var(--faint);
    counter-reset:fl; }
  .legend i { display:block; font-style:normal; padding:2px 0 2px 16px; position:relative;
    counter-increment:fl; }
  .legend i::before { content:counter(fl); position:absolute; left:0; top:2px;
    color:rgba(52,211,153,.7); font-variant-numeric:tabular-nums; font-size:10px; }

  .sfoot { margin-top:auto; padding:10px 8px 2px; border-top:1px solid var(--line); }
  .privacy { font-size:10.5px; line-height:1.65; color:var(--faint); }
  .privacy strong { display:block; color:var(--muted); font-weight:550; margin-bottom:3px; }
  .privacy .never { text-decoration:line-through; text-decoration-color:rgba(248,113,113,.5); }
  .guarantees { font-size:10px; line-height:1.6; color:var(--faint); margin-top:9px; }

  /* ---- main ---- */
  main.view { flex:1 1 auto; min-width:0; height:100vh; display:flex; flex-direction:column; }
  .topbar {
    height:45px; flex:0 0 auto; display:flex; align-items:center; gap:10px;
    padding:0 16px; border-bottom:1px solid var(--line); background:var(--bg);
  }
  /* The topbar is a fixed 45px row, so a long failure headline must truncate rather than
     wrap — wrapping pushed the breadcrumb over the toggle and status text on narrow screens. */
  .crumbs { font-size:13px; color:var(--fg); font-weight:500; display:flex; align-items:center; gap:7px; min-width:0; flex-wrap:nowrap; overflow:hidden; }
  .crumbs > * { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .crumbs .sep { color:var(--faint); }
  .crumbs button { background:none; border:none; color:var(--muted); font:inherit; padding:0; cursor:pointer; }
  .crumbs button:hover { color:var(--fg); }
  .spacer { flex:1; }
  .kbd {
    display:inline-flex; align-items:center; gap:3px; padding:2px 5px; border-radius:4px;
    border:1px solid var(--line); background:rgba(255,255,255,.03);
    font-size:10.5px; color:var(--faint); font-family:inherit;
  }
  .searchbtn {
    display:flex; align-items:center; gap:8px; height:27px; padding:0 8px 0 9px;
    border:1px solid var(--line); background:rgba(255,255,255,.025); color:var(--faint);
    border-radius:var(--r); font:inherit; font-size:12.5px; cursor:pointer; min-width:190px;
    transition:border-color .15s var(--ease), background-color .15s var(--ease);
  }
  .searchbtn:hover { border-color:var(--line-strong); background:rgba(255,255,255,.05); }
  .searchbtn .kbd { margin-left:auto; }
  input#search { position:absolute; width:1px; height:1px; opacity:0; pointer-events:none; }

  .switch { display:inline-flex; align-items:center; gap:7px; font-size:12px; color:var(--muted); cursor:pointer; white-space:nowrap; }
  .switch input { appearance:none; width:28px; height:16px; border-radius:999px; background:rgba(255,255,255,.09); border:1px solid var(--line); position:relative; cursor:pointer; transition:background-color .18s var(--ease); }
  .switch input::after { content:""; position:absolute; top:1.5px; left:1.5px; width:11px; height:11px; border-radius:50%; background:var(--faint); transition:transform .18s var(--ease), background-color .18s var(--ease); }
  .switch input:checked { background:var(--accent-dim); border-color:rgba(52,211,153,.4); }
  .switch input:checked::after { transform:translateX(12px); background:var(--accent); }
  .switch:hover { color:var(--fg); }
  .status { font-size:11.5px; color:var(--faint); white-space:nowrap; }
  .status b { color:var(--muted); font-weight:500; }

  .content { flex:1 1 auto; overflow:auto; min-height:0; }

  /* ---- overview ---- */
  /* Stage colours are tokens so the donut, the legend and the sidebar dots can never drift. */
  :root{
    --s-untriaged:#5c616a; --s-known_shape:#34d399; --s-repro_invalid:#fbbf24;
    --s-reproduced:#7aa2f7; --s-fix_failed:#f87171; --s-fixed:#34d399;
  }
  .ov{padding:0 30px 64px;max-width:1340px;margin:0 auto}
  .ov .hero{display:grid;grid-template-columns:1.05fr .95fr;gap:40px;align-items:center;
    padding:46px 0 38px}
  .ov .eyebrow{font-size:10.5px;letter-spacing:.19em;text-transform:uppercase;
    color:var(--accent);margin:0 0 14px}
  .ov h1{margin:0;font-size:clamp(34px,4.1vw,56px);font-weight:600;letter-spacing:-.045em;
    line-height:1.03}
  .ov h1 b{color:var(--accent);font-weight:600}
  .ov .lede{color:var(--muted);font-size:14.5px;margin:16px 0 0;max-width:47ch;line-height:1.65}
  .ov .cta{display:flex;gap:9px;margin-top:24px}
  .ov .cta button{border-radius:99px;padding:8px 16px;font-size:13px}

  /* Every open failure as its own mark — the glyph stops being decoration. */
  .cst{position:relative;height:320px}
  .cnode{position:absolute;padding:9px;border-radius:12px;border:1px solid var(--line);
    background:rgba(22,23,27,.72);cursor:pointer;
    box-shadow:0 12px 34px -18px rgba(0,0,0,.9);
    transition:transform .3s var(--ease),border-color .3s var(--ease)}
  .cnode:hover{transform:translateY(-3px);border-color:rgba(52,211,153,.5)}
  .cnode.lead{padding:16px;border-color:rgba(52,211,153,.34);
    box-shadow:0 0 0 1px rgba(52,211,153,.12),0 22px 60px -26px rgba(52,211,153,.5)}
  .cnode .cl{display:block;font-size:9.5px;color:var(--faint);margin-top:5px;text-align:center}

  .stripe{display:grid;grid-template-columns:repeat(4,1fr);
    border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
  .stripe .st{padding:20px 24px 18px;border-left:1px solid var(--line)}
  .stripe .st:first-child{border-left:none;padding-left:0}
  .stripe .k{font-size:11.5px;color:var(--faint)}
  .stripe .v{font-size:34px;font-weight:600;letter-spacing:-.042em;margin-top:5px;line-height:1;
    font-variant-numeric:tabular-nums}
  .stripe .d{font-size:11.5px;color:var(--faint);margin-top:6px}

  .ov .two{display:grid;grid-template-columns:1.5fr 1fr;gap:18px;margin-top:30px}
  .ov .card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
    padding:22px 24px}
  .ov .card.accent{border-color:rgba(52,211,153,.16);
    background:linear-gradient(158deg,rgba(52,211,153,.075),var(--surface) 52%)}
  .ov .ch{display:flex;align-items:baseline;gap:11px;margin-bottom:18px}
  .ov .ch h2{margin:0;font-size:14.5px;font-weight:550;letter-spacing:-.022em}
  .ov .ch .sub{font-size:12px;color:var(--faint)}
  .ov .ch .rt{margin-left:auto;font-size:12px;color:var(--accent)}
  .ov .axis{display:flex;justify-content:space-between;font-size:10.5px;color:var(--faint);
    margin-top:9px}
  .chart{display:block}

  .ringwrap{display:flex;align-items:center;position:relative}
  .ringmid{position:absolute;left:66px;top:50%;transform:translate(-50%,-50%);text-align:center}
  .ringmid .b{font-size:25px;font-weight:600;letter-spacing:-.03em;line-height:1;
    font-variant-numeric:tabular-nums}
  .ringmid .s{font-size:10px;color:var(--faint);margin-top:2px}
  .legend{display:flex;flex-direction:column;gap:9px;margin-left:20px;flex:1}
  .lg{display:flex;align-items:center;gap:9px;font-size:12.5px}
  .lg .sw{width:8px;height:8px;border-radius:3px;flex:0 0 auto}
  .lg .n{margin-left:auto;color:var(--muted);font-weight:550;font-variant-numeric:tabular-nums}

  .prow{display:flex;align-items:center;gap:13px;padding:10px 0;border-top:1px solid var(--line)}
  .prow:first-child{border-top:none;padding-top:0}
  .prow .nm{font-size:12.5px;min-width:92px}
  .prow .bar{flex:1;height:7px;border-radius:99px;background:rgba(255,255,255,.05);
    overflow:hidden}
  .prow .fill{display:block;height:100%;border-radius:99px;
    background:linear-gradient(90deg,var(--accent-2),var(--accent))}
  .prow .n{font-size:12px;color:var(--muted);min-width:74px;text-align:right;
    font-variant-numeric:tabular-nums}

  .orow{display:flex;align-items:center;gap:11px;width:100%;text-align:left;padding:9px 0;
    background:none;border:none;border-top:1px solid var(--line);color:var(--fg);font:inherit;
    cursor:pointer}
  .orow:first-child{border-top:none}
  .orow:hover{background:rgba(255,255,255,.025)}
  .orow .t{flex:1;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .orow .pp{font-size:11.5px;color:var(--muted);min-width:62px;text-align:right}
  .orow .wh{font-size:11.5px;color:var(--faint);min-width:70px;text-align:right}
  @media(max-width:1120px){.ov .hero,.ov .two{grid-template-columns:1fr}.cst{display:none}}

  /* ---- grouped list (the board, as a list) ---- */
  .ghead {
    position:sticky; top:0; z-index:2; display:flex; align-items:center; gap:9px;
    padding:7px 16px; background:var(--panel); border-bottom:1px solid var(--line);
    font-size:11.5px; color:var(--muted); cursor:pointer; user-select:none;
  }
  .ghead:hover { background:var(--surface); }
  .ghead .gname { font-weight:550; color:var(--fg); letter-spacing:-.005em; }
  .ghead .gct { color:var(--faint); font-variant-numeric:tabular-nums; }
  .ghead .gwhy { color:var(--faint); font-size:11px; }
  .ghead .chev { color:var(--faint); font-size:9px; width:9px; transition:transform .18s var(--ease); }
  .ghead.collapsed .chev { transform:rotate(-90deg); }

  .row {
    display:flex; align-items:center; gap:11px; width:100%; text-align:left;
    padding:0 16px; height:42px; background:none; border:none; border-bottom:1px solid var(--line);
    color:var(--fg); font:inherit; cursor:pointer; position:relative;
    transition:background-color .12s var(--ease);
  }
  .row:hover { background:rgba(255,255,255,.028); }
  .row.sel { background:rgba(255,255,255,.05); }
  .row.sel::before { content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--accent); }
  .row .rt { font-size:13px; font-weight:450; letter-spacing:-.008em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; flex:1 1 auto; }
  .row .rt.mono { font-size:12.5px; }
  .row .meta { display:flex; align-items:center; gap:14px; flex:0 0 auto; font-size:11.5px; color:var(--faint); font-variant-numeric:tabular-nums; }
  .row .seen { color:var(--accent); font-size:11.5px; white-space:nowrap; }
  .row .cnt { min-width:74px; text-align:right; }
  .row .when { min-width:78px; text-align:right; }

  .listempty { padding:22px 16px; font-size:12.5px; color:var(--faint); }

  /* ---- command palette ---- */
  .scrim { position:fixed; inset:0; z-index:70; background:rgba(4,5,6,.62); backdrop-filter:blur(3px); display:grid; place-items:start center; padding-top:14vh; }
  .palette {
    width:min(560px, 92vw); background:var(--raised); border:1px solid var(--line-strong);
    border-radius:11px; overflow:hidden;
    box-shadow:0 24px 70px -18px rgba(0,0,0,.8), 0 0 0 1px rgba(255,255,255,.02) inset;
  }
  .palette input {
    width:100%; border:none; background:none; color:var(--fg); font:inherit; font-size:14.5px;
    padding:14px 16px; outline:none; letter-spacing:-.01em;
  }
  .palette input::placeholder { color:var(--faint); }
  .presults { max-height:52vh; overflow:auto; border-top:1px solid var(--line); }
  .pitem {
    display:flex; align-items:center; gap:10px; width:100%; text-align:left;
    padding:9px 16px; border:none; background:none; color:var(--fg); font:inherit; font-size:13px; cursor:pointer;
  }
  .pitem .pk { margin-left:auto; font-size:11px; color:var(--faint); }
  .pitem.on { background:rgba(255,255,255,.06); }
  .pitem .ps { color:var(--faint); font-size:11.5px; }
  .pempty { padding:16px; color:var(--faint); font-size:12.5px; }

  /* ---- detail ---- */
  .detail { padding:24px 28px 56px; max-width:1080px; }
  .verdict { display:flex; gap:16px; align-items:flex-start; }
  .verdict h1 { margin:0; font-size:21px; font-weight:560; letter-spacing:-.022em; line-height:1.3; text-wrap:pretty; }
  .verdict .facts { display:flex; flex-wrap:wrap; gap:6px 12px; margin-top:8px; font-size:12.5px; color:var(--faint); }
  .next {
    margin-top:18px; padding:11px 13px; border-radius:var(--r-lg);
    border:1px solid rgba(52,211,153,.22); background:var(--accent-dim); font-size:13px; line-height:1.55;
  }
  .next .lab { font-size:10.5px; letter-spacing:.07em; text-transform:uppercase; color:var(--accent); margin-bottom:3px; }
  /* The primary act on a failure: get the reproduction out of the browser and into CI. */
  .primary-actions { margin-top:20px; padding:13px 14px 4px; border:1px solid var(--line-strong); border-radius:var(--r-lg); background:var(--surface); }
  .primary-actions .lab { font-size:10.5px; letter-spacing:.07em; text-transform:uppercase; color:var(--muted); margin-bottom:9px; }
  .primary-actions .row-actions { margin-bottom:9px; }
  /* Demo banner: permanent, above everything, impossible to mistake for chrome. */
  .demobar {
    position:sticky; top:0; z-index:60; display:flex; gap:10px; align-items:baseline;
    flex-wrap:wrap; padding:8px 16px; font-size:12.5px; line-height:1.5;
    background:var(--accent-dim); border-bottom:1px solid rgba(52,211,153,.32); color:var(--fg);
  }
  .demobar b { color:var(--accent); font-weight:560; flex:0 0 auto; }
  .demobar span { color:var(--muted); }

  .tabs { display:flex; gap:1px; margin:24px 0 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .tabs button {
    background:none; border:none; border-bottom:1.5px solid transparent; border-radius:0;
    color:var(--muted); font:inherit; font-size:12.5px; padding:8px 11px; cursor:pointer;
    transition:color .15s var(--ease), border-color .15s var(--ease);
  }
  .tabs button:hover { color:var(--fg); }
  .tabs button[aria-selected="true"] { color:var(--fg); border-bottom-color:var(--accent); }
  .panel { padding-top:20px; }

  .box { background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg); padding:14px 15px; margin-bottom:11px; }
  .box h3 { margin:0 0 10px; font-size:11px; font-weight:550; color:var(--faint); text-transform:uppercase; letter-spacing:.06em; }
  .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:11px; }
  pre {
    white-space:pre-wrap; word-break:break-word; margin:0;
    background:var(--bg); border:1px solid var(--line); border-radius:var(--r);
    padding:12px; font-size:12px; line-height:1.62; max-height:420px; overflow:auto; color:#c9ccd1;
  }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th { text-align:left; color:var(--faint); font-weight:550; padding:3px 12px 6px 0; }
  td { padding:3px 12px 3px 0; vertical-align:top; }
  td.k { color:var(--faint); white-space:nowrap; }
  ul.tight { margin:6px 0 0; padding-left:17px; font-size:12.5px; color:var(--muted); }
  ul.tight li { margin-bottom:2px; }
  .chips { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
  .chip { border:1px solid var(--line); background:rgba(255,255,255,.02); border-radius:5px; padding:2px 7px; font-size:11.5px; color:var(--muted); }
  .chip.strike { text-decoration:line-through; text-decoration-color:rgba(248,113,113,.5); }
  .note { font-size:11.5px; color:var(--faint); margin-top:8px; line-height:1.6; }
  .row-actions { display:flex; gap:7px; flex-wrap:wrap; margin-bottom:12px; }

  /* ---- controls ---- */
  button, input, select, textarea {
    font:inherit; color:var(--fg); background:var(--surface);
    border:1px solid var(--line); border-radius:var(--r); padding:5px 9px; font-size:12.5px;
  }
  button { cursor:pointer; transition:background-color .14s var(--ease), border-color .14s var(--ease); }
  button:hover { border-color:var(--line-strong); background:var(--raised); }
  button:active { transform:translateY(.5px); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#04241a; font-weight:550; }
  button.primary:hover { background:#4ade9f; border-color:#4ade9f; }
  button.ghost { background:none; }
  button.link { background:none; border:none; color:var(--accent); padding:0; font-size:12.5px; }
  button.link:hover { background:none; text-decoration:underline; }
  a { color:var(--accent); text-underline-offset:2px; }

  .pill { display:inline-block; padding:1px 7px; border-radius:5px; font-size:11px; border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
  .pill.ok { color:var(--ok); border-color:rgba(52,211,153,.32); background:rgba(52,211,153,.08); }
  .pill.bad { color:var(--bad); border-color:rgba(248,113,113,.32); background:rgba(248,113,113,.08); }
  .pill.warn { color:var(--warn); border-color:rgba(251,191,36,.32); background:rgba(251,191,36,.08); }
  .pill.acc { color:var(--accent); border-color:rgba(52,211,153,.32); background:var(--accent-dim); }
  .muted { color:var(--muted); } .err { color:var(--bad); }

  /* ---- skeletons, teaching, setup ---- */
  @media (prefers-reduced-motion: no-preference) { .skel { animation:pulse 1.5s ease-in-out infinite; } }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.5 } }
  .skel { background:var(--surface); border-radius:var(--r); height:42px; border-bottom:1px solid var(--line); }
  .skel.line { height:11px; border-radius:999px; border:none; }

  /* A teaching note is a footnote, not an alert. One muted line under the group header, with a
     hairline to mark it as commentary — four boxed callouts on first load read as clutter. */
  .teach {
    display:flex; gap:8px; align-items:baseline;
    padding:8px 16px 8px 45px; border-bottom:1px solid var(--line);
    font-size:11.5px; color:var(--faint); line-height:1.55; background:rgba(255,255,255,.012);
  }
  .teach span { flex:1 1 auto; }
  .teach button { background:none; border:none; color:var(--faint); padding:0 3px; font-size:13px; line-height:1; flex:0 0 auto; }
  .teach button:hover { color:var(--fg); background:none; }

  .setup { max-width:600px; }
  .setup h1 { font-size:19px; margin:0 0 6px; font-weight:560; letter-spacing:-.02em; }
  .setup ol { list-style:none; margin:16px 0 0; padding:0; }
  .setup li { display:flex; gap:12px; padding:13px 0; border-top:1px solid var(--line); }
  .setup li:first-child { border-top:none; }
  .setup .tick { flex:0 0 auto; width:19px; height:19px; border-radius:50%; display:grid; place-items:center; border:1px solid var(--line-strong); color:var(--faint); font-size:10px; margin-top:1px; }
  .setup li.done .tick { border-color:rgba(52,211,153,.5); color:var(--ok); background:var(--accent-dim); }
  .setup li.done .st { color:var(--muted); }
  .setup .st { font-size:13.5px; font-weight:500; }
  .setup .sd { font-size:12.5px; color:var(--faint); margin-top:3px; line-height:1.55; }
  .setupbar { display:flex; align-items:center; gap:12px; padding:8px 16px; border-bottom:1px solid var(--line); font-size:11.5px; color:var(--faint); background:var(--panel); }
  .setupbar b { color:var(--accent); font-weight:550; }

  .gate { max-width:400px; margin:16vh auto 0; }
  .gate h1 { font-size:19px; margin:0 0 7px; font-weight:560; letter-spacing:-.02em; }
  .gate p { color:var(--muted); font-size:13px; margin:0 0 16px; line-height:1.6; }
  .gate .field { display:flex; gap:7px; }
  .gate input { flex:1; padding:7px 10px; }

  @media (max-width: 860px) {
    body { overflow:auto; }
    aside.sidebar { display:none; }
    main.view { height:auto; }
    /* Counts are a convenience, not navigation: drop them before the breadcrumb truncates. */
    #statusbar { display:none; }
    .detail { padding:18px 16px 48px; }
  }
</style>
</head>
<body>
<div class="grain" aria-hidden="true"></div>

<aside class="sidebar">
  <div class="brandrow">
    <span class="mark" aria-hidden="true"></span>
    <b>StepStitch</b>
    <span class="env">operator console</span>
  </div>

  <div class="sgroup" id="nav" role="navigation" aria-label="Sections"></div>
  <div class="sgroup" id="stagenav"></div>

  <!-- The pipeline, stated twice. Both registers ship in the document — the technical one names
       the real artefacts for an engineer, the plain one is what everyone else follows — and the
       technical-detail toggle decides which is shown. -->
  <div class="sgroup" id="flow-tech" hidden>
    <p class="slabel">How it works</p>
    <p class="legend"><i>Customer bug</i><i>privacy scrub</i><i>replayability score</i><i>Playwright repro</i><i>draft ticket/PR</i><i>verified fix</i></p>
  </div>
  <div class="sgroup" id="flow-plain">
    <p class="slabel">How it works</p>
    <p class="legend"><i>Someone reports a bug</i><i>personal details stripped</i><i>we check it can be reproduced</i><i>a test is written for it</i><i>a ticket is drafted</i><i>the fix is proven</i></p>
  </div>

  <div class="sfoot">
    <div class="privacy" id="privacy">
      <strong>Structural evidence only.</strong>
      StepStitch never captures, ever:
      <span class="never">screens</span>, <span class="never">input values</span>,
      <span class="never">page text</span>, <span class="never">raw URLs</span>,
      <span class="never">request bodies</span>, <span class="never">cookies &amp; headers</span>.
    </div>
    <div class="guarantees">
      Operator console &middot; every read and config change is audited &middot; records are
      scrubbed server-side before storage &middot; drafts are previews, nothing is sent &middot;
      evidence is never edited or deleted here.
    </div>
  </div>
</aside>

<main class="view" id="view">
  <div class="demobar" id="demobar" role="status" hidden>
    <b>Synthetic demo</b>
    <span id="demobartext"></span>
  </div>
  <div class="topbar">
    <div class="crumbs" id="crumbs"></div>
    <span class="spacer"></span>
    <button class="searchbtn" id="searchbtn">
      <span>Search failures</span><span class="kbd">&#8984;K</span>
    </button>
    <input id="search" type="search" aria-label="Search failures" autocomplete="off" tabindex="-1">
    <label class="switch" for="techtoggle">
      <input type="checkbox" id="techtoggle">
      <span>Technical</span>
    </label>
    <span class="status" id="statusbar" aria-live="polite"></span>
    <button id="tokenbtn" class="ghost">Disconnect</button>
  </div>
  <div class="content" id="content" aria-live="polite" aria-busy="false"></div>
</main>

<script nonce="__CSP_NONCE__">
(function () {
  "use strict";

  // The console is served at "<mount>/dashboard" — at the root for the real host, under
  // /demo for the public demo copy, and under the site's own path when proxied. Deriving the
  // API base from our own URL means one template works at every mount point, with nothing to
  // keep in sync. DEMO is substituted server-side (server/demo.py:render_dashboard).
  var ROOT = location.pathname.replace(/\/dashboard\/?$/, "");
  var API = ROOT + "/api/stepstitch/v1";
  var ADMIN = ROOT + "/admin";
  var DEMO = __DEMO_MODE__;
  var viewEl = document.getElementById("content");
  var navEl = document.getElementById("nav");
  var stageNavEl = document.getElementById("stagenav");
  var crumbsEl = document.getElementById("crumbs");
  // The demo needs no credential; a placeholder keeps the transport code identical.
  var token = DEMO ? "demo" : (sessionStorage.getItem("ss_token") || "");
  // StepStitch Local pairing: `stepstitch start` opens /dashboard#ss=<token> so the
  // developer never handles the generated credential. Fragments are never sent to the
  // server or its logs; adopt into sessionStorage (same place a pasted token lives)
  // and strip the URL immediately so it cannot be bookmarked or shared by copy/paste.
  function adoptPairingToken() {
    if (DEMO || !location.hash || location.hash.indexOf("#ss=") !== 0) return false;
    token = decodeURIComponent(location.hash.slice(4));
    try { sessionStorage.setItem("ss_token", token); } catch (e) { /* private mode */ }
    try { history.replaceState(null, "", location.pathname + location.search); } catch (e) {}
    return true;
  }
  adoptPairingToken();
  // Also on hashchange: restarting `stepstitch start` mints a new token, and a developer
  // with the console already open follows the new link in that same tab. Only the hash
  // changes, so without this the page keeps the dead token and answers 401 — with no
  // clue that the fix is simply a reload.
  window.addEventListener("hashchange", function () {
    if (adoptPairingToken()) location.reload();
  });

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
      body: o.body,
      // Forwarded so a long-running call (a local reproduction) can be cancelled.
      signal: o.signal
    });
    if (!res.ok) throw new Error("HTTP " + res.status + " on " + path);
    return res.json();
  }
  function api(path, opts) { return req(API, path, opts); }
  function adminApi(path, opts) { return req(ADMIN, path, opts); }
  function jsonPost(body) {
    return { method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(body) };
  }
  function jsonPut(body) {
    return { method: "PUT", headers: { "Content-Type": "application/json" },
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
  // Evidence has to be able to LEAVE the console — attached to a ticket, committed to a
  // repo, handed to an auditor. The endpoints set Content-Disposition, but they are admin-
  // gated, so a plain <a href> cannot carry the bearer token: fetch, then save the blob.
  // A blob: URL is same-origin data already in the document, so `default-src 'none'` is
  // satisfied without loosening the CSP.
  function downloadBtn(path, label, cls) {
    var b = el("button", { class: cls || "ghost", text: label });
    b.onclick = async function () {
      var original = b.textContent;
      b.disabled = true;
      b.textContent = "Preparing…";
      try {
        var res = await fetch(API + path, { headers: hdr() });
        if (!res.ok) throw new Error("HTTP " + res.status);
        var blob = await res.blob();
        var name = filenameFrom(res.headers.get("Content-Disposition")) || "stepstitch-export";
        var url = URL.createObjectURL(blob);
        var a = el("a", { href: url });
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 0);
        b.textContent = "Downloaded";
      } catch (e) {
        b.textContent = "Download failed";
      }
      setTimeout(function () { b.textContent = original; b.disabled = false; }, 1800);
    };
    return b;
  }
  // Read the server-supplied name, then strip anything that is not a plain filename so a
  // header can never steer the write. The server sanitizes too; this is the second gate.
  function filenameFrom(disposition) {
    if (!disposition) return null;
    var m = /filename="([^"]+)"/.exec(disposition);
    if (!m) return null;
    return m[1].replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 128);
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
    { id: "overview", label: "Overview", render: renderOverview },
    { id: "board", label: "Failures", render: renderBoard },
    { id: "agents", label: "Agents", render: renderAgents },
    { id: "governance", label: "Governance", render: renderGovernance }
  ];
  var current = "overview";

  var lastShapes = [];         // cached for the sidebar counts and the command palette
  var stageFilter = null;      // null = all stages

  function renderNav() {
    clear(navEl);
    navEl.appendChild(el("p", { class: "slabel", text: "Console" }));
    ROUTES.forEach(function (r) {
      var b = el("button", { class: "snav", text: r.label,
                             onclick: function () { go(r.id); } });
      if (r.id === current) b.setAttribute("aria-current", "page");
      navEl.appendChild(b);
    });
    renderStageNav();
  }

  // Stage filters live in the sidebar with live counts, so the pipeline is navigable without
  // the horizontal columns a board would need — and it still works at 200 shapes.
  function renderStageNav() {
    clear(stageNavEl);
    if (current !== "board" || !lastShapes.length) return;
    stageNavEl.appendChild(el("p", { class: "slabel", text: "Failures" }));

    var all = el("button", { class: "snav" + (stageFilter === null ? " on" : ""),
                             onclick: function () { stageFilter = null; renderBoard(); } }, [
      el("span", { class: "dot" }),
      el("span", { text: "All" }),
      el("span", { class: "ct", text: String(lastShapes.length) })
    ]);
    if (stageFilter === null) all.setAttribute("aria-current", "page");
    stageNavEl.appendChild(all);

    STAGES.forEach(function (stage) {
      var n = lastShapes.filter(function (s) { return s.stage === stage.id; }).length;
      if (!n) return;                       // an empty stage is not worth a permanent row
      var b = el("button", { class: "snav" + (stageFilter === stage.id ? " on" : ""),
                             onclick: function () { stageFilter = stage.id; renderBoard(); } }, [
        el("span", { class: "dot d-" + stage.id }),
        el("span", { text: tech ? stage.label : stage.plain }),
        el("span", { class: "ct", text: String(n) })
      ]);
      if (stageFilter === stage.id) b.setAttribute("aria-current", "page");
      stageNavEl.appendChild(b);
    });
  }

  // Breadcrumbs replace the old page-title guesswork: always says where you are, always offers
  // the way back.
  function renderCrumbs(trail) {
    clear(crumbsEl);
    (trail || []).forEach(function (part, i) {
      if (i) crumbsEl.appendChild(el("span", { class: "sep", text: "/" }));
      crumbsEl.appendChild(part.onclick
        ? el("button", { text: part.text, onclick: part.onclick })
        : el("span", { text: part.text }));
    });
  }

  var currentShapeId = null;   // set while a shape detail is open, so re-renders return to it

  function go(id, opts) {
    // Keep the URL in step with the view unless we are already responding to a hash change.
    if (!(opts && opts.fromHash)) setHash("#/" + id);
    current = id;
    currentShapeId = null;
    selectedRow = -1;
    renderNav();
    syncChrome();
    if (!token) return renderGate();
    loadStatus();   // counts move as you work — refresh them on every navigation
    var route = ROUTES.filter(function (r) { return r.id === id; })[0] || ROUTES[0];
    renderCrumbs([{ text: route.label }]);
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
    if (DEMO) showDemoBanner();   // the banner speaks in the operator's chosen register
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

  // Search opens the palette rather than living inline; the flow legend swaps register with
  // the toggle rather than being rewritten.
  function syncChrome() {
    document.getElementById("searchbtn").hidden = (current !== "board" || !!currentShapeId);
    document.getElementById("flow-tech").hidden = !tech;
    document.getElementById("flow-plain").hidden = tech;
  }

  async function loadStatus() {
    var bar = document.getElementById("statusbar");
    try {
      var s = await adminApi("/status");
      clear(bar);
      [["traces", s.traces], ["agents", s.agents_active + "/" + s.agents_total]]
        .forEach(function (pair, i) {
          if (i) bar.appendChild(document.createTextNode(" · "));
          bar.appendChild(document.createTextNode(pair[0] + " "));
          bar.appendChild(el("b", { text: String(pair[1]) }));
        });
    } catch (e) { clear(bar); }
  }

  // ---- command palette ---------------------------------------------------------------------
  // ⌘K over every failure plus the destinations. In a keyboard-first tool this replaces an
  // always-on search field: it costs no chrome and reaches more than a filter box would.
  var paletteOpen = false;

  function openPalette() {
    if (paletteOpen) return;
    paletteOpen = true;
    var input = el("input", { type: "text", placeholder: "Search failures, or jump to…",
                              "aria-label": "Command palette" });
    var results = el("div", { class: "presults" });
    var scrim = el("div", { class: "scrim" }, [
      el("div", { class: "palette", role: "dialog", "aria-modal": "true" }, [input, results])
    ]);
    var items = [], cursor = 0;

    function actions() {
      var out = ROUTES.filter(function (r) { return r.id !== current; }).map(function (r) {
        return { label: "Go to " + r.label, hint: "Section", run: function () { go(r.id); } };
      });
      out.push({ label: (tech ? "Hide" : "Show") + " technical detail", hint: "View",
                 run: function () { techEl.checked = !tech; techEl.onchange(); } });
      return out;
    }

    function draw() {
      var q = input.value.trim().toLowerCase();
      items = [];
      lastShapes.forEach(function (s) {
        var hay = [s.plain_summary, (s.fingerprint || {}).route, s.stage_label]
          .filter(Boolean).join(" ").toLowerCase();
        if (!q || hay.indexOf(q) >= 0) {
          items.push({ label: headlineFor(s), hint: stageLabelFor(s),
                       fp: s.fingerprint, run: function () { openShape(s.shape_id); } });
        }
      });
      actions().forEach(function (a) {
        if (!q || a.label.toLowerCase().indexOf(q) >= 0) items.push(a);
      });
      items = items.slice(0, 40);
      if (cursor >= items.length) cursor = Math.max(0, items.length - 1);

      clear(results);
      if (!items.length) {
        results.appendChild(el("div", { class: "pempty", text: "Nothing matches “" +
          input.value + "”." }));
        return;
      }
      items.forEach(function (it, i) {
        var b = el("button", { class: "pitem" + (i === cursor ? " on" : ""),
                               onclick: function () { closePalette(); it.run(); } }, [
          it.fp ? glyph(it.fp, 16) : el("span", { class: "ps", text: "→" }),
          el("span", { text: it.label }),
          el("span", { class: "pk", text: it.hint || "" })
        ]);
        b.onmousemove = function () {
          if (cursor === i) return;
          cursor = i; draw();
        };
        results.appendChild(b);
      });
    }

    input.oninput = function () { cursor = 0; draw(); };
    scrim.onclick = function (e) { if (e.target === scrim) closePalette(); };
    scrim.onkeydown = function (e) {
      if (e.key === "Escape") { e.preventDefault(); closePalette(); }
      else if (e.key === "ArrowDown" || (e.key === "n" && e.ctrlKey)) {
        e.preventDefault(); cursor = Math.min(cursor + 1, items.length - 1); draw();
        var on = results.querySelector(".pitem.on"); if (on) on.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp" || (e.key === "p" && e.ctrlKey)) {
        e.preventDefault(); cursor = Math.max(cursor - 1, 0); draw();
        var up = results.querySelector(".pitem.on"); if (up) up.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && items[cursor]) {
        e.preventDefault(); var run = items[cursor].run; closePalette(); run();
      }
    };
    document.body.appendChild(scrim);
    window.__ssPalette = scrim;
    draw();
    input.focus();
  }
  function closePalette() {
    paletteOpen = false;
    if (window.__ssPalette && window.__ssPalette.parentNode) {
      window.__ssPalette.parentNode.removeChild(window.__ssPalette);
    }
    window.__ssPalette = null;
  }
  function stageLabelFor(shape) {
    var st = STAGES.filter(function (s) { return s.id === shape.stage; })[0];
    return st ? (tech ? st.label : st.plain) : "";
  }

  // ---- keyboard ------------------------------------------------------------------------------
  function moveSelection(delta) {
    if (!rowShapes.length) return;
    selectedRow = Math.max(0, Math.min(rowShapes.length - 1, selectedRow + delta));
    var rows = viewEl.querySelectorAll(".row");
    Array.prototype.forEach.call(rows, function (r) { r.classList.remove("sel"); });
    var target = viewEl.querySelector('.row[data-idx="' + selectedRow + '"]');
    if (target) { target.classList.add("sel"); target.scrollIntoView({ block: "nearest" }); }
  }

  document.addEventListener("keydown", function (e) {
    var mod = e.metaKey || e.ctrlKey;
    if (mod && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      return paletteOpen ? closePalette() : openPalette();
    }
    if (paletteOpen) return;                       // the palette owns its own keys
    var t = e.target;
    if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;

    if (e.key === "/") { e.preventDefault(); return openPalette(); }
    if (e.key === "Escape" && currentShapeId) { e.preventDefault(); return renderBoard(); }
    if (current !== "board" || currentShapeId) return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); moveSelection(selectedRow < 0 ? 0 : 1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); moveSelection(-1); }
    else if (e.key === "Enter" && rowShapes[selectedRow]) {
      e.preventDefault(); openShape(rowShapes[selectedRow].shape_id);
    }
  });
  document.getElementById("searchbtn").onclick = openPalette;

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
        detail: s.local_mode
          ? "Open \"Connect your app\" for a snippet that already carries this host's " +
            "ingest credential, or send a sample below to see the console with evidence in it."
          : "Install @stepstitch/tracker in your app, or send a sample below to see the " +
            "console with real evidence in it." },
      { done: !!s.base_url_configured, title: "Point reproductions at your app",
        detail: "A generated test needs to know where your application lives, and which " +
                "values to use for templated routes and form fields. Without this every " +
                "reproduction targets localhost:3000 and cannot run in CI. Set " +
                "STEPSTITCH_APP_BASE_URL, or store per-project settings with " +
                "PUT /admin/config/repro. Run `stepstitch doctor` to check the whole setup." },
      { done: (s.verifications || 0) > 0, title: "Let CI report results",
        detail: "Your CI runs the generated test on the buggy commit and again on the fix, " +
                "then posts both measured outcomes back. Until it does, nothing can be proven " +
                "fixed and there is no memory to match new bugs against. Issue a " +
                "'verify'-scoped token in Agents — CI never needs your admin token." },
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

  // ---- StepStitch Local: connect your app -------------------------------------------------
  // In local mode the host generates the ingest credential, so the console can hand over a
  // ready-to-paste snippet. The developer never copies a token out of a terminal — the same
  // pairing idea as the dashboard's #ss= link, applied to the SDK side.
  var CONNECT_KITS = [
    { id: "next", label: "Next.js",
      code: function (t, origin) {
        return "// app/providers.tsx — client component\n" +
          "\"use client\";\n" +
          "import { StepStitchTracker } from \"@stepstitch/tracker\";\n\n" +
          "import { StepStitchTracker, mountReporter } from \"@stepstitch/tracker\";\n\n" +
          "const tracker = new StepStitchTracker({\n" +
          "  ingestEndpoint: \"/api/stepstitch\",   // your route, below\n" +
          "  appId: \"my-app\",\n" +
          "});\n" +
          "tracker.grantConsent(\"v1\");            // capture is OFF until this call\n" +
          "mountReporter({ tracker });            // the \"Report a problem\" control\n\n" +
          "// app/api/stepstitch/route.ts — the token stays on the server\n" +
          "export async function POST(req: Request) {\n" +
          "  return fetch(\"" + origin + "/api/stepstitch/v1/session\", {\n" +
          "    method: \"POST\",\n" +
          "    headers: {\n" +
          "      \"Content-Type\": \"application/json\",\n" +
          "      Authorization: `Bearer ${process.env.STEPSTITCH_INGEST_TOKEN}`,\n" +
          "    },\n" +
          "    body: await req.text(),\n" +
          "  });\n" +
          "}\n\n" +
          "# .env.local\n" +
          "STEPSTITCH_INGEST_TOKEN=" + t + "\n";
      } },
    { id: "express", label: "Express",
      code: function (t, origin) {
        return "// server.js — proxy so the browser never holds the token\n" +
          "app.post(\"/api/stepstitch\", express.json(), async (req, res) => {\n" +
          "  const r = await fetch(\"" + origin + "/api/stepstitch/v1/session\", {\n" +
          "    method: \"POST\",\n" +
          "    headers: {\n" +
          "      \"Content-Type\": \"application/json\",\n" +
          "      Authorization: `Bearer ${process.env.STEPSTITCH_INGEST_TOKEN}`,\n" +
          "    },\n" +
          "    body: JSON.stringify(req.body),\n" +
          "  });\n" +
          "  res.status(r.status).send(await r.text());\n" +
          "});\n\n" +
          "# .env\n" +
          "STEPSTITCH_INGEST_TOKEN=" + t + "\n";
      } },
    { id: "browser", label: "Browser only",
      code: function (t, origin) {
        return "// Local evaluation only: this puts the token in the page. For anything\n" +
          "// shared or deployed, proxy through your server (see the other tabs).\n" +
          "import { StepStitchTracker } from \"@stepstitch/tracker\";\n\n" +
          "const tracker = new StepStitchTracker({\n" +
          "  ingestEndpoint: \"" + origin + "/api/stepstitch/v1/session\",\n" +
          "  appId: \"my-app\",\n" +
          "  headers: { Authorization: \"Bearer " + t + "\" },\n" +
          "});\n" +
          "tracker.grantConsent(\"v1\");\n\n" +
          "// Report an API failure your app already caught:\n" +
          "// tracker.recordApiError({ route: \"/orders/:id\", status: 500 });\n" +
          "// Then submit when the user asks you to:\n" +
          "// await tracker.submitTrace({ explanation: userText });\n";
      } },
  ];

  function connectView(status) {
    var t = (status || {}).local_ingest_token || "";
    var origin = location.origin;
    var active = CONNECT_KITS[0];
    var codeBox = el("pre", { class: "code" });
    var tabs = el("div", { class: "row-actions" });
    var checkOut = el("div", { style: "margin-top:10px" });

    function paint() {
      clear(tabs);
      CONNECT_KITS.forEach(function (k) {
        var b = el("button", { class: k.id === active.id ? "primary" : "ghost", text: k.label,
                               onclick: function () { active = k; paint(); } });
        tabs.appendChild(b);
      });
      tabs.appendChild(copyBtn(function () { return active.code(t, origin); }, "Copy"));
      clear(codeBox);
      codeBox.appendChild(document.createTextNode(active.code(t, origin)));
    }
    paint();

    // The connection check: has a report arrived from something OTHER than this console's
    // sample? That is the only signal that the developer's own app is really wired up.
    var checkBtn = el("button", { class: "primary", text: "Check my connection" });
    checkBtn.onclick = async function () {
      checkBtn.disabled = true; checkBtn.textContent = "Checking…";
      clear(checkOut);
      try {
        var data = await api("/sessions?limit=50");
        var traces = data.traces || data.sessions || [];
        var real = traces.filter(function (tr) {
          return (tr.app_id || "") !== "console-sample";
        });
        if (real.length) {
          checkOut.appendChild(el("p", { class: "ok",
            text: "Connected — " + real.length + " report" + (real.length === 1 ? "" : "s") +
                  " from your app. Open Failures to see the evidence." }));
        } else {
          checkOut.appendChild(el("p", { class: "muted",
            text: "No report from your app yet. Paste the snippet above, trigger the bug, " +
                  "and submit a report — then check again." }));
        }
      } catch (e) { checkOut.appendChild(fail(e)); }
      checkBtn.disabled = false; checkBtn.textContent = "Check my connection";
    };

    return el("div", { class: "detail setup" }, [
      el("h1", { style: "font-size:21px;margin:0 0 6px;font-weight:640",
                 text: "Connect your app" }),
      el("p", { class: "muted", style: "margin:0 0 14px;font-size:13.5px",
                text: t
                  ? "This snippet already carries your local ingest credential — nothing to " +
                    "copy from the terminal. StepStitch captures structure only: no screens, " +
                    "no typed values, no page text."
                  : "Set STEPSTITCH_INGEST_TOKEN in your app to the ingest token this host " +
                    "was started with. StepStitch captures structure only: no screens, no " +
                    "typed values, no page text." }),
      tabs,
      codeBox,
      el("div", { class: "row-actions", style: "margin-top:14px" }, [checkBtn]),
      checkOut,
      el("div", { class: "note",
                  text: "Capture stays off until grantConsent() is called, and honors Global " +
                        "Privacy Control and Do Not Track." })
    ]);
  }

  function setupView(status) {
    var steps = setupSteps(status);
    var sampleBtn = el("button", { class: "primary", text: "Send a sample report" });
    var connectBtn = (status || {}).local_mode
      ? el("button", { class: "ghost", text: "Connect your app",
                       onclick: function () { mount(connectView(status)); } })
      : null;
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
        connectBtn,
        el("button", { class: "ghost", text: "Check again", onclick: renderBoard })
      ].filter(Boolean)),
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
    return el("div", { class: "setupbar" }, [
      el("span", {}, [
        el("b", { text: (steps.length - left.length) + "/" + steps.length + " set up" }),
        document.createTextNode(" · next: " + next.title)
      ]),
      el("button", { class: "link", text: "Show me", onclick: function () {
        mount(setupView(status));
      } })
    ]);
  }

  // ---- overview ----------------------------------------------------------------------------
  // The landing screen. Every number comes from the `overview` block on /shapes, computed
  // server-side by service/stepstitch_service/metrics.py — which is where it is unit-tested.
  //
  // It used to be recomputed here in JavaScript, mirroring that module. Mirrored maths is not
  // tested maths: the module had full coverage and was imported by nothing, so the arithmetic
  // actually on screen was the one copy nobody checked. A dashboard that quietly computes the
  // wrong number is worse than no dashboard, which only holds if the tested code is the code
  // that runs. This function now just reshapes the payload for rendering.

  function overviewMetrics(ov) {
    ov = ov || {};
    var stages = {};
    (ov.stages || []).forEach(function (r) { stages[r.stage] = r.count; });
    return {
      open: ov.open || 0,
      people: ov.people_affected || 0,
      fixed: ov.fixed || 0,
      repeat: ov.repeat_rate || 0,
      days: ov.days || [],
      series: ov.series || [],
      stages: STAGES.map(function (st) { return { st: st, n: stages[st.id] || 0 }; })
                    .filter(function (r) { return r.n; }),
      pages: ov.pages || [],
      total: ov.total || 0
    };
  }

  // Catmull-Rom -> cubic bezier. A polyline reads as a chart; a smoothed one reads as a
  // designed chart, and the shape of the data is unchanged.
  function smoothPath(series, w, h, close) {
    var hi = Math.max.apply(null, series) || 1, pad = 6;
    var p = series.map(function (v, i) {
      return [i * (w / Math.max(1, series.length - 1)),
              pad + (h - pad) * (1 - v / hi)];
    });
    // Catmull-Rom tangents are derived from a point's NEIGHBOURS, so a spiky series
    // (0 -> peak -> 0, the normal shape here) throws control points well outside the
    // plot band — measured -21 and +197 in a 170-tall box, which spilled the area fill
    // under the baseline and clipped the stroke at the top. A cubic bezier is contained
    // in the convex hull of its control points, so clamping their y into [pad, h] is a
    // guarantee of containment, not a nudge. x needs no clamp: it is monotonic by
    // construction and the ends repeat their endpoint.
    function clampY(y) { return y < pad ? pad : (y > h ? h : y); }
    var d = "M" + p[0][0].toFixed(1) + "," + p[0][1].toFixed(1);
    for (var i = 0; i < p.length - 1; i++) {
      var p0 = i ? p[i - 1] : p[0], p1 = p[i], p2 = p[i + 1];
      var p3 = (i + 2 < p.length) ? p[i + 2] : p2;
      d += " C" + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(1) + "," +
                  clampY(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1) + " " +
                  (p2[0] - (p3[0] - p1[0]) / 6).toFixed(1) + "," +
                  clampY(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1) + " " +
                  p2[0].toFixed(1) + "," + p2[1].toFixed(1);
    }
    if (close) d += " L" + p[p.length - 1][0].toFixed(1) + "," + h + " L" +
                    p[0][0].toFixed(1) + "," + h + " Z";
    return d;
  }

  function areaChart(series, w, h) {
    var root = svg("svg", { viewBox: "0 0 " + w + " " + h, preserveAspectRatio: "none",
                            width: "100%", height: String(h), class: "chart" });
    var defs = svg("defs", {}, []);
    var g = svg("linearGradient", { id: "ovg", x1: "0", y1: "0", x2: "0", y2: "1" }, [
      svg("stop", { offset: "0", "stop-color": "var(--accent)", "stop-opacity": ".38" }),
      svg("stop", { offset: "1", "stop-color": "var(--accent)", "stop-opacity": "0" })
    ]);
    var l = svg("linearGradient", { id: "ovl", x1: "0", y1: "0", x2: "1", y2: "0" }, [
      svg("stop", { offset: "0", "stop-color": "var(--accent-2)" }),
      svg("stop", { offset: "1", "stop-color": "var(--accent)" })
    ]);
    defs.appendChild(g); defs.appendChild(l); root.appendChild(defs);
    for (var i = 0; i <= 4; i++) {
      root.appendChild(svg("line", { x1: 0, y1: (h * i / 4).toFixed(0), x2: w,
        y2: (h * i / 4).toFixed(0), stroke: "rgba(255,255,255,.045)" }));
    }
    root.appendChild(svg("path", { d: smoothPath(series, w, h, true), fill: "url(#ovg)" }));
    root.appendChild(svg("path", { d: smoothPath(series, w, h), fill: "none",
      stroke: "url(#ovl)", "stroke-width": "2.2", "stroke-linecap": "round" }));
    return root;
  }

  function donut(rows, size) {
    var thick = 15, r = (size - thick) / 2, c = size / 2, circ = 2 * Math.PI * r;
    var total = rows.reduce(function (a, x) { return a + x.n; }, 0) || 1;
    var root = svg("svg", { width: String(size), height: String(size),
                            viewBox: "0 0 " + size + " " + size });
    root.appendChild(svg("circle", { cx: c, cy: c, r: r.toFixed(2), fill: "none",
      stroke: "rgba(255,255,255,.05)", "stroke-width": thick }));
    var off = 0;
    rows.forEach(function (row) {
      var seg = circ * row.n / total;
      root.appendChild(svg("circle", { cx: c, cy: c, r: r.toFixed(2), fill: "none",
        stroke: "var(--s-" + row.st.id + ")", "stroke-width": thick,
        "stroke-dasharray": (seg - 2).toFixed(2) + " " + (circ - seg + 2).toFixed(2),
        "stroke-dashoffset": (-off).toFixed(2),
        transform: "rotate(-90 " + c + " " + c + ")" }));
      off += seg;
    });
    return root;
  }

  async function renderOverview() {
    mountLoading(skeleton("board"));
    var shapes, status, overview;
    try {
      var data = await api("/shapes");
      shapes = data.shapes || [];
      overview = data.overview || {};   // computed by metrics.py, not re-derived here
      status = await adminApi("/status").catch(function () { return lastStatus || {}; });
      lastStatus = status;
    } catch (e) { return mount(fail(e)); }

    lastShapes = shapes;
    renderStageNav();
    if (!shapes.length) return mount(setupView(status));

    var m = overviewMetrics(overview);
    var days = m.days;
    var root = el("div", { class: "ov" });

    // Hero: the one number that matters, and the constellation of what is behind it.
    var top = shapes.slice().sort(function (a, b) {
      return (b.occurrences || 0) - (a.occurrences || 0); }).slice(0, 6);
    var POS = [[40, 24, 76], [3, 4, 42], [7, 60, 50], [72, 2, 44], [78, 56, 38], [28, 80, 36]];
    var cst = el("div", { class: "cst" }, top.map(function (s, i) {
      var p = POS[i] || POS[0];
      // These buttons contain only an SVG glyph, so `title` is their sole visible label —
      // and title alone is not a reliable accessible name. Name them explicitly.
      var label = s.plain_summary || "Open this failure";
      var node = el("button", { class: "cnode" + (i ? "" : " lead"),
        style: "left:" + p[0] + "%;top:" + p[1] + "%",
        title: label, "aria-label": label,
        onclick: function () { openShape(s.shape_id); } },
        [glyph(s.fingerprint, p[2])]);
      if (!i) node.appendChild(el("span", { class: "cl",
        text: (s.plain_summary || "").split("—")[0].trim() }));
      return node;
    }));

    root.appendChild(el("div", { class: "hero" }, [
      el("div", {}, [
        el("p", { class: "eyebrow", text: "Last 30 days" }),
        el("h1", {}, [
          el("b", { text: m.open + (m.open === 1 ? " failure" : " failures") }),
          el("br"), document.createTextNode(m.open === 1 ? "is open right now."
                                                         : "are open right now.")
        ]),
        el("p", { class: "lede", text: "They affected " + m.people.toLocaleString() +
          (m.people === 1 ? " person. " : " people. ") + m.fixed +
          (m.fixed === 1 ? " was" : " were") +
          " proven fixed — each verified by a test that failed before the fix and passed " +
          "after it. Nothing here was learned from anyone's screen." }),
        el("div", { class: "cta" }, [
          el("button", { class: "primary", text: "Work the queue",
                         onclick: function () { go("board"); } }),
          el("button", { class: "ghost", text: "See what agents can read",
                         onclick: function () { go("agents"); } })
        ])
      ]),
      cst
    ]));

    // Metric stripe.
    var tiles = [
      ["Open failures", String(m.open), m.total + " tracked in total"],
      ["People affected", m.people.toLocaleString(), "across open failures"],
      ["Proven fixed", String(m.fixed), "red then green, verified"],
      ["Repeat rate", m.repeat + "%", "shapes you had fixed before"]
    ];
    root.appendChild(el("div", { class: "stripe" }, tiles.map(function (t) {
      return el("div", { class: "st" }, [
        el("div", { class: "k", text: t[0] }),
        el("div", { class: "v", text: t[1] }),
        el("div", { class: "d", text: t[2] })
      ]);
    })));

    // Trend + stage mix. The series is PEOPLE per day, not new-failures per day: a real
    // deployment produces a handful of distinct failures a month, so plotting those drew a
    // flat line with a couple of spikes and read as "nothing is happening" while eighty-odd
    // people were hitting them. Same data, honest resolution.
    var total = m.series.reduce(function (a, b) { return a + b; }, 0);
    var avg = days.length ? (total / days.length).toFixed(1) : "0.0";
    root.appendChild(el("div", { class: "two" }, [
      el("div", { class: "card accent" }, [
        el("div", { class: "ch" }, [
          el("h2", { text: "People affected" }),
          el("span", { class: "sub", text: "per day, last 30 days" }),
          el("span", { class: "rt", text: avg + " a day on average" })
        ]),
        areaChart(m.series, 660, 170),
        el("div", { class: "axis" }, [
          el("span", { text: days[0] || "" }), el("span", { text: days[14] || "" }),
          el("span", { text: "today" })
        ])
      ]),
      el("div", { class: "card" }, [
        el("div", { class: "ch" }, [
          el("h2", { text: "Where they stand" }),
          el("span", { class: "sub", text: m.open + " open" })
        ]),
        el("div", { class: "ringwrap" }, [
          donut(m.stages, 132),
          el("div", { class: "ringmid" }, [
            el("div", { class: "b", text: String(m.open) }),
            el("div", { class: "s", text: "open" })
          ]),
          el("div", { class: "legend" }, m.stages.map(function (row) {
            return el("div", { class: "lg" }, [
              el("span", { class: "sw", style: "background:var(--s-" + row.st.id + ")" }),
              el("span", { text: tech ? row.st.label : row.st.plain }),
              el("span", { class: "n", text: String(row.n) })
            ]);
          }))
        ])
      ])
    ]));

    // Worst-hit pages + latest.
    var hi = m.pages.length ? m.pages[0].people : 1;
    root.appendChild(el("div", { class: "two" }, [
      el("div", { class: "card" }, [
        el("div", { class: "ch" }, [
          el("h2", { text: "Worst-hit pages" }),
          el("span", { class: "sub", text: "by people affected" })
        ]),
        el("div", {}, m.pages.map(function (p) {
          return el("div", { class: "prow" }, [
            el("span", { class: "nm", text: tech ? p.route : pageName(p.route) }),
            el("span", { class: "bar" }, [
              el("span", { class: "fill",
                           style: "width:" + Math.round(p.people / hi * 100) + "%" })
            ]),
            el("span", { class: "n", text: p.people + (p.people === 1 ? " person" : " people") })
          ]);
        }))
      ]),
      el("div", { class: "card" }, [
        el("div", { class: "ch" }, [
          el("h2", { text: "Latest" }),
          el("span", { class: "sub", text: "newest first" }),
          el("span", { class: "rt", text: "View all", onclick: function () { go("board"); },
                       style: "cursor:pointer" })
        ]),
        el("div", {}, shapes.slice(0, 5).map(function (s) {
          return el("button", { class: "orow",
                                onclick: function () { openShape(s.shape_id); } }, [
            glyph(s.fingerprint, 22),
            el("span", { class: "t", text: headlineFor(s) }),
            el("span", { class: "pp", text: (s.occurrences || 0) +
              ((s.occurrences || 0) === 1 ? " person" : " people") }),
            el("span", { class: "wh", text: relativeDay(s.last_seen) || "" })
          ]);
        }))
      ])
    ]));

    mount(root);
  }

  // "/accounts/:id/transfer" -> "Transfer". Mirrors humanize.page_name.
  function pageName(route) {
    var segs = String(route || "").split("/").filter(Boolean);
    for (var i = segs.length - 1; i >= 0; i--) {
      if (!/^[:{*]/.test(segs[i]) && !/^\d+$/.test(segs[i])) {
        var w = segs[i].replace(/[-_.]+/g, " ");
        return w.charAt(0).toUpperCase() + w.slice(1);
      }
    }
    return "Home";
  }

  // ---- board ----------------------------------------------------------------------------
  // An empty column is information too: "nothing invalid" is a different sentence from
  // "nothing fixed yet", so each says its own.
  // `label` is the technical name; `plain` is what a support lead or QA engineer reads. The
  // stage IDs are the contract — only the wording changes with the toggle.
  var STAGES = [
    { id: "untriaged", label: "Untriaged", plain: "Waiting for a test run",
      why: "no verdict recorded yet",
      // Careful wording: freezing a session RUNS the reproduction and measures a red run,
      // so "nobody has run the test" became false the moment local reproduction shipped.
      // What is actually missing at this stage is a recorded verdict on a FIX.
      teach: "No fix has been verified for these yet. StepStitch may already have " +
             "reproduced them locally — a verdict is recorded once a fix is checked.",
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

  // One failure = one row. A list scales to hundreds where columns stop working around thirty,
  // and it is what a keyboard-driven tool actually wants.
  function shapeRow(shape, index) {
    var fp = shape.fingerprint || {};
    var meta = [];
    if (tech) {
      if (fp.failing_status) meta.push(String(fp.failing_status));
      else if (fp.exception_type) meta.push(fp.exception_type);
    }
    var row = el("button", { class: "row", "data-idx": String(index),
                             onclick: function () { openShape(shape.shape_id); } }, [
      glyph(fp, 20),
      el("span", { class: "rt" + (tech ? " mono" : ""), text: headlineFor(shape) }),
      shape.prior_fixes && shape.prior_fixes.length
        ? el("span", { class: "seen", text: tech
            ? Math.round((shape.prior_fixes[0].similarity || 0) * 100) + "% match"
            : "fixed before" })
        : null,
      el("span", { class: "meta" }, meta.map(function (m) {
        return el("span", { text: m });
      }).concat([
        el("span", { class: "cnt", text: shape.occurrences === 1
          ? "1 person" : shape.occurrences + " people" }),
        el("span", { class: "when", text: relativeDay(shape.last_seen) || "" })
      ]))
    ]);
    return row;
  }

  // Free-text filter across everything a person might search by, in either register.
  function matchesQuery(shape) {
    if (!query) return true;
    var fp = shape.fingerprint || {};
    return [shape.plain_summary, shape.stage_label, fp.route, fp.diagnostic_type,
            fp.exception_type, fp.failing_status, fp.terminal_selector]
      .filter(Boolean).join(" ").toLowerCase().indexOf(query) >= 0;
  }

  var rowShapes = [];       // flat, in render order — what j/k and Enter walk
  var selectedRow = -1;

  async function renderBoard() {
    mountLoading(skeleton("board"));
    var data, status;
    try {
      data = await api("/shapes");
      status = await adminApi("/status").catch(function () { return lastStatus || {}; });
      lastStatus = status;
    } catch (e) { return mount(fail(e)); }

    var shapes = data.shapes || [];
    lastShapes = shapes;
    renderStageNav();

    // Nothing to show yet is not an error — it means setup is unfinished. Say what to do next.
    if (!shapes.length) return mount(setupView(status));

    var visible = shapes.filter(matchesQuery).filter(function (s) {
      return !stageFilter || s.stage === stageFilter;
    });
    var wrap = el("div", {});
    rowShapes = [];

    if (query || stageFilter) {
      wrap.appendChild(el("div", { class: "setupbar" }, [
        el("span", { text: "Showing " + visible.length + " of " + shapes.length +
                           (shapes.length === 1 ? " failure" : " failures") }),
        el("button", { class: "link", text: "Clear", onclick: function () {
          query = ""; stageFilter = null; searchEl.value = ""; renderNav(); renderBoard();
        } })
      ]));
    } else if (status && !setupComplete(status)) {
      wrap.appendChild(setupMini(status));
    }

    if (!visible.length) {
      wrap.appendChild(el("p", { class: "listempty",
        text: "Nothing matches. Try a different search, or clear the filter." }));
      return mount(wrap);
    }

    // Grouped by stage with sticky headers — the pipeline is still legible, but vertically,
    // so it survives hundreds of rows.
    STAGES.forEach(function (stage) {
      var items = visible.filter(function (s) { return s.stage === stage.id; });
      if (!items.length) return;
      var collapsed = pref("fold_" + stage.id, false);
      var body = el("div", {});
      var head = el("div", { class: "ghead" + (collapsed ? " collapsed" : ""),
                             role: "button", tabindex: "0" }, [
        el("span", { class: "chev", text: "▼" }),
        el("span", { class: "gname", text: tech ? stage.label : stage.plain }),
        el("span", { class: "gct", text: String(items.length) }),
        el("span", { class: "gwhy", text: stage.why })
      ]);
      function toggleFold() {
        collapsed = !collapsed;
        setPref("fold_" + stage.id, collapsed);
        head.className = "ghead" + (collapsed ? " collapsed" : "");
        body.hidden = collapsed;
      }
      head.onclick = toggleFold;
      head.onkeydown = function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleFold(); }
      };
      wrap.appendChild(head);

      // A group explains itself the first time it actually has something in it — the moment
      // the concept becomes relevant, rather than in a tour up front.
      var note = teach("col_" + stage.id, stage.teach);
      if (note) body.appendChild(note);

      items.forEach(function (s) {
        body.appendChild(shapeRow(s, rowShapes.length));
        rowShapes.push(s);
      });
      body.hidden = collapsed;
      wrap.appendChild(body);
    });
    mount(wrap);
  }

  // ---- shape detail ---------------------------------------------------------------------
  // Sections render IN PLACE. Nothing is ever injected above what the operator is reading.
  var GRADE_TONE = { A: "ok", B: "ok", C: "warn", D: "warn", E: "bad", F: "bad" };

  async function openShape(shapeId, opts) {
    if (!(opts && opts.fromHash)) setHash("#/shape/" + encodeURIComponent(shapeId));
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

    // Location and the way back live in the topbar breadcrumb, not inline above the content.
    renderCrumbs([
      { text: "Failures", onclick: renderBoard },
      { text: headlineFor(shape) }
    ]);

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

    // The one thing an operator came here to do. It used to be buried inside the Repro tab
    // behind a Copy button; a reproduction that stays in the browser proves nothing, so
    // running or exporting it is now the most prominent action on the failure.
    var actions = el("div", { class: "primary-actions" }, [
      el("div", { class: "lab",
                  text: tech ? "Run or export the reproduction"
                             : "Take the test to your code" }),
      el("div", { class: "row-actions" }, [
        downloadBtn("/session/" + trace.id + "/playwright/download",
                    "Download .spec.ts", "primary"),
        el("button", {
          class: "ghost",
          text: "Copy test",
          onclick: function (e) {
            var b = e.currentTarget;
            api("/session/" + trace.id + "/playwright").then(function (r) {
              if (navigator.clipboard) navigator.clipboard.writeText(r.playwright_code || "");
              b.textContent = "Copied";
            }).catch(function () { b.textContent = "Unavailable"; });
            setTimeout(function () { b.textContent = "Copy test"; }, 1800);
          }
        }),
        el("button", {
          class: "ghost",
          text: tech ? "Copy safe agent packet" : "Copy what an AI can see",
          onclick: function (e) {
            var b = e.currentTarget;
            api("/session/" + trace.id + "/agent-packet").then(function (packet) {
              if (navigator.clipboard) {
                navigator.clipboard.writeText(JSON.stringify(packet, null, 2));
              }
              b.textContent = "Copied";
            }).catch(function () { b.textContent = "Unavailable"; });
            setTimeout(function () {
              b.textContent = tech ? "Copy safe agent packet" : "Copy what an AI can see";
            }, 1800);
          }
        }),
        downloadBtn("/session/" + trace.id + "/attestation/download", "Download attestation")
      ])
    ]);
    root.appendChild(actions);
    var packetNote = teach("agent_packet",
      "The agent packet is exactly what an AI assistant receives: structure, scores, the " +
      "generated test, and — once a reproduction has run — the deep diagnostics from that " +
      "local run (failure stack, console errors, failed requests). Those come from " +
      "StepStitch's own run on this machine, never from the person who reported the bug, " +
      "and every string is scrubbed — but the run targets the application YOU configured, " +
      "so what that app prints is only as customer-free as its data. From the report " +
      "itself: no page text, no values, no raw URLs.");
    if (packetNote) root.appendChild(packetNote);

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

  // The four honest answers, in the words an operator uses. StepStitch derives these from
  // what it observed; the console only renders them.
  var REPRO_VERDICTS = {
    reproduced: { label: "Reproduced", tone: "bad",
      plain: "The failure happened again here." },
    not_reproduced: { label: "Could not reproduce", tone: "ok",
      plain: "The app behaved correctly — this evidence does not fail here." },
    needs_setup: { label: "Needs setup", tone: "warn",
      plain: "Something required is missing, so the test was not run." },
    inconclusive: { label: "Inconclusive", tone: "warn",
      plain: "No reliable answer — see the detail below." }
  };

  function reproVerdict(res) {
    if (res && res.status === "refused") {
      return el("div", {}, [
        el("span", { class: "pill warn", text: "Refused" }),
        el("p", { class: "muted", text: res.detail || "" })
      ]);
    }
    var meta = REPRO_VERDICTS[res.verdict] || { label: res.verdict, tone: "warn", plain: "" };
    var kids = [
      el("div", { class: "row-actions" }, [
        el("span", { class: "pill " + meta.tone, text: meta.label }),
        res.flaky ? el("span", { class: "pill warn", text: "flaky" }) : null
      ].filter(Boolean)),
      el("p", {}, [document.createTextNode(meta.plain)]),
      el("p", { class: "muted", text: res.detail || "" })
    ];
    (res.blockers || []).forEach(function (b) {
      kids.push(el("p", { class: "muted", text: "· " + b.title + ": " + b.detail }));
    });
    if (res.script_sha256) {
      kids.push(el("p", { class: "note",
        text: "frozen test sha256 " + String(res.script_sha256).slice(0, 16) +
              "… — verification reruns exactly these bytes." }));
    }
    return el("div", {}, kids);
  }

  async function panelRepro(trace) {
    var wrap = el("div", {});
    var full = await api("/session/" + trace.id + "/playwright").catch(function () { return {}; });
    var code = full.playwright_code || "";
    // In local mode StepStitch DOES run this, so the note must not claim otherwise.
    var isLocal = !!(lastStatus && lastStatus.local_mode);
    var actions = [copyBtn(function () { return code; }, "Copy test")];
    var runOut = el("div", { style: "margin-top:12px" });
    if (isLocal) {
      var runBtn = el("button", { class: "primary", text: "Reproduce locally" });
      var cancelBtn = el("button", { class: "ghost", text: "Cancel", hidden: true });
      var inflight = null;
      runBtn.onclick = async function () {
        runBtn.disabled = true;
        runBtn.textContent = "Running…";
        cancelBtn.hidden = false;
        clear(runOut);
        runOut.appendChild(el("p", { class: "muted",
          text: "Running the frozen test against your app. This opens a headless browser " +
                "on this machine — nothing is uploaded." }));
        var controller = new AbortController();
        inflight = controller;
        try {
          var res = await adminApi("/session/" + trace.id + "/reproduce", {
            method: "POST",
            body: JSON.stringify({ runs: 1, timeout_seconds: 120 }),
            headers: { "Content-Type": "application/json" },
            signal: controller.signal
          });
          clear(runOut);
          runOut.appendChild(reproVerdict(res));
        } catch (e) {
          clear(runOut);
          runOut.appendChild(controller.signal.aborted
            ? el("p", { class: "muted", text: "Cancelled — no verdict was reached." })
            : fail(e));
        }
        inflight = null;
        cancelBtn.hidden = true;
        runBtn.disabled = false;
        runBtn.textContent = "Reproduce locally";
      };
      cancelBtn.onclick = function () { if (inflight) inflight.abort(); };
      actions.push(runBtn, cancelBtn);
    }
    wrap.appendChild(box("Deterministic Playwright reproduction", [
      el("div", { class: "row-actions" }, actions),
      el("pre", { text: code }),
      runOut,
      el("div", { class: "note", text: isLocal
        ? "Running it here uses a headless browser on this machine, against the app you " +
          "configured. Your CI runs the identical test to prove a fix."
        : "Text only. StepStitch never runs this — your CI does." })
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
    // Least privilege: this snippet is handed to CI, and CI gets the narrow
    // verify-scoped token (fetch the repro, post the verdict, nothing else) — never the
    // operator's admin bearer. The Agents tab issues it; the gate copy promises exactly
    // this ("no agent ever receives this credential").
    var snippet =
      "# StepStitch: report the repro outcome so the fix is provable.\n" +
      "# Run the generated test BEFORE the fix (expect fail) and AFTER (expect pass).\n" +
      "# STEPSTITCH_VERIFY_TOKEN is a verify-scoped token issued from the Agents tab —\n" +
      "# CI never needs the admin token.\n" +
      "curl -sS -X POST \\\n" +
      "  " + origin + API + "/session/" + trace.id + "/verify \\\n" +
      "  -H \"Authorization: Bearer $STEPSTITCH_VERIFY_TOKEN\" \\\n" +
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
  // The four answers a fix can get. Wording matches the CLI and the API exactly, so an
  // operator reading the console and an agent reading the packet see the same verdicts.
  var FIX_VERDICTS = {
    fixed: { label: "Fixed", tone: "ok",
      plain: "Measured failing before the change, passing after — same frozen test." },
    still_failing: { label: "Still failing", tone: "bad",
      plain: "The same failure, in the same way." },
    different_failure: { label: "Different failure", tone: "warn",
      plain: "It still fails, but not how it failed before — the change moved the problem." },
    unable_to_verify: { label: "Unable to verify", tone: "warn",
      plain: "No reliable answer. Not a fix." }
  };

  function fixVerdict(res) {
    if (res && res.status === "refused") {
      return el("div", {}, [
        el("span", { class: "pill warn", text: "Refused" }),
        el("p", { class: "muted", text: res.detail || "" })
      ]);
    }
    var meta = FIX_VERDICTS[res.verdict] || { label: res.verdict, tone: "warn", plain: "" };
    var kids = [
      el("div", { class: "row-actions" }, [
        el("span", { class: "pill " + meta.tone, text: meta.label })
      ]),
      el("p", {}, [document.createTextNode(meta.plain)]),
      el("p", { class: "muted", text: res.detail || "" })
    ];
    if (res.script_sha256) {
      kids.push(el("p", { class: "note",
        text: "judged by frozen test " + String(res.script_sha256).slice(0, 16) + "…" }));
    }
    return el("div", {}, kids);
  }

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

    // Hand-off controls. The commands are shown rather than run: connecting an agent
    // touches the developer's own machine and their agent's config, which is not
    // something a web page should do behind their back.
    var handoff = el("div", { class: "row-actions", style: "margin-bottom:14px" }, [
      copyBtn(function () { return "stepstitch connect claude"; }, "Open in Claude Code"),
      copyBtn(function () { return "stepstitch connect codex"; }, "Open in Codex"),
      copyBtn(function () {
        return "stepstitch reproduce " + trace.id;
      }, "Copy agent command")
    ]);
    if (lastStatus && lastStatus.local_mode) {
      var verifyBtn = el("button", { class: "ghost", text: "Verify fix" });
      var verifyOut = el("div", { style: "margin-top:10px" });
      verifyBtn.onclick = async function () {
        verifyBtn.disabled = true;
        verifyBtn.textContent = "Verifying…";
        clear(verifyOut);
        verifyOut.appendChild(el("p", { class: "muted",
          text: "Rerunning the frozen reproduction. StepStitch decides — the agent does " +
                "not get a vote." }));
        try {
          var res = await adminApi("/session/" + trace.id + "/verify-fix", {
            method: "POST", body: JSON.stringify({ runs: 1, timeout_seconds: 120 }),
            headers: { "Content-Type": "application/json" }
          });
          clear(verifyOut);
          verifyOut.appendChild(fixVerdict(res));
        } catch (e) {
          clear(verifyOut);
          verifyOut.appendChild(fail(e));
        }
        verifyBtn.disabled = false;
        verifyBtn.textContent = "Verify fix";
      };
      handoff.appendChild(verifyBtn);
      wrap.appendChild(handoff);
      wrap.appendChild(verifyOut);
    } else {
      wrap.appendChild(handoff);
    }
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
    // Wire shape = the host's ScrubConfig document, verbatim: extra_redactions is a
    // list of [label, regex] PAIRS, keys/testids/templates are string lists, the save
    // is a PUT. server/tests/test_dashboard_contract.py pins these tokens against the
    // pydantic model — the first version of this page invented its own shape
    // ({overrides:{patterns:[{label,regex}]}}, POSTed) and silently saved nothing.
    var pending = {
      extra_redactions: (cfg.extra_redactions || []).slice(),
      extra_forbidden_keys: (cfg.extra_forbidden_keys || []).slice(),
      approved_testids: (cfg.approved_testids || []).slice(),
      route_templates: (cfg.route_templates || []).slice()
    };

    // Scrub policy
    var label = el("input", { placeholder: "label (e.g. empid)", "aria-label": "pattern label" });
    var regex = el("input", { placeholder: "regex (e.g. EMP-\\d+)", "aria-label": "pattern regex" });
    var keyIn = el("input", { placeholder: "metadata key", "aria-label": "metadata key" });
    var listNode = el("div", {});

    function drawLists() {
      clear(listNode);
      listNode.appendChild(el("div", { class: "note", text: "Custom redaction patterns" }));
      listNode.appendChild(pending.extra_redactions.length
        ? el("div", { class: "chips" }, pending.extra_redactions.map(function (p) {
            return el("span", { class: "chip mono", text: (p[0] || "?") + " · " + (p[1] || "") });
          }))
        : el("div", { class: "muted", text: "None yet." }));
      listNode.appendChild(el("div", { class: "note", text: "Extra dropped metadata keys" }));
      listNode.appendChild(pending.extra_forbidden_keys.length
        ? el("div", { class: "chips" }, pending.extra_forbidden_keys.map(function (k) {
            return el("span", { class: "chip mono", text: k });
          }))
        : el("div", { class: "muted", text: "None yet." }));
    }
    drawLists();

    var addPat = el("button", { class: "ghost", text: "Add pattern", onclick: function () {
      if (!label.value.trim() || !regex.value.trim()) return;
      pending.extra_redactions.push([label.value.trim(), regex.value.trim()]);
      label.value = ""; regex.value = ""; drawLists();
    } });
    var addKey = el("button", { class: "ghost", text: "Add key", onclick: function () {
      if (!keyIn.value.trim()) return;
      pending.extra_forbidden_keys.push(keyIn.value.trim()); keyIn.value = ""; drawLists();
    } });

    var previewIn = el("textarea", { rows: 3, style: "width:100%",
      "aria-label": "text to preview", placeholder: "Paste sample text to see what would be redacted…" });
    var previewOut = el("pre", { text: "" });
    var previewBtn = el("button", { class: "ghost", text: "Preview redaction",
      onclick: async function () {
        try {
          var r = await adminApi("/scrub/preview", jsonPost({ text: previewIn.value,
            extra_redactions: pending.extra_redactions }));
          previewOut.textContent = r.redacted || "";
        } catch (e) { previewOut.textContent = e.message; }
      } });
    var saveBtn = el("button", { class: "primary", text: "Save scrub policy",
      onclick: async function () {
        try { await adminApi("/config/scrub", jsonPut(pending)); renderGovernance(); }
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

    // Strict allowlists — only meaningful when the base profile enforces the
    // strict schema (deny-by-default). The host says so explicitly; never inferred
    // from the profile name.
    if (cfg.strict_schema) {
      var testidIn = el("input", { placeholder: "data-testid (e.g. transfer-submit)",
        "aria-label": "approved testid" });
      var routeIn = el("input", { placeholder: "route template (e.g. /accounts/:id)",
        "aria-label": "route template" });
      var strictList = el("div", {});
      function drawStrict() {
        clear(strictList);
        strictList.appendChild(el("div", { class: "note", text: "Approved data-testid selectors" }));
        strictList.appendChild(pending.approved_testids.length
          ? el("div", { class: "chips" }, pending.approved_testids.map(function (t) {
              return el("span", { class: "chip mono", text: t });
            }))
          : el("div", { class: "muted",
              text: "None yet — every semantic selector is rejected until you approve specific testids." }));
        strictList.appendChild(el("div", { class: "note", text: "Approved route templates" }));
        strictList.appendChild(pending.route_templates.length
          ? el("div", { class: "chips" }, pending.route_templates.map(function (t) {
              return el("span", { class: "chip mono", text: t });
            }))
          : el("div", { class: "muted",
              text: "None yet — every route is rejected until you declare templates." }));
      }
      drawStrict();
      var addTestid = el("button", { class: "ghost", text: "Approve testid", onclick: function () {
        if (!testidIn.value.trim()) return;
        pending.approved_testids.push(testidIn.value.trim()); testidIn.value = ""; drawStrict();
      } });
      var addRoute = el("button", { class: "ghost", text: "Declare template", onclick: function () {
        if (!routeIn.value.trim()) return;
        pending.route_templates.push(routeIn.value.trim()); routeIn.value = ""; drawStrict();
      } });
      root.appendChild(box("Strict allowlists", [
        el("div", { class: "muted", text: "This profile is deny-by-default: only the static " +
          "data-testid values and route templates named here are accepted; everything else is " +
          "refused with a 422. The lists scope the checks — they can never disable them. " +
          "Saved together with the scrub policy above." }),
        el("div", { class: "row-actions", style: "margin-top:12px" }, [testidIn, addTestid]),
        el("div", { class: "row-actions" }, [routeIn, addRoute]),
        strictList
      ]));
    }

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

  // ---- URL state ------------------------------------------------------------------------
  // The console had no addressable state at all: a failure could not be linked to, and a
  // refresh dropped you back on Overview. Hash routing keeps that inside the page (no server
  // routes, nothing for the CSP to object to).
  var applyingHash = false;
  function setHash(next) {
    if (applyingHash || location.hash === next) return;
    applyingHash = true;
    location.hash = next;
    applyingHash = false;
  }
  function routeFromHash() {
    var raw = (location.hash || "").replace(/^#\/?/, "");
    var parts = raw.split("/").filter(Boolean);
    if (parts[0] === "shape" && parts[1]) {
      current = "board";
      renderNav();
      syncChrome();
      return openShape(decodeURIComponent(parts[1]), { fromHash: true });
    }
    var known = ROUTES.filter(function (r) { return r.id === parts[0]; })[0];
    go(known ? known.id : "overview", { fromHash: true });
  }

  // Unmissable and permanent. Someone who lands here from a link must not be able to
  // mistake this for their own data. The markup ships in the page and is only revealed
  // here, so it is on screen before any of this script runs.
  function showDemoBanner() {
    document.getElementById("demobartext").textContent = tech
      ? "Read-only. Six failure shapes generated by the real StepStitch pipeline "
        + "(scrubber, scorer, compiler, verdict rules). No real user data exists here, "
        + "and nothing on this page can be changed."
      : "Everything here is made up. It is a working copy of the real console, filled "
        + "with example failures so you can look around. Nothing can be changed.";
    document.getElementById("demobar").hidden = false;
  }

  // ---- boot -----------------------------------------------------------------------------
  renderNav();
  syncChrome();
  if (DEMO) {
    showDemoBanner();
    // There is no credential to disconnect from, and no agent token can be issued here.
    document.getElementById("tokenbtn").hidden = true;
  }
  if (token) {
    loadStatus();
    // Deep links: a failure has a URL, so it can be shared, bookmarked and reloaded.
    window.addEventListener("hashchange", routeFromHash);
    routeFromHash();
  } else { renderGate(); }
})();
</script>
</body>
</html>
"""
