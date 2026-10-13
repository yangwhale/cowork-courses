#!/usr/bin/env python3
"""把 pages/ 里的正文片段套上页框，输出整站到 out/。

  python3 build.py            # 构建到 out/
  python3 build.py --check    # 构建 + 查坏链 / 坏锚点

book.json 是唯一的目录：栏目、页面顺序、标题、侧栏文字、手册与讲义的配对。
pages/ 下每个文件是一页的正文（<article> 里面那一段）；standalone 的页（首页、宣传页）是整页。
static/ 原样拷贝。侧栏、本页目录、上一页 / 下一页、面包屑、搜索索引都由脚本生成，不要手改产物。
"""
import html
import json
import re
import shutil
from html.parser import HTMLParser
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
BOOK = json.loads((ROOT / "book.json").read_text())
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
           "%3Ctext y='.9em' font-size='90'%3E%F0%9F%A6%80%3C/text%3E%3C/svg%3E")
SIDE_JS = ("try{var d=document.documentElement,w=localStorage.getItem('v7x-sidew');"
           "if(localStorage.getItem('v7x-side')==='off')d.classList.add('side-off');"
           "if(w)d.style.setProperty('--sidew',w+'px')}catch(e){}")


def rel(target: str, frm: str) -> str:
    """站内路径 target 相对于页面 frm 的写法。"""
    a, b = Path(frm).parent.parts, Path(target).parts
    i = 0
    while i < len(a) and i < len(b) - 1 and a[i] == b[i]:
        i += 1
    return "/".join([".."] * (len(a) - i) + list(b[i:]))


def root_of(path: str) -> str:
    n = len(Path(path).parts) - 1
    return "/".join([".."] * n) or "."


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def toc_text(h: str) -> str:
    """标题 → 本页目录里的文字：节号后补空格，去掉出处气泡，其余标签剥掉、实体原样保留。"""
    h = re.sub(r'<span class="hn">(.*?)</span>', r"\1 ", h)
    h = re.sub(r'<span class="src"[^>]*>源<span class="srci">.*?</span></span>', "", h, flags=re.S)
    return re.sub(r"<[^>]+>", "", h).strip()


def headings(art: str):
    return [(int(m.group(1)), m.group(2), toc_text(m.group(3)))
            for m in re.finditer(r'<h([23]) id="([^"]+)"[^>]*>(.*?)</h\1>', art, re.S)]


class _Text(HTMLParser):
    """正文 → 搜索用纯文本：标签处断开，跳过内嵌图（svg）、样式、脚本和出处气泡（span.src）。"""
    SKIP = {"svg", "style", "script"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            self.out.append(" ")
            return
        hide = tag in self.SKIP or (tag == "span" and "src" in (dict(attrs).get("class") or "").split())
        self.stack.append(hide)
        self.skip += hide
        self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack:
            return
        self.skip -= self.stack.pop()
        self.out.append(" ")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "base", "embed", "track"}


def plain(h: str) -> str:
    p = _Text()
    p.feed(h)
    return re.sub(r"\s+", " ", "".join(p.out)).strip()


def search_index(pages: list) -> str:
    """assets/search-index.js：每页标题、栏目、h2/h3 锚点、全文。site.js 的搜索框读它。"""
    items = []
    for p, art in pages:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", art, re.S)
        items.append({"t": toc_text(h1.group(1)) if h1 else p["title"], "u": p["path"], "s": p["section"],
                      "h": [[hid, plain(h)] for hid, h in re.findall(r'<h[23] id="([^"]+)"[^>]*>(.*?)</h[23]>', art, re.S)],
                      "x": plain(art)})
    return "window.__SEARCH__=" + json.dumps(items, ensure_ascii=False, separators=(",", ":")) + ";"


def topnav(sec: str | None, path: str) -> str:
    links = [f'<a href="{rel("index.html", path)}" class="">首页</a>']
    for s in BOOK["sections"]:
        on = "on" if s["name"] == sec else ""
        links.append(f'<a class="{on}" href="{rel(s["home"], path)}">{s["name"]}</a>')
    return "".join(links)


def page_html(p: dict, art: str, sec_pages: list) -> str:
    path, sec = p["path"], p["section"]
    side = "".join(
        f'<li><a class="on" aria-current="page" href="{rel(q["path"], path)}">{q["side"]}</a></li>' if q is p
        else f'<li><a href="{rel(q["path"], path)}">{q["side"]}</a></li>' for q in sec_pages)
    home = next(s["home"] for s in BOOK["sections"] if s["name"] == sec)
    if home == path:
        crumb = f'<a href="{rel("index.html", path)}">首页</a> › <span>{sec}</span>'
    else:
        crumb = (f'<a href="{rel("index.html", path)}">首页</a> › <a href="{rel(home, path)}">{sec}</a>'
                 f' › <span>{p["side"]}</span>')
    lbar, split = "", ""
    if "lecture" in p:
        lbar = (f'<nav class="lbar" aria-label="手册与讲义"><a class="on" aria-current="page" href="{rel(path, path)}">📘 手册</a>'
                f'<a href="{rel(p["lecture"], path)}">📝 讲义 · {p["lecture_minutes"]}</a>'
                f'<span class="lbar-tip">讲课的人看讲义，投屏放这一页</span></nav>')
    elif "handbook" in p:
        split = (f'<aside class="lsplit" aria-label="并排的手册页"><iframe name="chap" title="手册页" loading="lazy" '
                 f'data-src="{rel(p["handbook"], path)}"></iframe></aside>')
        lbar = (f'<nav class="lbar" aria-label="手册与讲义"><a href="{rel(p["handbook"], path)}">📘 手册</a>'
                f'<a class="on" aria-current="page" href="{rel(path, path)}">📝 讲义 · {p["lecture_minutes"]}</a>'
                f'<button type="button" class="lsplit-btn" aria-pressed="false" '
                f'title="左边讲义、右边手册；点 🖥 屏幕里的链接，右边跟着跳">⇆ 并排看手册</button></nav>')
    pn = ""
    if not p.get("no_pn"):
        i = sec_pages.index(p)
        prv = sec_pages[i - 1] if i > 0 else None
        nxt = sec_pages[i + 1] if i + 1 < len(sec_pages) else None
        a = (f'<a class="prev" href="{rel(prv["path"], path)}"><small>← 上一页</small>{prv["side"]}</a>'
             if prv else "<span></span>")
        b = f'<a class="next" href="{rel(nxt["path"], path)}"><small>下一页 →</small>{nxt["side"]}</a>' if nxt else "<span></span>"
        pn = f'<nav class="pn" aria-label="上一页 / 下一页">{a}{b}</nav>'
    toc = ""
    if not p.get("no_toc"):
        items = "".join(f'<li class="l{lv}"><a href="#{hid}">{txt}</a></li>' for lv, hid, txt in headings(art))
        toc = f'<nav class="ptoc" aria-label="本页目录"><div class="ptoc-h">本页</div><ol>{items}</ol></nav>'
    r = root_of(path)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{p["title"]} · {BOOK["title"]}</title>
<link rel="icon" href="{FAVICON}">
<meta name="v7x-book" content="handbook-public">
<link rel="stylesheet" href="{r}/assets/site.css">
<script>{SIDE_JS}</script>
<meta name="robots" content="noindex">
</head><body data-root="{r}">
<div class="progress"><i></i></div>
<header class="top"><div class="inner">
  <a class="brand" href="{rel("index.html", path)}"><span class="crab">🦀</span><span class="bt">{BOOK["title"]}</span></a>
  <nav class="secs" aria-label="栏目">{topnav(sec, path)}</nav>
  <div class="search"><input id="q" type="search" placeholder="搜索（聚焦）" aria-label="全站搜索" autocomplete="off">
  <div id="qr" class="qr" role="listbox"></div></div>
</div></header>
<div class="page {p["level"]}">
<nav class="side" aria-label="{sec}"><div class="side-h">{sec}</div><ol>{side}</ol></nav>{split}
<main id="main"><nav class="crumb" aria-label="面包屑">{crumb}</nav>{lbar}<article class="{p["article"]}">{art}</article>{pn}</main>
{toc}
</div>
<footer class="foot"><div class="inner">{BOOK["foot"]}</div></footer>
<a class="totop" href="#" aria-label="回到顶部">↑</a>
<script src="{r}/assets/site.js"></script>
</body></html>
"""


def redirect_html(path: str, r: dict) -> str:
    to = r["to"]
    renamed = r["kind"] == "renamed"
    hash = ' + location.hash' if renamed else ""
    msg = f"这一章已改号，在本书《万卡级 {BOOK['title']}》" if renamed else "这一页已并入本书《经验教训》"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="v7x-redirect" content="{to}">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={to}">
<link rel="canonical" href="{to}">
<link rel="icon" href="{FAVICON}">
<title>{r["title"]}</title>
<script>location.replace("{to}"{hash});</script>
</head><body style="font:16px/1.7 sans-serif;margin:40px">
<p>🦀 {msg}，正在跳转……</p>
<p>没有自动跳转就点这里：<a href="{to}">{to}</a></p>
</body></html>
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)
    by_sec = {}
    for p in BOOK["pages"]:
        if not p.get("standalone"):
            by_sec.setdefault(p["section"], []).append(p)
    for p in BOOK["pages"]:
        src = (ROOT / "pages" / p["path"]).read_text()
        dst = OUT / p["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src if p.get("standalone") else page_html(p, src, by_sec[p["section"]]))
    (OUT / "assets/search-index.js").write_text(search_index(
        [(p, (ROOT / "pages" / p["path"]).read_text()) for s in BOOK["sections"] for p in by_sec[s["name"]] if not p.get("no_pn")]))
    for path, r in BOOK["redirects"].items():
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_text(redirect_html(path, r))
    print(f"✅ {len(BOOK['pages'])} 页 + {len(BOOK['redirects'])} 跳转 → {OUT}")
    if "--check" in sys.argv:
        check()


def check():
    """查产物里所有站内链接：目标文件要在，带 #锚点 的要能在目标页找到那个 id。"""
    ids, bad = {}, []
    for f in OUT.rglob("*.html"):
        ids[f] = set(re.findall(r'\bid="([^"]+)"', f.read_text()))
    for f in ids:
        for url in re.findall(r'\b(?:href|src)="([^"]+)"', f.read_text()):
            if re.match(r"(?:[a-z]+:|//|\$|\{)", url):
                continue
            path, _, frag = unquote(html.unescape(url)).partition("#")
            path = path.split("?")[0]
            tgt = (f.parent / path).resolve() if path else f
            if tgt.is_dir():
                tgt = tgt / "index.html"
            if not tgt.exists():
                bad.append(f"{f.relative_to(OUT)} → {url}（文件不存在）")
            elif frag and tgt in ids and frag not in ids[tgt]:
                bad.append(f"{f.relative_to(OUT)} → {url}（锚点不存在）")
    for b in bad:
        print("❌", b)
    if bad:
        sys.exit(f"⛔ {len(bad)} 个坏链")
    print(f"✅ 链接检查：{len(ids)} 个 HTML，0 坏链")


if __name__ == "__main__":
    main()
