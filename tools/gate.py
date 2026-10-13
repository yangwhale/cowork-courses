#!/usr/bin/env python3
"""禁词闸：扫仓库里的文本文件和构建产物，命中任何一条规则就失败。

每门课的脱敏口径不同，规则表按课程分：
  {"<课程文件夹>": [[名字, 正则, flags], ...], ...}
课程文件夹里的文件只套这门课的规则；文件夹以外的文件（README、tools/ 等）套全部规则的并集。
仓库里出现了规则表里没有的课程文件夹，直接失败：新课先补规则再进来。

规则表不在仓库里（它本身就含有不该公开的字样）：
  · CI 里来自 secret FORBIDDEN_PATTERNS
  · 本机用环境变量 FORBIDDEN_PATTERNS_FILE 指向规则文件

日志只打印文件、行号和规则序号，不打印规则内容和命中的原文。

  python3 tools/gate.py            # 扫整个仓库（含各课程的 out/）
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".webm", ".pdf", ".woff", ".woff2", ".ttf"}
SKIP = {".git", "__pycache__"}


def load():
    raw = os.environ.get("FORBIDDEN_PATTERNS")
    if not raw and os.environ.get("FORBIDDEN_PATTERNS_FILE"):
        raw = Path(os.environ["FORBIDDEN_PATTERNS_FILE"]).read_text()
    if not raw:
        sys.exit("⛔ gate: 没有规则表（FORBIDDEN_PATTERNS / FORBIDDEN_PATTERNS_FILE 都没设）。"
                 "从 fork 提的 PR 拿不到 secret，请维护者在本仓库分支上重跑。")
    return {k: [re.compile(p, f) for _, p, f in v] for k, v in json.loads(raw).items()}


def svg_text(t: str) -> str:
    """SVG 里路径坐标、动画时间参数是画图用的数字，不是正文；剥掉再扫。<text> / <title> / 注释照扫。"""
    t = re.sub(r'\sd="[^"]*"', ' d=""', t)
    t = re.sub(r"(?s)<style[^>]*>.*?</style>", lambda m: re.sub(r"\d+(?:\.\d+)?(?:%|m?s\b)", "", m.group(0)), t)
    return re.sub(r'\s(?:dur|begin|end|keyTimes|keySplines|values|repeatDur|calcMode|from|to|by)="[^"]*"', "", t)


def main():
    books = load()
    courses = {p.parent.name for p in ROOT.glob("*/build.py")}
    if courses - books.keys():
        sys.exit(f"⛔ gate: 这些课程还没有规则表：{sorted(courses - books.keys())}，请维护者补上")
    union = [rx for v in books.values() for rx in v]
    hits = 0
    for f in sorted(ROOT.rglob("*")):
        parts = f.relative_to(ROOT).parts
        if not f.is_file() or SKIP & set(parts) or f.suffix.lower() in BINARY:
            continue
        rel = f.relative_to(ROOT).as_posix()
        rules = books[parts[0]] if parts[0] in courses else union
        t = f.read_bytes().decode("utf-8", errors="replace")
        if f.suffix == ".svg":
            t = svg_text(t)
        for n, line in enumerate([rel] + t.split("\n")):
            for i, rx in enumerate(rules):
                if rx.search(line):
                    hits += 1
                    print(f"❌ {rel}:{n if n else '(路径)'}  规则 #{i}")
    if hits:
        sys.exit(f"⛔ gate: {hits} 处命中。改掉再提交；看不出哪里不对就问维护者。")
    print(f"✅ gate: {len(courses)} 门课、{len(union)} 条规则，0 命中")


if __name__ == "__main__":
    main()
