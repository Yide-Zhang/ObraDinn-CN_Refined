#!/usr/bin/env python3
"""核对「模板里用到的 [] 占位符」与「人名表的行」是否一一对应。只读。

这类漏网很隐蔽：模板里写了 [CrewNameXxxDia]，但表里没有对应行 ——
运行时这个占位符就展开不出来（或被当字面量）。

用法: python CN_Refined/langpack/check_tokens.py [模板.tsv] [人名表.tsv] [--report 文件]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TPL = HERE / "extracted" / "template-zh-s.tsv"
DEFAULT_TBL = HERE / "extracted" / "crew_name_variants.tsv"

# 这些占位符不进人名表（另有归属：按是否和谐版显示 / 挂难度档位）
EXEMPT = {"[China]", "[Formosa]", "[DifficultyZH]", "[]键"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tpl", nargs="?", default=str(DEFAULT_TPL))
    ap.add_argument("tbl", nargs="?", default=str(DEFAULT_TBL))
    ap.add_argument("--report")
    args = ap.parse_args()

    tpl_lines = Path(args.tpl).read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n")
    used = {}
    for ln in tpl_lines:
        if not ln.strip() or ln.startswith("#"):
            continue
        key = ln.split("\t")[0]
        for tok in re.findall(r"\[[A-Za-z0-9_]+\]", ln):
            if tok in EXEMPT:
                continue
            used.setdefault(tok, []).append(key)

    tbl_keys = set()
    for ln in Path(args.tbl).read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if f[0].strip() and f[0].strip() != "[]键":
            tbl_keys.add(f[0].strip())

    missing = {t: ks for t, ks in used.items() if t not in tbl_keys}
    extra = sorted(tbl_keys - set(used))

    rep = []
    say = rep.append
    say("模板里用到的占位符: %d 个（已排除 %s）" % (len(used), ", ".join(sorted(EXEMPT - {"[]键"}))))
    say("人名表里的行    : %d 个" % len(tbl_keys))
    say("")
    if missing:
        say("!! 模板用了、但表里没有的占位符 %d 个:" % len(missing))
        for t, ks in sorted(missing.items()):
            say("   %-26s 出现于: %s" % (t, ", ".join(sorted(set(ks)))))
    else:
        say("模板用到的占位符全部都有表行 ✓")
    if extra:
        say("")
        say("表里有、但模板没用到 %d 个（可能是预留或已废弃）:" % len(extra))
        for t in extra:
            say("   %s" % t)

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
