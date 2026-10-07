#!/usr/bin/env python3
"""查模板里还有没有「漏换 Token 的硬编码人名」。

做法：从 dev 包里取出每个 `crew_name_*` 的两格中文（全名 / 简称），在模板里全文搜索；
命中且**该行 key 不是 crew_name_** 的，就是候选漏网。

注意：简称常常是别人全名的子串（如「霍斯卡特」是「阿比盖尔·霍斯卡特·威特瑞」的一部分），
所以命中要人眼过一遍 —— 脚本只负责把候选连同行号列出来。

用法: python name_leak.py <TSV 目录> <详细输出.txt>
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


def main() -> int:
    root = Path(sys.argv[1])
    out = Path(sys.argv[2])
    dev = load(root / "dev-zh-s.tsv")
    tpl = load(root / "template-zh-s.tsv")
    tpl_lines = (root / "template-zh-s.tsv").read_text(encoding="utf-8").splitlines()

    # 人名（含简称）→ 来源 key
    names: dict[str, str] = {}
    for k, v in dev.items():
        if not k.startswith("crew_name_"):
            continue
        for part in v.split("|"):
            part = part.strip()
            if len(part) >= 2:
                names.setdefault(part, k)

    hits: list[tuple[int, str, str, str]] = []
    for i, line in enumerate(tpl_lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        key, _, val = line.partition("\t")
        if key.startswith("crew_name_"):
            continue
        for name, src in names.items():
            if name in val:
                hits.append((i, key, name, src))

    print("检查了 %d 个人名（含简称），模板 %d 行" % (len(names), len(tpl_lines)))
    print("crew_name_* 之外的命中 = %d" % len(hits))
    for i, key, name, src in hits:
        print("  L%-4d %-30s <- %s (%s)" % (i, key, name, src))

    rep = ["候选漏网（模板 key 不是 crew_name_，但值里出现了某个人名）", ""]
    for i, key, name, src in hits:
        rep.append("L%-4d %-30s 命中 %-14s 来自 %s" % (i, key, name, src))
        rep.append("       值 = %r" % tpl[key])
    out.write_text("\n".join(rep), encoding="utf-8")
    print("detail -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
