#!/usr/bin/env python3
"""挑出「值得精修」的人名候选（供精修中文名那两列参考）。

两条判据都是可追溯的数据，不靠语感：
  A. **中文 Short 与全名相同** —— 英文那边是 `R. Witterel` 这种缩写，
     中文这边完全没缩。这是整张表要解决的主要问题。
  B. **dev 与官方 zh-s 不一致** —— 官方是正式译名，差异处往往值得回看。

另附 C：英文有 Short、而中文 Short 不是英文 Short 音译上的「缩写形态」的明细，
    其实就是 A 的展开，便于逐条过。

用法: python name_candidates.py <TSV 目录> <输出.txt>
"""
from __future__ import annotations

import sys
from pathlib import Path


def load(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        k, _, v = line.partition("\t")
        d[k] = v
    return d


def slots(v: str | None) -> tuple[str, str]:
    if v is None:
        return ("", "")
    a, sep, b = v.partition("|")
    return (a.strip(), b.strip() if sep else "")


def main() -> int:
    root = Path(sys.argv[1])
    out = Path(sys.argv[2])

    dev = load(root / "dev-zh-s.tsv")
    off = load(root / "original-zh-s.tsv")
    en = load(root / "original-en.tsv")
    tpl = load(root / "template-zh-s.tsv")

    keys = [k for k in tpl if k.startswith("crew_name_")]

    a_list: list[str] = []
    b_list: list[tuple[str, str, str, str, str, str]] = []
    en_has_short = 0

    for k in keys:
        d1, d2 = slots(dev.get(k))
        o1, o2 = slots(off.get(k))
        e1, e2 = slots(en.get(k))

        if e2 and e2 != e1:
            en_has_short += 1
        if d2 == d1:
            a_list.append(k)
        if (d1, d2) != (o1, o2):
            b_list.append((k, d1, d2, o1, o2, en.get(k, "")))

    print("keys = %d" % len(keys))
    print("英文有真 Short（≠全名）的 = %d" % en_has_short)
    print("A 中文 Short == 全名 的 = %d" % len(a_list))
    print("B dev ≠ 官方 zh-s 的 = %d" % len(b_list))

    rep = ["# 人名精修候选", "",
           "keys=%d  英文有真 Short 的=%d  A(中文Short==全名)=%d  B(dev≠官方)=%d"
           % (len(keys), en_has_short, len(a_list), len(b_list)), ""]
    rep.append("## B：dev 与官方 zh-s 不一致（官方译名可作参照）")
    for k, d1, d2, o1, o2, env in b_list:
        rep.append("  %s" % k)
        rep.append("    en       = %s" % env)
        rep.append("    dev      = %s|%s" % (d1, d2))
        rep.append("    官方 zh-s = %s|%s" % (o1, o2))
    rep.append("")
    rep.append("## A：中文 Short 与全名相同（英文那边是缩写）")
    for k in a_list:
        rep.append("  %s" % k)

    out.write_text("\n".join(rep), encoding="utf-8")
    print("detail -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
