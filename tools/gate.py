#!/usr/bin/env python3
"""禁词闸：扫仓库里的文本文件和构建产物，命中任何一条规则就失败。

规则表不在仓库里（它本身就含有不该公开的字样）：
  · CI 里来自 secret FORBIDDEN_PATTERNS（JSON：[[名字, 正则, flags], ...]）
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
    return [re.compile(p, f) for _, p, f in json.loads(raw)]


def main():
    rules = load()
    hits = 0
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or SKIP & set(f.relative_to(ROOT).parts) or f.suffix.lower() in BINARY:
            continue
        rel = f.relative_to(ROOT).as_posix()
        lines = [rel] + f.read_bytes().decode("utf-8", errors="replace").split("\n")
        for n, line in enumerate(lines):
            for i, rx in enumerate(rules):
                if rx.search(line):
                    hits += 1
                    print(f"❌ {rel}:{n if n else '(路径)'}  规则 #{i}")
    if hits:
        sys.exit(f"⛔ gate: {hits} 处命中。改掉再提交；看不出哪里不对就问维护者。")
    print(f"✅ gate: {len(rules)} 条规则，0 命中")


if __name__ == "__main__":
    main()
