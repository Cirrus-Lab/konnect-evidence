"""Static, accessible review dashboard (Dashboard Spec §3–§10).

`render()` writes one self-contained HTML file with the evidence store
embedded as JSON. It is a read-only decision and navigation surface: it
never mutates sources, never claims live telemetry, and shows non-mutating
CLI instructions instead of action buttons.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import gates
from .util import freshness, now_iso

TYPE_FRESHNESS = {"run": None, "bom_line": "lifecycle", "github_pr": "github", "manufacturing_package": "manufacturing_output"}


def _fresh(rec, policy):
    days = policy.get("freshness_days", {})
    if rec.get("type") == "run":
        key = rec.get("check", "")
        key = "simulation" if key == "simulation" else ("manufacturing_output" if key.startswith("export:") else key)
        return freshness(rec.get("timestamp"), days.get(key, days.get("default")))
    if rec.get("type") == "bom_line":
        return freshness(rec.get("lifecycle_date"), days.get("lifecycle"))
    if rec.get("type") == "artifact" and rec.get("tags"):
        return freshness(rec.get("timestamp") or rec.get("updated_at"), days.get("analysis"))
    k = TYPE_FRESHNESS.get(rec.get("type"))
    return freshness(rec.get("timestamp") or rec.get("updated_at"), days.get(k) if k else None)


def view_model(store, *, snapshot_manifest=None, diff=None) -> dict:
    policy = store.policy
    records = store.all_records()
    for rs in records.values():
        for r in rs:
            r["_freshness"] = _fresh(r, policy)
    ok, problems = store.audit.verify()
    events = store.audit.events()
    executed = any(r.get("executed") for r in records.get("run", []))
    verified_conn = [c["id"] for c in records.get("connector", []) if c.get("trust_tier") != "untrusted"]
    return {
        "identity": store.identity,
        "generated_at": now_iso(),
        "policy_version": policy.get("policy_version"),
        "freshness_days": policy.get("freshness_days"),
        "gates": gates.evaluate_all(store),
        "records": records,
        "audit": {"verified": ok, "problems": problems, "count": len(events), "events": events[-300:]},
        "mode": {
            "executed_runs": executed,
            "verified_integrations": verified_conn,
            "banner": " ".join([
                "Static snapshot; nothing on this page updates by itself.",
                ("Some runs were executed by edagov and carry provenance." if executed else
                 "Documentation-only: no run was executed by edagov; every check result is an ingested report."),
                (f"Connectors marked verified: {', '.join(verified_conn)}; all others are untrusted."
                 if verified_conn else "No integration is verified; no live synchronization is implied."),
            ]),
        },
        "snapshot": snapshot_manifest and {k: snapshot_manifest[k] for k in ("snapshot", "generated_at", "filters", "store_fingerprint", "caveats")},
        "diff": diff,
    }


def render(store, out_path, *, snapshot_manifest=None, diff=None, standalone: bool = True) -> Path:
    vm = view_model(store, snapshot_manifest=snapshot_manifest, diff=diff)
    data = json.dumps(vm, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = TEMPLATE.replace("/*__EDAGOV_DATA__*/null", data)
    if standalone:
        html = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
                + html.replace("<!--BODY-->", "</head>\n<body>", 1) + "\n</body>\n</html>\n")
    else:
        html = html.replace("<!--BODY-->", "", 1)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


TEMPLATE = r"""<title>EDA Evidence Console</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Layout: sticky identity bar + gate rail, then one screen at a time (A–G) in a 1280px column; detail drawer on the right. */
:root{
  --bg:#eef1f3; --surface:#ffffff; --sunk:#e3e8ec; --ink:#15202b; --muted:#56626e; --line:#cfd6dc;
  --accent:#9c4c17; --accent-ink:#ffffff;
  --s-block:#b42318; --s-block-bg:#fde8e6; --s-warn:#8a5000; --s-warn-bg:#fdf0d8;
  --s-ready:#1b5a9e; --s-ready-bg:#e2edf9; --s-ok:#1c6e37; --s-ok-bg:#e1f3e6; --s-none:#56626e; --s-none-bg:#e8ecef;
  --s-exc:#6b3fa0; --s-exc-bg:#efe6f8;
  --f-display:"Archivo","Arial Narrow",system-ui,sans-serif;
  --f-body:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  --f-mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
  --r:6px;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0e141a; --surface:#16202a; --sunk:#1d2834; --ink:#e4eaef; --muted:#9aa7b3; --line:#2b3744;
  --accent:#e08a4f; --accent-ink:#1a0e05;
  --s-block:#ff8a7e; --s-block-bg:#3a1a18; --s-warn:#f3bb5a; --s-warn-bg:#36290f; --s-ready:#82b3ef; --s-ready-bg:#14283f;
  --s-ok:#6fd08f; --s-ok-bg:#13301d; --s-none:#9aa7b3; --s-none-bg:#222d38; --s-exc:#c6a2f0; --s-exc-bg:#2a1f3a; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e141a; --surface:#16202a; --sunk:#1d2834; --ink:#e4eaef; --muted:#9aa7b3; --line:#2b3744;
  --accent:#e08a4f; --accent-ink:#1a0e05;
  --s-block:#ff8a7e; --s-block-bg:#3a1a18; --s-warn:#f3bb5a; --s-warn-bg:#36290f; --s-ready:#82b3ef; --s-ready-bg:#14283f;
  --s-ok:#6fd08f; --s-ok-bg:#13301d; --s-none:#9aa7b3; --s-none-bg:#222d38; --s-exc:#c6a2f0; --s-exc-bg:#2a1f3a; color-scheme:dark}
*{box-sizing:border-box} [hidden]{display:none!important}
body{background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-body);margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--surface)}
.wrap{max-width:1280px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
a{color:var(--accent)} :focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:3px}
.mono{font-family:var(--f-mono);font-size:.82em;overflow-wrap:anywhere}
button.mono,.tablewrap .mono{white-space:nowrap;overflow-wrap:normal}
.muted{color:var(--muted)} .small{font-size:.85rem}
h1,h2,h3{font-family:var(--f-display);font-stretch:85%;text-wrap:balance;margin:0;letter-spacing:.005em}
h1{font-size:1.35rem;font-weight:750} h2{font-size:1.15rem;font-weight:700} h3{font-size:1rem;font-weight:650}
.eyebrow{font:600 .7rem/1 var(--f-body);letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
header.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--surface);border-bottom:1px solid var(--line)}
.idbar{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:center;padding-block:12px 8px}
.idbar .ident{display:flex;flex-wrap:wrap;gap:4px 18px;align-items:baseline}
.kv{display:flex;flex-direction:column;gap:2px;min-width:0}
.kv b{font:600 .95rem var(--f-mono)}
.banner{border:1px dashed var(--accent);color:var(--ink);background:var(--sunk);border-radius:var(--r);padding:6px 10px;font-size:.85rem;display:flex;gap:8px;align-items:flex-start}
.banner strong{color:var(--accent)}
nav[role=tablist]{display:flex;gap:2px;overflow-x:auto;scrollbar-width:thin}
nav[role=tablist] button{font:600 .9rem var(--f-body);border:0;background:none;color:var(--muted);padding:10px 12px;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap}
nav[role=tablist] button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--accent)}
nav[role=tablist] button .k{font-family:var(--f-mono);font-size:.75rem;color:var(--accent);margin-right:4px}
main{padding-block:20px 48px;display:grid;gap:20px}
section.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px;min-width:0}
.ph{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;align-items:baseline;margin-bottom:12px}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))}
.badge{display:inline-flex;align-items:center;gap:6px;font:600 .78rem/1.2 var(--f-body);padding:3px 8px 3px 6px;border-radius:999px;border:1.5px solid currentColor;cursor:pointer;background:var(--s-none-bg);color:var(--s-none);white-space:nowrap}
.badge .g{font-family:var(--f-mono);font-size:.8rem;line-height:1}
.badge[data-tone=block]{color:var(--s-block);background:var(--s-block-bg);border-radius:3px}
.badge[data-tone=warn]{color:var(--s-warn);background:var(--s-warn-bg);border-style:dashed}
.badge[data-tone=ready]{color:var(--s-ready);background:var(--s-ready-bg)}
.badge[data-tone=ok]{color:var(--s-ok);background:var(--s-ok-bg)}
.badge[data-tone=exc]{color:var(--s-exc);background:var(--s-exc-bg);border-style:double;border-width:3px}
.badge[data-tone=none]{border-style:dotted}
span.badge{cursor:default}
.rail{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,138px),1fr));gap:0;list-style:none;margin:0;padding:0;counter-reset:g}
.rail li{counter-increment:g;padding:10px 10px 12px;border-left:1px solid var(--line);display:grid;gap:6px;align-content:start;position:relative}
.rail li:first-child{border-left:0}
.rail.steps li::before{content:"Step " counter(g)}
.rail li::before{content:"G" counter(g);font:600 .7rem var(--f-mono);color:var(--muted)}
.rail li[data-tone=block]{box-shadow:inset 0 -3px 0 var(--s-block)} .rail li[data-tone=ok]{box-shadow:inset 0 -3px 0 var(--s-ok)}
.rail li[data-tone=ready]{box-shadow:inset 0 -3px 0 var(--s-ready)} .rail li[data-tone=warn]{box-shadow:inset 0 -3px 0 var(--s-warn)}
.rail li[data-tone=exc]{box-shadow:inset 0 -3px 0 var(--s-exc)}
.rail .nm{font:650 .9rem var(--f-display);font-stretch:85%}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:12px}
.tile{border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;display:grid;gap:4px;background:var(--surface);text-align:left;font:inherit;color:inherit;cursor:pointer}
.tile .n{font:700 1.6rem/1 var(--f-display);font-variant-numeric:tabular-nums}
.tile[data-tone=block] .n{color:var(--s-block)} .tile[data-tone=warn] .n{color:var(--s-warn)} .tile[data-tone=ok] .n{color:var(--s-ok)}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font:600 .72rem var(--f-body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);background:var(--sunk);position:sticky;top:0}
td.num{font-variant-numeric:tabular-nums;text-align:right}
tr.hl td{background:var(--s-ready-bg)}
tr:last-child td{border-bottom:0}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:end}
.filters label{display:grid;gap:2px;font-size:.75rem;color:var(--muted)}
.filters select,.filters input{font:inherit;font-size:.88rem;padding:5px 8px;border:1px solid var(--line);border-radius:4px;background:var(--surface);color:var(--ink);min-width:0}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:.78rem;border:1px solid var(--line);border-radius:999px;padding:2px 8px;background:var(--sunk)}
.chip button{border:0;background:none;color:var(--muted);cursor:pointer;padding:0 0 0 4px;font:inherit}
.btn{font:600 .85rem var(--f-body);border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:5px 10px;cursor:pointer}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
pre.explain{font:.78rem/1.55 var(--f-mono);background:var(--sunk);padding:10px 12px;border-radius:4px;overflow-x:auto;white-space:pre-wrap;margin:0}
.cmd{display:flex;gap:6px;align-items:stretch}
.cmd code{flex:1;min-width:0;font:.78rem var(--f-mono);background:var(--sunk);padding:6px 8px;border-radius:4px;overflow-x:auto;white-space:nowrap}
ul.plain{margin:0;padding-left:18px} ul.plain li{margin:2px 0}
.ev{display:grid;gap:8px;border:1px solid var(--line);border-radius:var(--r);padding:12px;min-width:0}
.ev dl{display:grid;grid-template-columns:minmax(90px,max-content) 1fr;gap:3px 12px;margin:0;font-size:.85rem}
.ev dt{color:var(--muted)} .ev dd{margin:0;min-width:0}
.bar{height:8px;background:var(--sunk);border-radius:4px;overflow:hidden;min-width:60px}
.bar i{display:block;height:100%;background:var(--accent)}
aside#drawer{position:fixed;top:0;right:0;bottom:0;width:min(460px,100%);background:var(--surface);border-left:1px solid var(--line);box-shadow:-12px 0 32px rgb(0 0 0 / .18);z-index:20;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px);padding-right:env(safe-area-inset-right,0px)}
#drawer .dh{display:flex;justify-content:space-between;gap:8px;padding:14px 16px;border-bottom:1px solid var(--line);align-items:center}
#drawer .db{padding:16px;overflow:auto;display:grid;gap:12px;align-content:start}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.empty{padding:14px;border:1px dashed var(--line);border-radius:var(--r);color:var(--muted);font-size:.9rem}
.legend{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
@media (max-width:640px){header.top{position:static} .idbar h1{width:100%}}
@media (prefers-reduced-motion:no-preference){aside#drawer{animation:slide .16s ease-out}@keyframes slide{from{transform:translateX(24px);opacity:.6}}}
</style>
<!--BODY-->
<header class="top">
  <div class="wrap">
    <div class="idbar" id="idbar"></div>
    <div class="banner" id="banner" role="note"></div>
    <nav role="tablist" aria-label="Dashboard screens" id="tabs"></nav>
  </div>
</header>
<div class="wrap"><main id="main" tabindex="-1"></main></div>
<aside id="drawer" hidden aria-labelledby="drawer-title" role="dialog" aria-modal="false">
  <div class="dh"><h2 id="drawer-title">Details</h2><button class="btn" id="drawer-close" aria-label="Close details">Close</button></div>
  <div class="db" id="drawer-body"></div>
</aside>
<div class="sr" role="status" aria-live="polite" id="live"></div>
<script id="edagov-data" type="application/json">/*__EDAGOV_DATA__*/null</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById("edagov-data").textContent);
var R = D.records || {};
function list(t){return (R[t]||[]).slice();}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function short(h){if(!h)return "—";var s=String(h);var i=s.indexOf(":");return i>0? s.slice(0,i+1)+s.slice(i+1,i+13):s.slice(0,16);}
function when(t){if(!t)return "—";return String(t).replace("T"," ").replace("Z"," UTC");}
var TONE = {
  approved:"ok", clean:"ok", synced:"ok", success:"ok", complete:"ok", current:"ok", executed:"ok", pass:"ok", verified:"ok", closed:"ok", approve:"ok", production_approved:"ok",
  approved_with_exception:"exc", accepted:"exc", engineering_approved:"exc",
  ready_for_review:"ready", in_progress:"ready", proposed:"ready", converged_with_warnings:"warn", candidate:"ready", open:"warn", contained:"warn", comment:"ready",
  blocked:"block", rejected:"block", violations:"block", failed:"block", tool_error:"block", conflict:"block", invalid:"block", unauthorized:"block", dead_lettered:"block",
  unavailable:"block", timeout:"block", fail:"block", incomplete:"block", requested_changes:"block", request_changes:"block", disallowed:"block", critical:"block", high:"block", blocking:"block",
  stale:"warn", partial:"warn", altered_settings:"warn", "future-dated":"warn", unknown:"warn", "queued/retrying":"warn", warning:"warn", medium:"warn", attention:"warn", stale_dismissed:"warn", missing:"warn",
  not_started:"none", not_applicable:"none", not_checked:"none", empty:"none", not_configured:"none", superseded:"none", low:"none", info:"none", loading:"none", pending:"none"
};
var GLYPH = {ok:"✓", exc:"◆", ready:"●", warn:"▲", block:"■", none:"○"};
var TONE_WORD = {ok:"complete", exc:"accepted with exception", ready:"needs action", warn:"attention", block:"blocking", none:"not started or not applicable"};
function uniq(a){var s={};return a.filter(function(x){if(s[x])return false;s[x]=1;return true;});}
function tone(s){return TONE[s]||"none";}
var REG = []; // records reachable from badges for the detail drawer
function reg(rec){REG.push(rec);return REG.length-1;}
function badge(state, rec, label){
  var t=tone(state); var txt=label||String(state||"unknown").replace(/_/g," ");
  if(!rec) return '<span class="badge" data-tone="'+t+'"><span class="g" aria-hidden="true">'+GLYPH[t]+'</span>'+esc(txt)+'</span>';
  return '<button type="button" class="badge" data-tone="'+t+'" data-rec="'+reg(rec)+'" aria-label="'+esc(txt)+' ('+TONE_WORD[t]+'). Open details"><span class="g" aria-hidden="true">'+GLYPH[t]+'</span>'+esc(txt)+'</button>';
}
function idlink(id){ if(!id) return "—"; var r=findId(id); return r? '<button type="button" class="btn mono" style="padding:1px 6px" data-rec="'+reg(r)+'">'+esc(id)+'</button>' : '<span class="mono">'+esc(id)+'</span>'; }
var BYID={}; Object.keys(R).forEach(function(t){R[t].forEach(function(r){BYID[r.id]=r;});});
(D.gates||[]).forEach(function(g){BYID["GATE:"+g.gate]=Object.assign({type:"gate_eval",id:"GATE:"+g.gate},g);});
function findId(id){return BYID[id];}
function cmd(c){return '<div class="cmd"><code>'+esc(c)+'</code><button type="button" class="btn" data-copy="'+esc(c)+'">Copy</button></div>';}
function table(cols, rows, opt){
  opt=opt||{};
  if(!rows.length) return '<div class="empty">'+esc(opt.empty||"No records.")+'</div>';
  var h='<div class="tablewrap"><table><caption class="sr">'+esc(opt.caption||"")+'</caption><thead><tr>'+cols.map(function(c){return '<th scope="col">'+esc(c[0])+'</th>';}).join("")+'</tr></thead><tbody>';
  rows.forEach(function(r){h+='<tr'+(opt.hl&&opt.hl(r)?' class="hl"':'')+'>'+cols.map(function(c){return '<td'+(c[2]?' class="'+c[2]+'"':'')+'>'+c[1](r)+'</td>';}).join("")+'</tr>';});
  return h+'</tbody></table></div>';
}
var GATE_NAMES={requirements:"Requirements",architecture:"Architecture",schematic_library:"Schematic & library",simulation:"Simulation",pcb:"PCB integrity",supply:"Supply",release:"Release",change:"Change"};

/* ---------- filters (preserved across screens) ---------- */
var F={q:"",owner:"",severity:"",fresh:""};
function owners(){var s={};Object.keys(R).forEach(function(t){R[t].forEach(function(r){if(r.owner)s[r.owner]=1;});});return Object.keys(s).sort();}
function pass(r){
  if(F.owner && r.owner!==F.owner) return false;
  if(F.severity && r.severity!==F.severity) return false;
  if(F.fresh && r._freshness!==F.fresh) return false;
  if(F.q){var s=JSON.stringify([r.id,r.title,r.text,r.mpn,r.check,r.name,r.filename,r.provider]).toLowerCase(); if(s.indexOf(F.q.toLowerCase())<0) return false;}
  return true;
}
function filterBar(){
  var o=owners().map(function(x){return '<option'+(F.owner===x?' selected':'')+'>'+esc(x)+'</option>';}).join("");
  function sel(id,label,vals,cur){return '<label for="'+id+'">'+label+'<select id="'+id+'"><option value="">Any</option>'+vals.map(function(v){return '<option'+(cur===v?' selected':'')+'>'+v+'</option>';}).join("")+'</select></label>';}
  var chips=Object.keys(F).filter(function(k){return F[k];}).map(function(k){return '<span class="chip">'+k+': '+esc(F[k])+'<button type="button" data-clear="'+k+'" aria-label="Remove filter '+k+'">×</button></span>';}).join("");
  return '<div class="filters" role="search"><label for="f-q">Search<input id="f-q" type="search" value="'+esc(F.q)+'" placeholder="ID, MPN, title…"></label>'+
    '<label for="f-owner">Owner<select id="f-owner"><option value="">Any</option>'+o+'</select></label>'+
    sel("f-severity","Severity",["blocking","warning","attention","info","approved"],F.severity)+
    sel("f-fresh","Freshness",["current","stale","future-dated","unknown","missing"],F.fresh)+
    '</div>'+(chips?'<div class="chips" style="margin-top:8px">'+chips+'</div>':'');
}

/* ---------- shell ---------- */
var I=D.identity||{};
function shell(){
  var rs = I.release_state||"unknown";
  document.getElementById("idbar").innerHTML =
    '<h1>'+esc(I.product_id||"Product")+' · '+esc(I.board_id||"")+'</h1><div class="ident">'+
    kv("Design",I.design_id)+kv("Revision",I.revision)+kv("Variant",I.variant)+kv("Assembly",I.assembly_id)+
    '<div class="kv"><span class="eyebrow">Release state</span>'+badge(rs==="released"?"approved":"in_progress",null,rs.replace(/_/g," "))+'</div>'+
    kv("Generated",when(D.generated_at))+'</div>';
  document.getElementById("banner").innerHTML='<strong aria-hidden="true">!</strong><span>'+esc(D.mode.banner)+' Policy '+esc(D.policy_version)+'. '+
    (D.audit.verified?'Audit chain verified ('+D.audit.count+' events).':'<strong>Audit chain verification failed.</strong>')+'</span>';
}
function kv(k,v){return '<div class="kv"><span class="eyebrow">'+esc(k)+'</span><b>'+esc(v||"—")+'</b></div>';}
var SCREENS=[["overview","A","Overview"],["requirements","B","Requirements"],["evidence","C","Design evidence"],["bom","D","BOM & supply"],["release","E","Manufacturing release"],["review","F","Review"],["admin","G","Connectors & audit"]];
function tabs(cur){
  document.getElementById("tabs").innerHTML=SCREENS.map(function(s){return '<button role="tab" id="tab-'+s[0]+'" aria-controls="main" aria-selected="'+(s[0]===cur)+'" tabindex="'+(s[0]===cur?0:-1)+'" data-screen="'+s[0]+'"><span class="k">'+s[1]+'</span>'+s[2]+'</button>';}).join("");
}

/* ---------- Screen A ---------- */
function gateRail(){
  return '<ol class="rail" aria-label="Release gates in order">'+(D.gates||[]).map(function(g){
    var t=tone(g.state);
    return '<li data-tone="'+t+'"><span class="nm">'+esc(GATE_NAMES[g.gate]||g.gate)+'</span>'+badge(g.state,BYID["GATE:"+g.gate])+
      (g.approval_note?'<span class="small muted">approval stale</span>':'')+'</li>';}).join("")+'</ol>';
}
function screenOverview(){
  var issues=list("issue").filter(function(i){return (i.state==="open"||i.state==="contained");});
  var crit=issues.filter(function(i){return i.severity==="critical"||i.severity==="high";});
  var allRecs=[];Object.keys(R).forEach(function(t){allRecs=allRecs.concat(R[t]);});
  var stale=allRecs.filter(function(r){return r._freshness==="stale"||r._freshness==="future-dated";});
  var missing=[];(D.gates||[]).forEach(function(g){(g.missing_evidence||[]).forEach(function(m){missing.push({gate:g.gate,item:m});});});
  var blocked=(D.gates||[]).filter(function(g){return g.state==="blocked"||g.state==="rejected";});
  var ready=(D.gates||[]).filter(function(g){return g.state==="ready_for_review";});
  var html='<section class="panel" aria-labelledby="h-gates"><div class="ph"><h2 id="h-gates">Gate status</h2><span class="small muted">Automation can set at most “ready for review”. Approval needs a named reviewer bound to the evidence.</span></div>'+gateRail()+'</section>';
  html+='<section class="panel" aria-labelledby="h-sum"><div class="ph"><h2 id="h-sum">What needs attention</h2></div><div class="tiles">'+
    tile(blocked.length,"Blocked gates",blocked.length?"block":"ok","review")+
    tile(crit.length,"Open high/critical issues",crit.length?"block":"ok","review")+
    tile(missing.length,"Missing evidence items",missing.length?"warn":"ok","evidence")+
    tile(stale.length,"Stale or future-dated records",stale.length?"warn":"ok","evidence")+
    tile(ready.length,"Gates awaiting review",ready.length?"ready":"ok","review")+'</div></section>';
  html+='<div class="grid">';
  html+='<section class="panel" aria-labelledby="h-block"><h2 id="h-block">Blocking reasons</h2>'+
    (blocked.length? '<ul class="plain">'+blocked.map(function(g){return '<li><b>'+esc(GATE_NAMES[g.gate])+'</b>: '+esc(uniq(g.blocking||[]).slice(0,4).join("; ")||g.next_action)+'</li>';}).join("")+'</ul>' : '<p class="muted">No gate is blocked.</p>')+'</section>';
  html+='<section class="panel" aria-labelledby="h-next"><h2 id="h-next">Next actions</h2><ul class="plain">'+(D.gates||[]).filter(function(g){return g.next_action&&g.state!=="approved";}).map(function(g){return '<li><b>'+esc(GATE_NAMES[g.gate])+'</b>: '+esc(g.next_action)+'</li>';}).join("")+'</ul></section>';
  html+='</div>';
  html+='<section class="panel" aria-labelledby="h-miss"><div class="ph"><h2 id="h-miss">Missing evidence</h2></div>'+table([["Gate",function(r){return esc(GATE_NAMES[r.gate]);}],["Missing",function(r){return esc(r.item);}]],missing,{caption:"Missing evidence by gate",empty:"No evidence is missing for configured gate checks."})+'</section>';
  html+=legend();
  return html;
}
function tile(n,label,t,go){return '<button type="button" class="tile" data-tone="'+t+'" data-go="'+go+'"><span class="n">'+n+'</span><span class="small">'+esc(label)+'</span></button>';}
function legend(){return '<section class="panel" aria-labelledby="h-leg"><h2 id="h-leg" class="sr">Status legend</h2><div class="legend"><span class="eyebrow">Legend</span>'+
  ["approved","approved_with_exception","ready_for_review","stale","blocked","not_started"].map(function(s){return badge(s);}).join("")+
  '<span class="small muted">Shape and glyph carry the state as well as color. “Not started”, “not applicable”, “missing” and “passed” are never merged.</span></div></section>';}

/* ---------- Screen B ---------- */
var TRACE=null;
function links(r){var out=[];["allocated_requirements","evidence_links","affected","linked_evidence","affected_claims","evidence","exceptions","closure_evidence"].forEach(function(k){(r[k]||[]).forEach(function(x){if(typeof x==="string")out.push(x);});});if(r.retry_of)out.push(r.retry_of);return out;}
function traceSet(id){
  var set={};set[id]=1;
  for(var pass=0;pass<2;pass++){Object.keys(BYID).forEach(function(k){var r=BYID[k];var l=links(r);if(set[r.id]){l.forEach(function(x){set[x]=1;});}else if(l.some(function(x){return set[x];})){set[r.id]=1;}});}
  return set;
}
function screenRequirements(){
  var reqs=list("requirement").filter(pass), blocks=list("architecture_block").filter(pass);
  var methods={};list("requirement").forEach(function(r){var m=r.verification_method||"unspecified";methods[m]=methods[m]||{n:0,v:0};methods[m].n++;if(r.status==="verified")methods[m].v++;});
  var ts=TRACE?traceSet(TRACE):null;
  var h='<section class="panel">'+filterBar()+'</section>';
  h+='<section class="panel" aria-labelledby="h-cov"><div class="ph"><h2 id="h-cov">Coverage by verification method</h2><span class="small muted">Table is the chart’s text alternative.</span></div>'+
    table([["Method",function(r){return esc(r.m);}],["Requirements",function(r){return r.n;},"num"],["Verified",function(r){return r.v;},"num"],["Share verified",function(r){var p=r.n?Math.round(100*r.v/r.n):0;return '<div style="display:flex;gap:8px;align-items:center"><div class="bar" aria-hidden="true" style="flex:1"><i style="width:'+p+'%"></i></div><span class="mono">'+p+'%</span></div>';}]],
      Object.keys(methods).sort().map(function(m){return {m:m,n:methods[m].n,v:methods[m].v};}),{caption:"Requirement coverage"})+'</section>';
  h+='<section class="panel" aria-labelledby="h-req"><div class="ph"><h2 id="h-req">Requirements</h2>'+(TRACE?'<span>Tracing <span class="mono">'+esc(TRACE)+'</span> <button type="button" class="btn" data-trace="">Clear trace</button></span>':'<span class="small muted">Select Trace to highlight linked blocks, runs, issues and approvals.</span>')+'</div>'+
    table([["ID",function(r){return idlink(r.id);}],["Requirement",function(r){return esc(r.text);}],["Method",function(r){return esc(r.verification_method);}],["Acceptance",function(r){return esc(r.acceptance);}],["Owner",function(r){return esc(r.owner);}],["Status",function(r){return badge(r.status==="verified"?"approved":r.status==="unmet"?"blocked":r.status==="at_risk"?"stale":"in_progress",r,r.status);}],["",function(r){return '<button type="button" class="btn" data-trace="'+esc(r.id)+'">Trace</button>';}]],
      reqs,{caption:"Requirements",empty:"No requirement records match.",hl:function(r){return ts&&ts[r.id];}})+'</section>';
  h+='<section class="panel" aria-labelledby="h-blk"><h2 id="h-blk" style="margin-bottom:12px">Architecture blocks</h2>'+
    table([["ID",function(r){return idlink(r.id);}],["Block",function(r){return esc(r.name);}],["Purpose",function(r){return esc(r.purpose);}],["Interfaces",function(r){return esc((r.interfaces||[]).join(", "));}],["Allocated",function(r){return (r.allocated_requirements||[]).map(idlink).join(" ");}],["Owner",function(r){return esc(r.owner);}]],
      blocks,{caption:"Architecture blocks",empty:"No architecture blocks recorded.",hl:function(r){return ts&&ts[r.id];}})+'</section>';
  if(ts){var linked=Object.keys(ts).filter(function(k){return k!==TRACE&&BYID[k];}).map(function(k){return BYID[k];});
    h+='<section class="panel" aria-labelledby="h-tr"><h2 id="h-tr" style="margin-bottom:12px">Trace path for '+esc(TRACE)+'</h2>'+table([["Type",function(r){return esc(r.type);}],["ID",function(r){return idlink(r.id);}],["State",function(r){return badge(r.state,r);}]],linked,{empty:"Nothing links to this requirement yet."})+'</section>';}
  var dec=list("decision").concat(list("assumption"));
  h+='<section class="panel" aria-labelledby="h-dec"><h2 id="h-dec" style="margin-bottom:12px">Decisions and assumptions</h2>'+table([["ID",function(r){return idlink(r.id);}],["Record",function(r){return esc(r.title||r.text);}],["Owner / review",function(r){return esc(r.owner||"")+(r.review_condition?' · until: '+esc(r.review_condition):'');}]],dec,{empty:"None recorded."})+'</section>';
  return h;
}

/* ---------- Screen C ---------- */
function runCard(r){
  if(!r) return '';
  var ins=(r.inputs||[]);
  return '<div class="ev"><div class="ph" style="margin:0"><h3>'+esc((r.check||"").toUpperCase())+' · '+idlink(r.id)+'</h3>'+badge(r.result_class,r)+'</div><dl>'+
    '<dt>Tool</dt><dd class="mono">'+esc(r.tool)+' '+esc(r.tool_version)+'</dd>'+
    '<dt>Executed</dt><dd>'+(r.executed?badge("executed",null,"executed by edagov"):badge("not_checked",null,"ingested, not executed"))+'</dd>'+
    '<dt>Inputs</dt><dd>'+(ins.length?ins.length+' file(s) · <span class="mono">'+esc(short(ins[0].hash))+'</span>…':'<span style="color:var(--s-warn)">not bound to input hashes</span>')+'</dd>'+
    '<dt>Source rev.</dt><dd class="mono">'+esc(short(r.source_revision))+'</dd>'+
    (r.counts?'<dt>Counts</dt><dd>'+esc(r.counts.active)+' active ('+esc(r.counts.error)+' err, '+esc(r.counts.warning)+' warn) · '+esc(r.counts.excluded)+' excluded</dd>':'')+
    '<dt>Freshness</dt><dd>'+badge(r._freshness)+' '+esc(when(r.timestamp))+'</dd>'+
    '<dt>Reviewer</dt><dd>'+esc(r.reviewer||"none yet")+'</dd></dl>'+
    '<details><summary class="small">Claim scope and limitations</summary><p class="small">'+esc(r.claim_scope)+'</p><ul class="plain small">'+(r.limitations||[]).map(function(l){return '<li>'+esc(l)+'</li>';}).join("")+'</ul></details></div>';
}
function latest(check){var rs=list("run").filter(function(r){return r.check===check&&!r.superseded;});rs.sort(function(a,b){return (a.timestamp||"")<(b.timestamp||"")?-1:1;});return rs[rs.length-1];}
function screenEvidence(){
  var h='<section class="panel">'+filterBar()+'</section>';
  var inv=list("artifact").filter(function(a){return a.report_kind==="inventory";}).pop();
  h+='<section class="panel" aria-labelledby="h-sl"><div class="ph"><h2 id="h-sl">Schematic and library</h2><span class="small muted">ERC is a consistency check, not functional proof.</span></div><div class="grid">'+
    (latest("erc")?runCard(latest("erc")):'<div class="empty">No ERC evidence for this revision.'+cmd('edagov run erc --project . --authorize "reason"')+'</div>')+
    (inv?'<div class="ev"><div class="ph" style="margin:0"><h3>Project inventory · '+idlink(inv.id)+'</h3>'+badge(inv.complete?"ready_for_review":"blocked",inv,inv.complete?"complete":"incomplete")+'</div><dl>'+
      '<dt>KiCad files</dt><dd class="mono">'+esc((inv.kicad_generator_versions||[]).join(", ")||"—")+'</dd><dt>Sheets</dt><dd>'+esc(inv.sheet_count)+'</dd><dt>Symbols</dt><dd>'+esc(inv.symbol_count)+'</dd>'+
      '<dt>Library pin</dt><dd>'+esc(inv.library_release_pinned||"not pinned")+'</dd></dl><ul class="plain small">'+(inv.findings||[]).slice(0,8).map(function(f){return '<li>'+badge(f.severity)+' '+esc(f.message)+'</li>';}).join("")+'</ul></div>':'<div class="empty">No inventory recorded.'+cmd("edagov inventory --project .")+'</div>')+
    '</div></section>';
  var sims=list("run").filter(function(r){return r.check==="simulation";}).filter(pass);
  h+='<section class="panel" aria-labelledby="h-sim"><div class="ph"><h2 id="h-sim">Simulation</h2><span class="small muted">Convergence is numerical, not physical validation. Failed runs stay on record.</span></div>'+
    table([["Run",function(r){return idlink(r.id);}],["Class",function(r){return badge(r.result_class,r);}],["Simulator",function(r){return '<span class="mono">'+esc(r.tool_version)+'</span>';}],["Analyses",function(r){return esc(((r.manifest||{}).analyses||[]).map(function(a){return a.type;}).join(", "));}],["Netlist hash",function(r){return '<span class="mono">'+esc(short((r.manifest||{}).hash))+'</span>';}],["Retry of",function(r){return r.retry_of?idlink(r.retry_of):"—";}],["Validation",function(r){return r.validation?esc(r.validation):'<span style="color:var(--s-warn)">none</span>';}],["Freshness",function(r){return badge(r._freshness);}]],
      sims,{caption:"Simulation runs",empty:"No simulation runs recorded."})+'</section>';
  var tags=["stackup","pi_analysis","si_analysis","thermal_analysis","emc_plan"];
  h+='<section class="panel" aria-labelledby="h-pcb"><div class="ph"><h2 id="h-pcb">PCB integrity</h2><span class="small muted">DRC and a 3D view are not functional or manufacturing proof.</span></div><div class="grid">'+
    (latest("drc")?runCard(latest("drc")):'<div class="empty">No DRC evidence for this revision.'+cmd('edagov run drc --project . --authorize "reason"')+'</div>')+
    '<div class="ev"><h3>Analysis evidence</h3>'+table([["Topic",function(r){return esc(r.t.replace(/_/g," "));}],["Evidence",function(r){return r.items.length?r.items.map(function(a){return idlink(a.id);}).join(" "):'<span class="muted">missing</span>';}],["State",function(r){var a=r.items[r.items.length-1];return a?badge(a.reviewer?(a._freshness==="current"?"approved":"stale"):"ready_for_review",a,a.reviewer?(a._freshness==="current"?"reviewed":"stale"):"unreviewed"):badge("missing");}]],
      tags.map(function(t){return {t:t,items:list("artifact").concat(list("run")).filter(function(a){return (a.tags||[]).indexOf(t)>=0;})};}),{caption:"PCB analysis evidence"})+'</div></div></section>';
  return h;
}

/* ---------- Screen D ---------- */
function screenBom(){
  var lines=list("bom_line").filter(pass);
  var by={blocking:0,warning:0,attention:0,info:0};list("bom_line").forEach(function(l){by[l.severity]=(by[l.severity]||0)+1;});
  var h='<section class="panel">'+filterBar()+'</section>';
  h+='<section class="panel" aria-labelledby="h-bs"><div class="ph"><h2 id="h-bs">Supply risk</h2><span class="small muted">Authorized distribution reduces risk; it does not prove authenticity.</span></div><div class="tiles">'+
    tile(by.blocking||0,"Blocking lines",by.blocking?"block":"ok","bom")+tile(by.warning||0,"Lines with warnings",by.warning?"warn":"ok","bom")+tile(list("bom_line").filter(function(l){return l.alternate_state||l.alternate_state_claimed;}).length,"Alternates","ready","bom")+'</div></section>';
  h+='<section class="panel" aria-labelledby="h-bl"><h2 id="h-bl" style="margin-bottom:12px">BOM lines</h2>'+table([
    ["Line",function(r){return idlink(r.id);}],["Refs",function(r){return '<span class="mono">'+esc((r.references||[]).join(" "))+'</span>';}],["Qty",function(r){return esc(r.quantity);},"num"],
    ["Manufacturer · MPN",function(r){return esc(r.manufacturer)+' · <span class="mono">'+esc(r.mpn||"—")+'</span>';}],
    ["Lifecycle",function(r){return esc(r.lifecycle)+'<br><span class="small muted">'+esc(r.lifecycle_source||"no source")+' · '+esc(r.lifecycle_date||"no date")+'</span>';}],
    ["Evidence age",function(r){return badge(r._freshness);}],["Source",function(r){return esc(r.approved_source||"—");}],
    ["Alternate",function(r){return r.alternate_state?badge(r.alternate_state,r):(r.alternate_state_claimed?badge("blocked",r,"claimed "+r.alternate_state_claimed+", unsupported"):"—");}],
    ["Findings",function(r){return (r.findings||[]).length?'<ul class="plain small">'+r.findings.slice(0,3).map(function(f){return '<li>'+badge(f.severity)+' '+esc(f.message)+'</li>';}).join("")+'</ul>':badge("ready_for_review",null,"no findings");}]
  ],lines,{caption:"BOM lines",empty:"No BOM lines recorded for this revision."})+'</section>';
  return h;
}

/* ---------- Screen E ---------- */
function screenRelease(){
  var pk=list("manufacturing_package").sort(function(a,b){return (a.updated_at||"")<(b.updated_at||"")?-1:1;}).pop();
  if(!pk) return '<section class="panel"><h2>Manufacturing release</h2><div class="empty">No manufacturing package recorded.'+cmd("edagov manifest --outputs ./fab")+'</div></section>';
  var steps=[["Manifest",pk.completeness==="complete"?"complete":pk.completeness==="conflict"?"conflict":"incomplete",pk.completeness],["Plotted-view review",pk.plotted_view_review]].concat(["design_owner","fabrication_dfm","assembly_dfa","release_control"].filter(function(k){return (pk.signoffs||{})[k];}).map(function(k){return [k.replace(/_/g," ")+" sign-off",(pk.signoffs[k]||{}).state];}));
  var h='<section class="panel" aria-labelledby="h-rel"><div class="ph"><h2 id="h-rel">Release package '+idlink(pk.id)+'</h2>'+badge(pk.state,pk)+'</div>'+
    '<div class="ev" style="border:0;padding:0"><dl><dt>Board / assembly</dt><dd class="mono">'+esc(pk.board_id)+' / '+esc(pk.assembly_id)+'</dd><dt>Revision · variant</dt><dd class="mono">'+esc(pk.revision)+' · '+esc(pk.variant)+'</dd><dt>Units</dt><dd>'+esc((pk.units||[]).join(", ")||"—")+'</dd><dt>Origin</dt><dd>'+esc(pk.origin)+'</dd><dt>Supplier assumptions</dt><dd>'+esc((pk.supplier_assumptions||[]).join("; ")||"none recorded")+'</dd></dl></div>'+
    '<h3 style="margin:14px 0 8px">Release steps</h3><ol class="rail steps" aria-label="Release sign-off steps">'+steps.map(function(s){return '<li data-tone="'+tone(s[1])+'"><span class="nm">'+esc(s[0])+'</span>'+badge(s[1]||"not_started",null,s[2])+'</li>';}).join("")+'</ol></section>';
  h+='<section class="panel" aria-labelledby="h-cf"><h2 id="h-cf" style="margin-bottom:12px">Consistency findings</h2>'+table([["Severity",function(r){return badge(r.severity);}],["Finding",function(r){return esc(r.message);}],["Next action",function(r){return esc(r.next_action);}]],pk.consistency_findings||[],{empty:"No consistency findings."})+'</section>';
  h+='<section class="panel" aria-labelledby="h-mf"><h2 id="h-mf" style="margin-bottom:12px">Manifest</h2>'+table([["File",function(r){return '<span class="mono">'+esc(r.filename)+'</span>';}],["Kind",function(r){return esc(r.kind);}],["Format",function(r){return esc(r.format||"—");}],["Function",function(r){return '<span class="mono">'+esc(r.file_function||"—")+'</span>';}],["Units",function(r){return esc(r.units||"—");}],["Rev.",function(r){return esc(r.project_revision||"—");}],["SHA-256",function(r){return '<span class="mono">'+esc(short(r.hash))+'</span>';}]],pk.files||[],{caption:"Manifest files"})+'</section>';
  h+='<section class="panel" aria-labelledby="h-dfm"><h2 id="h-dfm" style="margin-bottom:12px">DFM / DFA findings</h2>'+table([["ID",function(r){return '<span class="mono">'+esc(r.id)+'</span>';}],["Rule",function(r){return esc(r.rule);}],["Finding",function(r){return esc(r.description);}],["Disposition",function(r){return badge(r.disposition);}],["Rationale · approver",function(r){return esc(r.rationale)+(r.approver?' · '+esc(r.approver):'');}]],pk.dfm_findings||[],{empty:"No DFM/DFA review recorded yet."})+
    '<ul class="plain small" style="margin-top:10px">'+(pk.limitations||[]).map(function(l){return '<li>'+esc(l)+'</li>';}).join("")+'</ul></section>';
  return h;
}

/* ---------- Screen F ---------- */
function screenReview(){
  var h='<section class="panel">'+filterBar()+'</section>';
  h+='<section class="panel" aria-labelledby="h-ga"><div class="ph"><h2 id="h-ga">Gate decisions</h2><span class="small muted">An approval is bound to the evidence fingerprint. If evidence changes, the approval is shown as stale.</span></div>'+
    table([["Gate",function(g){return esc(GATE_NAMES[g.gate]);}],["State",function(g){return badge(g.state,BYID["GATE:"+g.gate]);}],["Automation",function(g){return badge(g.automation_state);}],["Approval",function(g){return g.approval?idlink(g.approval)+(g.approval_note?'<br><span class="small" style="color:var(--s-warn)">'+esc(g.approval_note)+'</span>':''):'—';}],["Record a decision (run locally)",function(g){return cmd('edagov approve '+g.gate+' --decision approved --note "..."');}]],D.gates||[],{caption:"Gate decisions"})+'</section>';
  var issues=list("issue").filter(pass);
  h+='<section class="panel" aria-labelledby="h-is"><div class="ph"><h2 id="h-is">Issues</h2></div>'+table([["ID",function(r){return idlink(r.id);}],["Title",function(r){return esc(r.title);}],["Severity",function(r){return badge(r.severity,r);}],["State",function(r){return badge(r.state);}],["Owner",function(r){return esc(r.owner);}],["Gates",function(r){return esc((r.gates||[]).join(", ")||"all");}],["Due / trigger",function(r){return esc(r.due_or_trigger||"—");}],["Affected",function(r){return (r.affected||[]).map(idlink).join(" ");}]],issues,{caption:"Issues",empty:"No issues match."})+
    '<p class="small muted" style="margin-top:8px">Acknowledging never changes technical state. To escalate, open or link an issue with an owner and deadline:</p>'+cmd('edagov issue open "title" --severity high --owner name --affected RUN-... --gate pcb --due 2026-11-15')+'</section>';
  h+='<section class="panel" aria-labelledby="h-ex"><h2 id="h-ex" style="margin-bottom:12px">Accepted exceptions</h2>'+table([["ID",function(r){return idlink(r.id);}],["Title",function(r){return esc(r.title);}],["Rationale",function(r){return esc(r.rationale);}],["Approver · date",function(r){return esc(r.approver)+' · '+esc(when(r.approved_at));}],["Review trigger",function(r){return esc(r.review_trigger);}],["Affected claims",function(r){return (r.affected_claims||[]).map(idlink).join(" ");}]],list("exception").filter(pass),{empty:"No exceptions recorded."})+'</section>';
  h+='<section class="panel" aria-labelledby="h-rv"><h2 id="h-rv" style="margin-bottom:12px">Reviews</h2>'+table([["ID",function(r){return idlink(r.id);}],["Target",function(r){return idlink(r.target);}],["Reviewer",function(r){return esc(r.reviewer)+(r.reviewer_verified?'':' <span class="small muted">(identity unverified)</span>');}],["Role",function(r){return esc(r.reviewer_role);}],["State",function(r){return badge(r.state,r);}],["Comments",function(r){return esc(r.comments);}]],list("review").filter(pass),{empty:"No reviews recorded."})+'</section>';
  var prs=list("github_pr");
  h+='<section class="panel" aria-labelledby="h-gh"><div class="ph"><h2 id="h-gh">GitHub pull requests</h2><span class="small muted">Read-only sync. Policy shown is what GitHub reports, not invented.</span></div>'+table([
    ["PR",function(r){return r.url?'<a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.repository)+'#'+esc(r.number)+'</a>':esc(r.repository+"#"+r.number);}],
    ["Lane",function(r){return '<span class="mono">'+esc(r.head||"?")+' → '+esc(r.base||"?")+'</span><br><span class="small">'+esc(r.gitflow_lane||"")+(r.merge_target_matches_convention===false?' · <b style="color:var(--s-warn)">unconventional target</b>':'')+'</span>';}],
    ["Sync",function(r){return badge(r.sync_state,r)+'<br><span class="small muted">'+esc(when(r.last_successful_sync))+'</span>';}],
    ["Approvals (current diff)",function(r){return esc(r.current_diff_approvals)+' / '+esc(r.required_approvals==null?"?":r.required_approvals)+'<br><span class="small">'+esc(r.approvals_state||"")+'</span>';}],
    ["Blocking checks",function(r){return (r.blocking_checks||[]).length?esc(r.blocking_checks.join(", ")):badge("approved",null,"none");}],
    ["Issue links",function(r){return '<ul class="plain small">'+(r.issue_links||[]).map(function(l){return '<li><span class="mono">'+esc(l.issue)+'</span> '+(l.auto_close?badge("approved",null,"auto-closes"):badge("not_applicable",null,"linked only"))+'</li>';}).join("")+'</ul>';}]
  ],prs,{empty:"No GitHub synchronization configured."})+'</section>';
  if(D.diff){var d=D.diff;h+='<section class="panel" aria-labelledby="h-df"><h2 id="h-df" style="margin-bottom:12px">Revision comparison: '+esc(d.before.revision)+' → '+esc(d.after.revision)+'</h2><div class="grid">'+
    ["added","removed","superseded"].map(function(k){return '<div class="ev"><h3>'+k+' ('+d[k].length+')</h3><ul class="plain small mono">'+d[k].slice(0,40).map(function(x){return '<li>'+esc(typeof x==="string"?x:x.record)+'</li>';}).join("")+'</ul></div>';}).join("")+'</div>'+
    table([["Record",function(r){return '<span class="mono">'+esc(r.record)+'</span>';}],["Version",function(r){return esc(r.from_version)+' → '+esc(r.to_version);}],["State",function(r){return esc(r.state[0])+' → '+esc(r.state[1]);}]],d.changed,{empty:"No changed records."})+
    '<h3 style="margin:12px 0 6px">Gate changes</h3>'+table([["Gate",function(r){return esc(r.gate);}],["From",function(r){return badge(r.from||"not_started");}],["To",function(r){return badge(r.to);}]],d.gate_changes,{empty:"No gate changed state."})+'</section>';}
  else h+='<section class="panel"><h2>Revision comparison</h2><p class="small muted">No comparison embedded. Generate one from two snapshots:</p>'+cmd("edagov diff snapshotA.zip snapshotB.zip --dashboard compare.html")+'</section>';
  return h;
}

/* ---------- Screen G ---------- */
function screenAdmin(){
  var h='<section class="panel" aria-labelledby="h-cn"><div class="ph"><h2 id="h-cn">Connectors</h2><span class="small muted">Secret values are never stored or shown; only logical references.</span></div>'+table([
    ["ID",function(r){return idlink(r.id);}],["Provider",function(r){return esc(r.provider);}],["Protocol",function(r){return '<span class="mono">'+esc(r.protocol)+' '+esc(r.protocol_version)+'</span>';}],["Transport",function(r){return esc(r.transport);}],
    ["Scopes",function(r){return esc((r.scopes||[]).join(", "));}],["Trust tier",function(r){return badge(r.trust_tier==="untrusted"?"stale":"approved",r,r.trust_tier);}],["Sync",function(r){return badge(r.sync_state,r);}],["Last success",function(r){return esc(when(r.last_successful_sync));}],["Last error",function(r){return r.last_error?esc(r.last_error.state+": "+r.last_error.error)+'<br><span class="mono small">'+esc(r.last_error.correlation_id||"")+'</span>':"—";}]
  ],list("connector"),{empty:"No connectors registered (not_configured)."})+'</section>';
  h+='<section class="panel" aria-labelledby="h-ca"><h2 id="h-ca" style="margin-bottom:12px">Connector actions</h2>'+table([["ID",function(r){return idlink(r.id);}],["Action",function(r){return '<b>'+esc(r.action)+'</b> → '+esc(r.target);}],["Revision",function(r){return esc(r.affected_revision);}],["State",function(r){return badge(r.action_state,r);}],["Approved by",function(r){return esc(r.approved_by||"—");}],["Outcome evidence",function(r){return esc(r.outcome_evidence||"—");}]],list("connector_action"),{empty:"No connector actions proposed."})+'</section>';
  var ev=(D.audit.events||[]).slice().reverse();
  h+='<section class="panel" aria-labelledby="h-au"><div class="ph"><h2 id="h-au">Audit history</h2>'+badge(D.audit.verified?"verified":"invalid",null,D.audit.verified?"hash chain verified":"hash chain broken")+'</div>'+
    (D.audit.problems&&D.audit.problems.length?'<ul class="plain small">'+D.audit.problems.map(function(p){return '<li>'+esc(p)+'</li>';}).join("")+'</ul>':'')+
    '<p class="small muted">Showing the latest '+ev.length+' of '+D.audit.count+' events. Corrections are new events; nothing is edited in place.</p>'+
    table([["Time",function(r){return '<span class="mono">'+esc(when(r.timestamp))+'</span>';}],["Actor",function(r){return esc(r.actor)+(r.actor_verified?'':' <span class="small muted">(unverified)</span>');}],["Action",function(r){return '<span class="mono">'+esc(r.action)+'</span>';}],["Object",function(r){return '<span class="mono">'+esc(r.object_id)+'</span>';}],["Result",function(r){return badge(r.result==="success"?"approved":"blocked",null,r.result);}],["Reason",function(r){return esc(r.reason);}],["Correlation",function(r){return '<span class="mono small">'+esc(r.correlation_id)+'</span>';}]],ev,{caption:"Audit events"})+'</section>';
  if(D.snapshot) h+='<section class="panel"><h2>Snapshot</h2><p class="mono small">'+esc(D.snapshot.snapshot)+' · '+esc(D.snapshot.store_fingerprint)+'</p><ul class="plain small">'+D.snapshot.caveats.map(function(c){return '<li>'+esc(c)+'</li>';}).join("")+'</ul></section>';
  return h;
}

/* ---------- drawer: explain status ---------- */
var lastFocus=null;
function openDrawer(rec){
  lastFocus=document.activeElement;
  var b=document.getElementById("drawer-body"); var title=document.getElementById("drawer-title");
  title.textContent=(rec.type==="gate_eval"?"Explain status: "+(GATE_NAMES[rec.gate]||rec.gate):(rec.type||"record")+" "+rec.id);
  var h='<div>'+badge(rec.state||rec.result_class||rec.sync_state)+'</div><div class="ev" style="border:0;padding:0"><dl>'+
    row("State",rec.state)+row("Severity",rec.severity)+row("Timestamp",when(rec.timestamp||rec.evaluated_at))+row("Owner",rec.owner)+row("Source",rec.source)+row("Freshness",rec._freshness)+row("Revision",rec.revision)+row("Variant",rec.variant)+row("Next action",rec.next_action)+'</dl></div>';
  if(rec.type==="gate_eval"){h+='<h3>Rule, inputs and result</h3><pre class="explain">'+esc(rec.explanation)+'</pre>'+cmd("edagov explain "+rec.gate);}
  if(rec.claim_scope) h+='<h3>Claim scope</h3><p class="small">'+esc(rec.claim_scope)+'</p>';
  if(rec.limitations&&rec.limitations.length) h+='<h3>Limitations</h3><ul class="plain small">'+rec.limitations.map(function(l){return '<li>'+esc(l)+'</li>';}).join("")+'</ul>';
  if(rec.findings&&rec.findings.length) h+='<h3>Findings</h3><ul class="plain small">'+rec.findings.map(function(f){return '<li>'+esc(f.severity)+': '+esc(f.message)+'</li>';}).join("")+'</ul>';
  var l=links(rec); if(l.length) h+='<h3>Linked evidence</h3><div class="chips">'+l.map(function(x){return '<span class="chip mono">'+esc(x)+'</span>';}).join("")+'</div>';
  h+='<details><summary class="small">Full record (JSON)</summary><pre class="explain">'+esc(JSON.stringify(rec,null,2))+'</pre></details>';
  b.innerHTML=h; var d=document.getElementById("drawer"); d.hidden=false; document.getElementById("drawer-close").focus();
  say("Opened details for "+title.textContent);
}
function row(k,v){return v==null||v===""?"":'<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>';}
function closeDrawer(){document.getElementById("drawer").hidden=true; if(lastFocus&&lastFocus.focus) lastFocus.focus();}
function say(t){var l=document.getElementById("live"); l.textContent=""; setTimeout(function(){l.textContent=t;},30);}

/* ---------- router ---------- */
var RENDER={overview:screenOverview,requirements:screenRequirements,evidence:screenEvidence,bom:screenBom,release:screenRelease,review:screenReview,admin:screenAdmin};
var current="overview";
function show(name, focusMain){
  if(!RENDER[name]) name="overview"; current=name; REG=[];
  tabs(name);
  var m=document.getElementById("main"); m.setAttribute("aria-labelledby","tab-"+name); m.innerHTML=RENDER[name]();
  if(focusMain) m.focus();
}
function route(){show((location.hash||"").replace("#","")||"overview");}
document.addEventListener("click",function(e){
  var t=e.target.closest("[data-screen],[data-rec],[data-copy],[data-go],[data-trace],[data-clear]"); if(!t) return;
  if(t.dataset.screen){ if(location.hash!=="#"+t.dataset.screen){location.hash=t.dataset.screen;} else show(t.dataset.screen); return; }
  if(t.dataset.go){location.hash=t.dataset.go; return;}
  if(t.dataset.rec!=null){openDrawer(REG[+t.dataset.rec]); return;}
  if(t.dataset.trace!=null){TRACE=t.dataset.trace||null; show("requirements"); say(TRACE?"Tracing "+TRACE:"Trace cleared"); return;}
  if(t.dataset.clear){F[t.dataset.clear]=""; show(current); say("Filter removed"); return;}
  if(t.dataset.copy!=null){var txt=t.dataset.copy; var done=function(){t.textContent="Copied";say("Command copied");setTimeout(function(){t.textContent="Copy";},1500);};
    try{navigator.clipboard.writeText(txt).then(done,function(){selectCode(t);});}catch(err){selectCode(t);}}
});
function selectCode(btn){var c=btn.parentNode.querySelector("code");var r=document.createRange();r.selectNodeContents(c);var s=getSelection();s.removeAllRanges();s.addRange(r);say("Command selected; press Ctrl+C to copy");}
document.addEventListener("change",function(e){var id=e.target.id; if(!/^f-/.test(id)) return; F[id.slice(2)]=e.target.value; show(current); var el=document.getElementById(id); if(el) el.focus(); say("Filters updated");});
document.addEventListener("input",function(e){if(e.target.id!=="f-q")return; F.q=e.target.value; clearTimeout(window.__q); window.__q=setTimeout(function(){var pos=e.target.selectionStart; show(current); var el=document.getElementById("f-q"); if(el){el.focus(); try{el.setSelectionRange(pos,pos);}catch(x){}} say("Search updated");},250);});
document.getElementById("tabs").addEventListener("keydown",function(e){
  var i=SCREENS.findIndex(function(s){return s[0]===current;}); var n=null;
  if(e.key==="ArrowRight") n=(i+1)%SCREENS.length; else if(e.key==="ArrowLeft") n=(i-1+SCREENS.length)%SCREENS.length; else if(e.key==="Home") n=0; else if(e.key==="End") n=SCREENS.length-1;
  if(n!=null){e.preventDefault(); location.hash=SCREENS[n][0]; setTimeout(function(){var b=document.getElementById("tab-"+SCREENS[n][0]); if(b) b.focus();},0);}
});
document.getElementById("drawer-close").addEventListener("click",closeDrawer);
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!document.getElementById("drawer").hidden) closeDrawer();});
window.addEventListener("hashchange",route);
shell(); route();
})();
</script>"""
