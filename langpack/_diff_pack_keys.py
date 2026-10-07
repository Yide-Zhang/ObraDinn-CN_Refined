# -*- coding: utf-8 -*-
"""比对两个「语言包 TSV」，只输出**键**和长度（键是 ASCII，控制台不会乱码）。
用来确认某次改动只影响了预期的那几行。

用法: python CN_Refined\\langpack\\_diff_pack_keys.py <新> <旧>
"""
from __future__ import annotations

import sys
from pathlib import Path


def load(p: Path) -> dict:
    m = {}
    for ln in p.read_text(encoding="utf-8-sig").splitlines():
        if not ln.strip() or ln.startswith("#") or "\t" not in ln:
            continue
        k, v = ln.split("\t", 1)
        m[k] = v
    return m


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: _diff_pack_keys.py <new> <old>")
        return 2
    a, b = load(Path(sys.argv[1])), load(Path(sys.argv[2]))
    ka, kb = set(a), set(b)
    print("new=%s keys=%d   old=%s keys=%d" % (Path(sys.argv[1]).name, len(ka),
                                               Path(sys.argv[2]).name, len(kb)))
    if ka - kb:
        print("only in new: %s" % sorted(ka - kb)[:20])
    if kb - ka:
        print("only in old: %s" % sorted(kb - ka)[:20])
    diff = sorted(k for k in ka & kb if a[k] != b[k])
    print("changed keys: %d" % len(diff))
    for k in diff:
        print("  %-34s new_len=%-5d old_len=%-5d" % (k, len(a[k]), len(b[k])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
