#!/usr/bin/env python3
"""Build the Weekly Changes page (hub/changes.html): every hub account's Sponsored Products and
Sponsored Brands changes over the last 30 days, grouped into work sessions, behind a password.

The data never sits in the repo in readable form. The weekly run on the XP PC
(C:\\XP\\xp_change_audit\\change_audit.py, Amazon Ads Change History API) writes hub/changes-data.json:
an AES-256-GCM blob (PBKDF2-SHA256, 250,000 iterations) that the page decrypts in the browser with the
password Tim and Abe have. This script only builds the page shell, the filters and the AM / PPC columns
(from tools/account_team.json); rebuild it when the layout or the account list changes:

    python3 tools/build_changes.py --repo .

Monday refresh: copy the new changes-data.json into hub/ and push. The page itself does not change.
"""
import argparse, json, os, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_monthly as P   # noqa: E402
import build_master as M      # noqa: E402
import build_performance as BP  # noqa: E402

B, H, esc = P.B, P.H, P.esc

# Account name in the budget bot config (C:\XP\xp_budget_bot\config.json) -> hub client key.
NAME_TO_CLIENT = {
    "Advanced Bionutritionals": "advanced-bionutritionals", "Badass Moto": "badass-moto", "Bingo": "bingo1525",
    "Cosmo": "cosmo-technologies", "DEZINE": "dzg-products", "Displate": "displate", "Inglesina": "inglesina",
    "Joe's Trends": "joes-trend", "Kensington": "kensingtonvalleytrading", "Kitchen Globe": "boroux",
    "Leading Choice": "leading-choice-products", "Nutrivein": "nutrivein", "Reliable Home": "md-buildingproducts",
    "SavonGoods": "savongoods", "Shine Water": "shinewater", "SkySail": "skysailconsumer",
    "Smart Cookie": "smart-cookie", "Spring Mount": "spring-mount-supply", "Steam Clip": "steam-clip",
    "TrailHeads": "trailheads-apparel", "TurmSkin": "turmskin", "Ultimate Footwear": "ultimate-footwear",
    "Ultimate Washer": "ultimate-washer", "VersaGroup": "versa-group",
}

CSS = """
[hidden] { display:none !important; }
.gate { max-width: 420px; background:#fff; border:1px solid %(border)s; border-radius: 8px; padding: 20px; display:grid; gap: 10px; }
.gate input { font: inherit; font-size: 14px; padding: 9px 10px; border: 1px solid %(border)s; border-radius: 6px; }
.gate button { font: inherit; font-size: 14px; font-weight: 600; padding: 9px 12px; border: 0; border-radius: 6px; background: %(dark)s; color: #fff; cursor: pointer; }
.gate .err { color: %(bad)s; font-size: 13px; min-height: 18px; margin: 0; }
.stp { display:inline-block; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.stp.bad { background: #fbe9e5; color: %(bad)s; } .stp.warn { background: #fdf3e3; color: #9a6512; } .stp.ok { background: #e4f3f1; color: %(good)s; } .stp.na { background:#f1f2f4; color: %(muted)s; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin: 0 0 10px; }
.chip { border: 1px solid %(border)s; border-radius: 4px; padding: 3px 8px; font-size: 12px; color: %(muted)s; background:#fff; }
.chip b { color: %(ink)s; margin-right: 3px; }
.strip { overflow-x:auto; background:#fff; border:1px solid %(border)s; border-radius: 6px; padding: 6px 4px 2px; }
.strip svg { display:block; min-width: 820px; width: 100%%; height:auto; }
.legend { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color: %(muted)s; margin: 8px 0 12px; }
.legend span { display:inline-flex; align-items:center; gap:6px; } .sw { width:10px; height:10px; border-radius:2px; display:inline-block; }
.sess td, .sess th { text-align:left; }
#rows tr.acc td:first-child { min-width: 190px; }
.sess td.n, .sess th.n { text-align:right; }
.sess td.w { white-space: normal; min-width: 260px; }
.kind { font-size: 11px; font-weight: 600; border-radius: 10px; padding: 1px 7px; background: #e8eef9; color: #3a6fc4; white-space: nowrap; }
.kind.m { background:#eef0f3; color: %(muted)s; }
@media print {
  body.print-one main > *:not(.wrap) , body.print-one .tools, body.print-one header, body.print-one footer, body.print-one .tabs-top { display:none !important; }
  body.print-one tbody tr { display:none !important; }
  body.print-one tbody tr.pr { display: table-row !important; }
  body.print-one .det-r { display:none !important; }
  .mini { max-height: none; overflow: visible; }
}
""" % dict(border=B.BORDER, ink=B.INK, dark=B.DARK, muted=B.MUTED, accent=B.ACCENT, good=B.GOOD, bad=B.BAD)

JS = r"""
(function(){
var $ = function(i){ return document.getElementById(i); }, T = window.TEAM, R = null, open = {};
var MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], WD = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
var CATS = [["#2a8c82","New campaigns, ad groups, ads, keywords",["NC","NAG","NAD","NK"]],["#3a6fc4","Bid changes",["BC"]],
  ["#7b5cc4","Budgets, placement, bid strategy",["BU","PL","BS"]],["#c8553d","Pauses and archives",["CP","CA","TP","TA","NA","AP","AA","AGP","AGA"]],
  ["#c99a2e","Negatives added",["NN"]],["#9aa4b2","Re-enables, renames, other",["CE","TE","AE","AGE","RN","OT"]],["#cdd5e0","Automated bid changes (hourly / dayparting)",["AU"]]];
var LABEL = {NC:"new campaigns",NAG:"ad groups added",NAD:"ads added",NK:"keywords/targets added",BC:"bid changes",BU:"budget changes",PL:"placement changes",BS:"bid-strategy changes",CP:"campaigns paused",CA:"campaigns archived",CE:"campaigns re-enabled",TP:"targets paused",TA:"targets archived",TE:"targets enabled",NN:"negatives added",NA:"negatives archived",AP:"ads paused",AA:"ads archived",AE:"ads enabled",AGP:"ad groups paused",AGA:"ad groups archived",AGE:"ad groups enabled",RN:"renames",OT:"other changes",AU:"automated bid changes"};
function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
function pd(s){ var a = s.split("-").map(Number); return new Date(a[0], a[1]-1, a[2]); }
function key(d){ return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); }
function nice(s){ var d = pd(s); return MON[d.getMonth()]+" "+d.getDate(); }
function sum(d, ks){ return ks.reduce(function(a,k){ return a+(d[k]||0); }, 0); }
function fmtK(n){ return n >= 1000 ? (n/1000).toFixed(n >= 10000 ? 0 : 1)+"k" : String(n); }
function words(c){ return Object.keys(c).filter(function(k){ return LABEL[k]; }).slice(0,3).map(function(k){ return c[k].toLocaleString()+" "+LABEL[k]; }).join(", "); }
function b64(s){ return Uint8Array.from(atob(s), function(c){ return c.charCodeAt(0); }); }

async function unlock(blob, pw){
  var km = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
  var k = await crypto.subtle.deriveKey({name:"PBKDF2", salt:b64(blob.salt), iterations:blob.iter, hash:"SHA-256"}, km, {name:"AES-GCM", length:256}, false, ["decrypt"]);
  var pt = await crypto.subtle.decrypt({name:"AES-GCM", iv:b64(blob.iv)}, k, b64(blob.ct));
  return JSON.parse(new TextDecoder().decode(pt));
}

var DATES = [], WK = "";
function prep(){
  var end = pd(R.end), start = pd(R.start);
  for (var d = new Date(start); d <= end; d.setDate(d.getDate()+1)) DATES.push(new Date(d));
  var w = new Date(end); w.setDate(w.getDate()-6); WK = key(w);
  var by = {}; R.accounts.forEach(function(a){ by[T.map[a.name] || ("x-" + a.name)] = a; });
  window.ROWS = T.rows.map(function(t){ return stats(t, by[t.client]); });
  R.accounts.forEach(function(a){ if (!T.map[a.name]) window.ROWS.push(stats({client:"x-"+a.name, brand:a.name, am:"", ppc:[], status:"active"}, a)); });
}
function stats(t, a){
  var r = {t:t, a:a};
  if (!a) { r.flag = ["na","Not in this pull"]; r.ord = 3; return r; }
  if (a.error) { r.flag = ["bad","Data error"]; r.ord = 0; return r; }
  var ss = a.sessions || [];
  r.s7 = ss.filter(function(x){ return x.d >= WK; }).length; r.sAll = ss.length;
  r.bulk = ss.filter(function(x){ return x.k === "B"; }).length; r.hand = r.sAll - r.bulk;
  r.active = a.days.length; r.last = a.days.length ? a.days[a.days.length-1].d : null;
  r.auto = a.days.reduce(function(x,d){ return x+(d.AU||0); }, 0);
  r.tot = a.days.reduce(function(x,d){ return x+d.n-(d.AU||0); }, 0); r.c7 = a.days.filter(function(d){ return d.d >= WK; }).reduce(function(x,d){ return x+d.n-(d.AU||0); }, 0);
  r.dp = (a.automation||[]).filter(function(s){ return s.state === "ENABLED" && s.campaigns > 0; }).length > 0;
  r.flag = r.s7 === 0 ? ["bad","No work in 7 days"] : r.active <= 3 ? ["warn","Low activity"] : ["ok","Active"];
  r.ord = {bad:0, warn:1, ok:2}[r.flag[0]];
  return r;
}

function strip(a){
  var W=1060,H=220,L=46,Rm=10,Tp=24,Bt=40,ph=H-Tp-Bt,n=DATES.length,step=(W-L-Rm)/n,bw=Math.max(3,step-3);
  var by = {}; a.days.forEach(function(d){ by[d.d] = d; });
  var max = Math.log10(Math.max.apply(null, [15].concat(a.days.map(function(d){ return d.n; })))*1.3+1);
  var y = function(v){ return Tp+ph-(Math.log10(v+1)/max)*ph; };
  var s = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Daily changes, log scale" font-family="Arial" font-size="10">';
  DATES.forEach(function(d,i){ if (d.getDay()===0||d.getDay()===6) s += '<rect x="'+(L+i*step)+'" y="'+Tp+'" width="'+step+'" height="'+ph+'" fill="#e7e9ee" opacity=".5"/>'; });
  [1,10,100,1000,10000].forEach(function(v){ if (v !== 1 && Math.log10(v) > max) return; var yy = v===1 ? Tp+ph : y(v);
    s += '<line x1="'+L+'" x2="'+(W-Rm)+'" y1="'+yy+'" y2="'+yy+'" stroke="#e1e4ea"/><text x="'+(L-6)+'" y="'+(yy+3)+'" text-anchor="end" fill="#6b7280">'+(v===1?"0":v.toLocaleString())+'</text>'; });
  DATES.forEach(function(d,i){ var day = by[key(d)], x = L+i*step+(step-bw)/2;
    if (day) { var top = y(day.n), cur = Tp+ph, h = cur-top;
      CATS.forEach(function(c){ var v = sum(day, c[2]); if (!v) return; var seg = h*v/day.n; cur -= seg;
        s += '<rect x="'+x+'" y="'+cur+'" width="'+bw+'" height="'+seg+'" fill="'+c[0]+'"><title>'+nice(day.d)+': '+day.n.toLocaleString()+' changes ('+day.h+' ET)</title></rect>'; });
      s += '<text x="'+(x+bw/2)+'" y="'+(top-4)+'" text-anchor="middle" fill="#18212f" font-size="9">'+fmtK(day.n)+(day.x?'*':'')+'</text>'; }
    if (i===0 || (d.getDay()===1 && i>2)) s += '<text x="'+(L+i*step+step/2)+'" y="'+(H-8)+'" text-anchor="middle" fill="#6b7280">'+MON[d.getMonth()]+' '+d.getDate()+'</text>';
  });
  return s+'</svg>';
}

function detail(r){
  var a = r.a;
  if (!a) return '<p class="na">This account is not in this pull yet: it is either not in the API account list or not pulled in this run.</p>';
  if (a.error) return '<p class="na">Could not pull this account: '+esc(a.error)+'</p>';
  var t = {}; a.days.forEach(function(d){ Object.keys(d).forEach(function(k){ if (LABEL[k]) t[k] = (t[k]||0)+d[k]; }); });
  var chips = [[r.tot,"changes (excl. automated)"],[t.NC||0,"new campaigns"],[t.NK||0,"new keywords / targets"],[t.NN||0,"negatives added"],[t.BU||0,"budget changes"],[t.BC||0,"bid changes (hand / bulk)"],[t.PL||0,"placement changes"],[t.TP||0,"targets paused"],[t.CP||0,"campaigns paused"],[(t.CA||0)+(t.TA||0),"archived"],[t.AU||0,"automated bid changes"],[a.budgetRule||0,"budget-rule changes (Amazon, auto)"]];
  var h = '<div class="det-h"><b>'+esc(r.t.brand)+' &middot; '+nice(R.start)+' &ndash; '+nice(R.end)+'</b><div class="det-r">'
    + '<button class="dl" data-csv="'+esc(r.t.client)+'">Download CSV</button><button class="dl" data-print="'+esc(r.t.client)+'">Print / save PDF</button></div></div>';
  var dp = (a.automation||[]).map(function(s){ return esc(s.name)+' ('+(s.state==="ENABLED"?"on":"paused")+(s.campaigns?', '+s.campaigns.toLocaleString()+' campaigns':'')+(s.since?', since '+nice(s.since):'')+')'; });
  var notes = [];
  if (dp.length) notes.push('<b>Ad Labs dayparting:</b> '+dp.join('; ')+'. Hourly bid changes from it are counted as automated.');
  if (a.days.some(function(d){ return d.x; })) notes.push('<b>*</b> Heavy day: keyword / target bid changes and new keywords / targets were counted, not itemised.');
  if (a.missing_days) notes.push(a.missing_days+' day(s) of this window were not pulled yet.');
  if (notes.length) h += '<p class="na" style="margin:0 0 8px;font-size:12px">'+notes.join(' ')+'</p>';
  h += '<div class="chips">'+chips.map(function(c){ return '<span class="chip"><b>'+c[0].toLocaleString()+'</b>'+c[1]+'</span>'; }).join("")+'</div>';
  h += '<div class="strip">'+strip(a)+'</div><div class="legend">'+CATS.map(function(c){ return '<span><i class="sw" style="background:'+c[0]+'"></i>'+c[1]+'</span>'; }).join("")+'<span>Bar height: changes per day, log scale</span></div>';
  var ss = (a.sessions||[]).slice().reverse();
  if (!ss.length) return h + '<p class="na">No work sessions in this period.</p>';
  h += '<div class="mini sess"><table><thead><tr><th>Date</th><th>Time (ET)</th><th>Type</th><th class="n">Changes</th><th class="n">Campaigns</th><th>What changed</th></tr></thead><tbody>';
  ss.forEach(function(x){ var dd = pd(x.d);
    h += '<tr><td>'+WD[dd.getDay()]+' '+nice(x.d)+'</td><td>'+(x.t0===x.t1 ? x.t0 : x.t0+'&ndash;'+x.t1)+'</td><td><span class="kind'+(x.k==="B"?"":" m")+'">'+(x.k==="B"?"Bulk upload / tool":"Hand edits")+'</span></td><td class="n">'+x.n.toLocaleString()+'</td><td class="n">'+x.c.toLocaleString()+'</td><td class="w">'+esc(words(x.codes))+'</td></tr>'; });
  return h + '</tbody></table></div>';
}

function shown(){
  var q = $("q").value.trim().toLowerCase(), am = $("am").value, ppc = $("ppc").value, st = $("st").value;
  return window.ROWS.filter(function(r){ var s = r.t.status || "active";
    return (!q || r.t.brand.toLowerCase().indexOf(q) >= 0) && (!am || r.t.am === am) && (!ppc || r.t.ppc.indexOf(ppc) >= 0)
      && (st === "" || (st === "current" ? s !== "inactive" : s === st)); })
    .sort(function(p,q){ return p.ord - q.ord || (p.s7||0) - (q.s7||0) || p.t.brand.localeCompare(q.t.brand); });
}
function render(){
  var rs = shown(), h = "";
  rs.forEach(function(r){ var id = r.t.client, o = !!open[id], v = function(x){ return r.a && !r.a.error ? x : '<span class="na">&ndash;</span>'; };
    h += '<tr class="acc'+(o?" open":"")+'" data-id="'+esc(id)+'"><td><span class="car">&#9656;</span><b>'+esc(r.t.brand)+'</b><div class="who">'+esc([r.t.am ? "AM "+r.t.am : "", r.t.ppc.length ? "PPC "+r.t.ppc.join(", ") : ""].filter(Boolean).join(" \u00b7 "))+'</div></td>'
      + '<td><span class="stp '+r.flag[0]+'">'+r.flag[1]+'</span></td><td>'+v(r.s7)+'</td><td>'+v(r.sAll+'<div class="who">'+r.bulk+' bulk &middot; '+r.hand+' hand</div>')+'</td><td>'+v(r.active)+'</td><td>'+v(r.last ? nice(r.last) : "&ndash;")+'</td><td>'+v((r.c7||0).toLocaleString())+'</td><td>'+v((r.tot||0).toLocaleString())+'</td><td>'+v((r.auto||0).toLocaleString()+(r.dp?' <span class="kind m">dayparting</span>':''))+'</td></tr>';
    if (o) h += '<tr class="det" data-id="'+esc(id)+'"><td colspan="9">'+detail(r)+'</td></tr>';
  });
  $("rows").innerHTML = h || '<tr><td colspan="9" class="na">No accounts match the filters.</td></tr>';
  $("count").textContent = rs.length + " account" + (rs.length === 1 ? "" : "s");
  try { localStorage.setItem("xp-hub-f", JSON.stringify({am:$("am").value, ppc:$("ppc").value, st:$("st").value})); } catch (e) {}
}

function q(x){ x = String(x == null ? "" : x); return /[",\n]/.test(x) ? '"'+x.replace(/"/g,'""')+'"' : x; }
function save(name, rows){
  var blob = new Blob(["\ufeff"+rows.map(function(r){ return r.map(q).join(","); }).join("\r\n")], {type:"text/csv"});
  var url = URL.createObjectURL(blob), l = document.createElement("a"); l.href = url; l.download = name; document.body.appendChild(l); l.click();
  setTimeout(function(){ URL.revokeObjectURL(url); l.remove(); }, 0);
}
function slug(s){ return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
function csvAccount(r){
  var out = [["Account","Date","Weekday","Start (ET)","End (ET)","Minutes","Type","Changes","Campaigns"].concat(Object.keys(LABEL).map(function(k){ return LABEL[k]; }))];
  (r.a.sessions||[]).forEach(function(x){ out.push([r.t.brand, x.d, WD[pd(x.d).getDay()], x.t0, x.t1, x.min, x.k==="B"?"Bulk upload / tool":"Hand edits", x.n, x.c].concat(Object.keys(LABEL).map(function(k){ return x.codes[k]||0; }))); });
  save("weekly-changes-"+slug(r.t.brand)+"-"+R.end+".csv", out);
}
function csvAll(){
  var out = [["Account","AM","PPC","Status","Work sessions last 7 days","Work sessions "+DATES.length+" days","Bulk / tool sessions","Hand-edit sessions","Active days","Last change","Changes last 7 days","Changes "+DATES.length+" days","Automated bid changes "+DATES.length+" days"]];
  shown().forEach(function(r){ var ok = r.a && !r.a.error;
    out.push([r.t.brand, r.t.am, r.t.ppc.join(" / "), r.flag[1], ok?r.s7:"", ok?r.sAll:"", ok?r.bulk:"", ok?r.hand:"", ok?r.active:"", ok&&r.last?r.last:"", ok?r.c7:"", ok?r.tot:"", ok?r.auto:""]); });
  save("weekly-changes-all-accounts-"+R.end+".csv", out);
}

$("rows").addEventListener("click", function(e){
  var c = e.target.closest("[data-csv]"), p = e.target.closest("[data-print]");
  if (c) { window.ROWS.forEach(function(r){ if (r.t.client === c.getAttribute("data-csv")) csvAccount(r); }); return; }
  if (p) { var id = p.getAttribute("data-print");
    [].forEach.call(document.querySelectorAll('#rows tr[data-id="'+id.replace(/"/g,'')+'"]'), function(tr){ tr.classList.add("pr"); });
    document.body.classList.add("print-one"); window.print();
    setTimeout(function(){ document.body.classList.remove("print-one"); [].forEach.call(document.querySelectorAll("tr.pr"), function(tr){ tr.classList.remove("pr"); }); }, 500); return; }
  var tr = e.target.closest("tr.acc"); if (!tr) return;
  var id = tr.getAttribute("data-id"); open[id] = !open[id]; render();
});

async function go(){
  var pw = $("pw").value, err = $("err");
  err.textContent = "Opening\u2026";
  try {
    var res = await fetch("changes-data.json", {cache:"no-store"});
    if (!res.ok) throw new Error("nodata");
    var blob = await res.json(); R = await unlock(blob, pw);
  } catch (e) { err.textContent = e.message === "nodata" ? "No data published yet." : "Wrong password. Try again."; return; }
  try { sessionStorage.setItem("xpca", pw); } catch (e) {}
  prep();
  $("gate").hidden = true; $("app").hidden = false;
  $("upd").textContent = "Last 30 days: " + nice(R.start) + " \u2013 " + nice(R.end) + " \u00b7 generated " + R.generated + " \u00b7 all times US Eastern";
  try { var f = JSON.parse(localStorage.getItem("xp-hub-f") || "{}"); ["am","ppc","st"].forEach(function(k){ if (f[k] !== undefined) $(k).value = f[k]; }); } catch (e) {}
  ["am","ppc","st"].forEach(function(k){ $(k).addEventListener("change", render); }); $("q").addEventListener("input", render);
  $("dl-all").addEventListener("click", csvAll);
  render();
}
$("go").addEventListener("click", go);
$("pw").addEventListener("keydown", function(e){ if (e.key === "Enter") go(); });
try { var s = sessionStorage.getItem("xpca"); if (s) { $("pw").value = s; go(); } } catch (e) {}
})();
"""


def page(team_rows, today):
    ams = sorted({r["am"] for r in team_rows if r["am"]}); ppcs = sorted({p for r in team_rows for p in r["ppc"]})
    sel = lambda id_, lab, vals: (f'<select id="{id_}" aria-label="{lab}"><option value="">{lab}: all</option>'
                                  + "".join(f'<option value="{esc(v)}">{lab}: {esc(v)}</option>' for v in vals) + "</select>")
    team = json.dumps({"map": NAME_TO_CLIENT, "rows": team_rows}, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>XP Strategy Analysis - Weekly Changes</title>
<style>{P.HUB_CSS}{H.HEADER_CSS}{BP.CSS}{CSS}
.xph-meta > div:last-child {{ display: none; }}
</style></head><body>
{H.hero_html("Weekly Changes", P.logo_b64(), "US", today, "Last 30 days of account changes")}
<main>
<div class="tabs-top"><a href="./">Account Hubs</a><a href="performance.html">Performance Overview</a><a class="on" href="changes.html">Weekly Changes</a></div>
<div id="gate" class="gate">
  <h2 style="margin:0;border:0;padding:0">Weekly Changes</h2>
  <p class="na" style="margin:0;font-size:13px">Internal. Enter the password to open.</p>
  <input id="pw" type="password" autocomplete="current-password" aria-label="Password">
  <button id="go" type="button">Open</button>
  <p id="err" class="err" role="alert"></p>
</div>
<div id="app" hidden>
<div class="h2row"><div><h2>Weekly Changes</h2><div class="upd" id="upd"></div></div><button class="dl" id="dl-all" title="Accounts currently shown, with the filters applied">Download CSV</button></div>
<div class="tools">
  {sel("am", "AM", ams)}{sel("ppc", "PPC", ppcs)}
  <select id="st" aria-label="Status"><option value="current">Current accounts</option><option value="inactive">Inactive</option><option value="">All accounts</option></select>
  <input id="q" type="search" placeholder="Filter accounts" aria-label="Filter accounts">
  <span class="count" id="count"></span>
</div>
<div class="wrap"><table><thead><tr><th>Account &middot; click for the full timeline</th><th>Status</th><th>Sessions, 7 days</th><th>Sessions, 30 days</th><th>Active days</th><th>Last change</th><th>Changes, 7 days</th><th>Changes, 30 days</th><th>Automated, 30 days</th></tr></thead>
<tbody id="rows"></tbody></table></div>
<p class="notes">A work session is a run of changes with no gap longer than 30 minutes. Bulk / tool = 50+ changes at 10+ per minute (a bulk file or an outside tool); hand edits = everything slower.
One bulk upload can create thousands of changes, so read sessions and active days before the change count. Status: red = no work session in the last 7 days, amber = 3 active days or fewer in 30 days.
Automated = bid changes that repeat hourly on the same campaign (Ad Labs dayparting or another scheduled tool); they have their own column and are left out of sessions and change counts.
Left out entirely: Amazon's out-of-budget toggles; Amazon budget rules are shown per account. Heavy days (over 2,000 changes) count keyword / target bid changes and new keywords / targets instead of listing each one (marked * on the chart). Amazon does not record which user made a change. Sponsored Display is not included.</p>
<p class="source" style="font-size:12px;color:{B.MUTED};margin-top:6px">Source: Amazon Ads Change History API (Sponsored Products and Sponsored Brands), pulled every Monday from the XP API connection. AM and PPC from tools/account_team.json.</p>
</div>
</main>
{H.footer_html(B.DISCLAIMER, "last 30 days", "Weekly Changes", today)}
<script>window.TEAM = {team};</script>
<script>{JS}</script>
</body></html>"""


def build(repo):
    T = M.team()
    team_rows = []
    for r in M.rows(repo):
        client = r["slug"].rsplit("-", 1)[0]
        team_rows.append({"client": client, "brand": r["brand"], "am": r["am"], "ppc": r["ppc"], "status": r["status"]})
    p = os.path.join(repo, "hub", "changes.html")
    open(p, "w").write(page(team_rows, date.today().isoformat()))
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default=".")
    print("[done]", build(ap.parse_args().repo))
