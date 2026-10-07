# -*- coding: utf-8 -*-
"""量一下「单语该保留原文」的规则涉及多少行。

规则（用户 2026-10-06 定）：**官方 zh-s 自己那一行带 `|` 的，单语也必须保留原文**
（原文是外语/闽南语线索，例如 `Signor`、`慢且！伊無做毋著代誌！`）；
官方那一行没有 `|` 的，才按「删竖线前缀」处理。

输出只用 ASCII（键名），避免控制台乱码。

用法: python CN_Refined\\langpack\\_mono_rule_check.py
产物: CN_Refined\\langpack\\out\\mono_rule.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

EX = Path(__file__).resolve().parent / "extracted"
OUT = Path(__file__).resolve().parent / "out" / "mono_rule.txt"


def load(p: Path) -> dict:
    m = {}
    for ln in p.read_text(encoding="utf-8-sig").splitlines():
        if not ln.strip() or ln.startswith("#") or "\t" not in ln:
            continue
        k, v = ln.split("\t", 1)
        m[k] = v
    return m


def main() -> int:
    tpl = load(EX / "template-zh-s.tsv")
    off = load(EX / "original-zh-s.tsv")
    en = load(EX / "original-en.tsv")
    rows = []
    dlg_pipe = [k for k, v in tpl.items() if k.startswith("dialog_") and "|" in v]
    for k in dlg_pipe:
        o = off.get(k, "")
        rows.append((k, "|" in o))
    keep = [k for k, has in rows if has]
    strip = [k for k, has in rows if not has]
    src = OUT.parent
    src.mkdir(parents=True, exist_ok=True)
    rep = []
    rep.append("单语「保留原文」规则核查")
    rep.append("=" * 78)
    rep.append("模板里 dialog_ 含竖线的行 = %d" % len(dlg_pipe))
    rep.append("  官方 zh-s 也含竖线（单语应保留原文）= %d" % len(keep))
    rep.append("  官方 zh-s 无竖线（单语删原文）    = %d" % len(strip))
    rep.append("")
    rep.append("【应保留原文的行】")
    for k in keep:
        rep.append("  %-30s 官方=%r" % (k, off.get(k, "")[:40]))
        rep.append("  %-30s 英文=%r" % ("", en.get(k, "")[:50]))
    rep.append("")
    rep.append("【其它含竖线的行（英文原文行；官方只给中文）前 40】")
    for k in strip[:40]:
        rep.append("  %-30s 官方=%r" % (k, off.get(k, "")[:40]))
    OUT.write_text("\n".join(rep) + "\n", encoding="utf-8-sig")
    # 控制台只打 ASCII
    print("dialog rows with pipe      : %d" % len(dlg_pipe))
    print("  official also has pipe   : %d   <- mono must keep original" % len(keep))
    print("  official has no pipe     : %d   <- mono strips" % len(strip))
    print("keys to keep: %s" % ", ".join(keep[:40]))
    print("report -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
