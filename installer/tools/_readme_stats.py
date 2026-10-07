# -*- coding: utf-8 -*-
"""统计我们的精修版与官方简中的差异（给 README 用真实数字）。

输出：差异条数 + 前若干条例子（key / 官方 / 精修）。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # CN_Refined/
LT = ROOT / "installer" / "assets" / "langtool" / "langtool.exe"
OFFICIAL = ROOT / "installer" / "assets" / "lang-zh-s-official"
OURS = ROOT / "installer" / "assets" / "packs" / "zh-s-v5-unharm-bi.tsv"
OUT = ROOT / "out" / "_diff_report.txt"


def read(p: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln or ln.startswith("#") or "\t" not in ln:
            continue
        k, v = ln.split("\t", 1)
        d[k] = v
    return d


def main() -> int:
    tmp = Path(tempfile.gettempdir()) / "official_export_readme.tsv"
    r = subprocess.run([str(LT), "export", str(OFFICIAL), str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.is_file():
        print("export 失败：%s" % ((r.stdout or "") + (r.stderr or ""))[:200])
        return 1
    off, ours = read(tmp), read(OURS)
    diff = {k: (off[k], ours[k]) for k in ours if k in off and off[k] != ours[k]}
    only_ours = sorted(set(ours) - set(off))

    L = ["共 %d 条字符串；与官方简中不同的 %d 条；我们独有的 key %d 个"
         % (len(ours), len(diff), len(only_ours)), ""]
    # 按 key 前缀分组统计，方便 README 里说清"改了哪几类"
    groups: dict[str, int] = {}
    for k in diff:
        g = k.split("_")[0]
        groups[g] = groups.get(g, 0) + 1
    L.append("按前缀分组：")
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        L.append("   %-14s %d" % (g, n))

    L.append("")
    L.append("=== 人名相关（crew_*/name 类）示例 ===")
    n = 0
    for k, (a, b) in sorted(diff.items()):
        if "crew" in k or "name" in k:
            L.append("   %-34s 官方=%r  精修=%r" % (k, a, b))
            n += 1
            if n >= 14:
                break
    L.append("")
    L.append("=== 其它示例（前 20 条） ===")
    other = [(k, v) for k, v in sorted(diff.items()) if "crew" not in k and "name" not in k]
    for k, (a, b) in other[:20]:
        L.append("   %-34s 官方=%r  精修=%r" % (k, a[:40], b[:40]))

    OUT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print("\n（完整写 %s）" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
