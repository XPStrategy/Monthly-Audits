#!/usr/bin/env python3
"""Add the account's Links / Pages bar to a standalone page (category or listing scorecard) before publishing.

Usage: python3 tools/add_linkbar.py --repo . --client xps-<client> page.html [page2.html ...]
The bar markup and its base styles are copied from the account's own index.html, so links match links.json.
publish_monthly.py then fills the Pages switcher. Running it twice on the same file does nothing.
"""
import argparse, glob, os, re


def strip_media(s):
    out, i = [], 0
    while i < len(s):
        j = s.find("@media", i)
        if j < 0:
            out.append(s[i:]); break
        out.append(s[i:j]); k = s.find("{", j) + 1; d = 1
        while d and k < len(s):
            d += (s[k] == "{") - (s[k] == "}"); k += 1
        i = k
    return "".join(out)


def bar_and_css(index_html):
    src = open(index_html, encoding="utf-8").read()
    style = " ".join(re.findall(r"<style>(.*?)</style>", src, re.S))
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", strip_media(style))
    css = '.linkbar{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif}\n'
    css += "".join(f"{a.strip()}{{{b}}}\n" for a, b in rules if re.search(r"\.linkbar|\.lb-|\.lk\b|\.lk-", a))
    css += "@media (max-width:720px){.linkbar-in{padding:9px 16px}}\n"
    i = src.find('<div class="linkbar"')
    if i < 0:
        raise SystemExit("no linkbar in " + index_html)
    # the bar ends where its two wrapping divs close
    depth, k = 0, i
    for m in re.finditer(r"<div\b|</div>", src[i:]):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            k = i + m.end(); break
    return src[i:k], css


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True); ap.add_argument("--client", required=True); ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    client = a.client.replace("xps-", "")
    hits = glob.glob(os.path.join(a.repo, "accounts", client + "-" + "[0-9a-f]" * 8))
    if not hits:
        raise SystemExit("no account folder for " + client)
    bar, css = bar_and_css(os.path.join(hits[0], "index.html"))
    for f in a.files:
        s = open(f, encoding="utf-8").read()
        if 'class="linkbar"' in s:
            print("already has a bar:", f); continue
        s = s.replace("</head>", f"<style>\n{css}</style></head>", 1)
        s = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + bar, s, count=1)
        open(f, "w", encoding="utf-8").write(s)
        print("bar added:", f)


if __name__ == "__main__":
    main()
