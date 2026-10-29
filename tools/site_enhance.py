#!/usr/bin/env python3
"""Site-wide additions injected into every account page at publish time (idempotent):

- Pages switcher grouped into dropdowns: Home · Monthly Reviews (newest 3) · one entry per Home section
  (AMC Reviews, Other Pages, ...). Replaces the flat chip list the shared header draws.
- "All accounts" button (master hub) and "Download PDF" button at the right of the links bar.
- Hides "Report Created" in the hero (the footer keeps the build date).
- PDF: render_pdf() writes <page>.pdf next to each published page; the button downloads it, or opens
  the print dialog when no PDF exists yet.
"""
import json, os, re

MARK_A, MARK_B = "<!--xp-site-enhance-->", "<!--/xp-site-enhance-->"

CSS = """
.xph-meta > div:last-child { display: none; }
.xpg { position: relative; display: inline-block; }
.xpg > summary { list-style: none; cursor: pointer; }
.xpg > summary::-webkit-details-marker { display: none; }
.xpg > summary::after { content: " \\25BE"; font-size: 10px; }
.xpg-m { position: absolute; right: 0; top: calc(100% + 6px); z-index: 50; min-width: 210px; background: #fff;
  border: 1px solid #d9dbe0; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.12); padding: 6px; }
.xpg-m a, .xpg-m span { display: block; padding: 7px 10px; border-radius: 6px; font-size: 12.5px; font-weight: 600;
  color: #111318; text-decoration: none; white-space: nowrap; }
.xpg-m a:hover { background: #fff3e0; }
.xpg-m span.cur { background: #111318; color: #fff; }
.xpg-m .off { color: #9aa0a6; font-weight: 500; }
.xp-act { display: inline-flex; gap: 8px; margin-left: 6px; padding-left: 12px; border-left: 1px solid #d9dbe0; }
.xp-act a, .xp-act button { font: inherit; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 14px;
  border: 1px solid #FF9900; background: #FF9900; color: #111318; cursor: pointer; text-decoration: none; white-space: nowrap; }
.xp-act a.hub { background: #111318; border-color: #111318; color: #fff; }
@media print { .linkbar, .xp-act, .xpg, nav.tabs { display: none !important; } .xph-hero { position: static !important; } }
"""

JS = r"""
(function(){
  var CFG = __CFG__;
  var here = location.pathname.split('/').pop() || 'index.html';
  function e(t){ var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }
  function group(label, items){
    if (!items.length) return '';
    var cur = items.some(function(p){ return p.file === here; });
    var m = items.map(function(p){
      if (p.file === here) return '<span class="cur">' + e(p.label) + '</span>';
      return '<a href="' + e(p.file) + '"' + (p.status === 'placeholder' ? ' class="off"' : '') + '>' + e(p.label) + '</a>';
    }).join('');
    return '<details class="xpg"><summary class="lk ' + (cur ? 'lk-here' : 'lk-page') + '">' + e(label) + '</summary><div class="xpg-m">' + m + '</div></details>';
  }
  function render(pages){
    var box = document.querySelector('.lb-pages'); if (!box) return;
    var months = pages.filter(function(p){ return p.kind !== 'page'; }).slice(0, CFG.nav_months);
    var h = '<span class="lb-h lb-h2">Pages</span>' + (here === 'index.html' ? '<span class="lk lk-here">Home</span>' : '<a class="lk lk-page" href="./">&larr; Home</a>');
    h += group('Monthly Reviews', months);
    CFG.sections.forEach(function(s){
      h += group(s[1], pages.filter(function(p){ return p.kind === 'page' && (p.section || 'other') === s[0]; }));
    });
    var pdf = CFG.pdf ? '<a href="' + e(CFG.pdf) + '" download>Download PDF</a>' : (CFG.printable ? '<button type="button" class="xp-print">Download PDF</button>' : '');
    h += '<span class="xp-act">' + pdf + '<a class="hub" href="' + e(CFG.hub) + '">All accounts</a></span>';
    box.setAttribute('data-xp', '1'); box.innerHTML = h; box.style.display = 'inline-flex';
    var b = box.querySelector('.xp-print'); if (b) b.addEventListener('click', function(){ window.print(); });
  }
  var PAGES = CFG.pages;
  function draw(){ render(PAGES); }
  function boot(){
    draw();
    var box = document.querySelector('.lb-pages');
    if (box && window.MutationObserver) new MutationObserver(function(){ if (!box.querySelector('.xpg') && box.getAttribute('data-xp') !== '2') { box.setAttribute('data-xp','2'); draw(); box.setAttribute('data-xp','1'); } }).observe(box, {childList: true});
    document.addEventListener('click', function(ev){
      document.querySelectorAll('details.xpg[open]').forEach(function(d){ if (!d.contains(ev.target)) d.removeAttribute('open'); });
    });
    if (location.protocol.indexOf('http') === 0) {
      fetch('links.json', {cache: 'no-store'}).then(function(r){ return r.ok ? r.json() : null; }).then(function(j){
        if (j && (j.all_pages || j.pages)) { PAGES = j.all_pages || j.pages; draw(); }
      }).catch(function(){});
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
"""


def block(pages, sections, nav_months, pdf=None, printable=True, hub="../../hub/"):
    cfg = {"pages": pages, "sections": sections, "nav_months": nav_months, "pdf": pdf, "printable": printable, "hub": hub}
    js = JS.replace("__CFG__", json.dumps(cfg).replace("</", "<\\/"))
    return f"{MARK_A}<style>{CSS}</style><script>{js}</script>{MARK_B}"


def inject(path, blk):
    s = open(path, encoding="utf-8").read()
    s = re.sub(re.escape(MARK_A) + r".*?" + re.escape(MARK_B), "", s, flags=re.S)
    i = s.rfind("</body>")
    s = (s[:i] + blk + s[i:]) if i >= 0 else s + blk
    open(path, "w", encoding="utf-8").write(s)


def render_pdf(html_path, pdf_path):
    """Screen-layout PDF of a page (links bar and buttons hidden). Needs Playwright."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto("file://" + os.path.abspath(html_path)); pg.wait_for_timeout(400)
        pg.add_style_tag(content=".linkbar,.xp-act,nav.tabs,.xpc-tip{display:none!important}"
                                 ".xph-hero,.xph-stick{position:static!important}")
        pg.emulate_media(media="screen")
        pg.pdf(path=pdf_path, width="1280px", height="1810px", print_background=True,
               margin={"top": "24px", "bottom": "24px", "left": "0", "right": "0"})
        b.close()
