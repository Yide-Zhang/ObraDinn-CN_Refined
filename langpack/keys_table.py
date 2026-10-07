#!/usr/bin/env python3
"""把指定 key（或按前缀匹配）在几个 lang-*.tsv 里的值并排打印，一行一个 key。

用法:
    python keys_table.py <目录> <key 或 前缀> [更多 key...]

例:
    python keys_table.py CN_Refined\\langpack\\extracted crew_name_

目录里所有 *.tsv 都会被读进来，列顺序固定为 en / 官方简体 / dev / 模板（有哪个列哪个）。
stdout 是给控制台看的（中文会乱码）—— 重定向到文件再读。
"""
from __future__ import annotations

import sys
from pathlib import Path

#: 列顺序：看得懂的先后
ORDER = ("original-en", "original-zh-s", "dev-zh-s", "template-zh-s")


def unescape(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append({"\\": "\\", "n": "\\n", "t": "\\t", "r": "\\r"}.get(s[i + 1],
                                                                           s[i + 1]))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        k, _, v = line.partition("\t")
        d[k] = v          # 保留转义形态，和源文件一致，便于比对
    return d


def main() -> int:
    root = Path(sys.argv[1])
    pats = sys.argv[2:]
    if not pats:
        print("用法: keys_table.py <目录> <key 或 前缀> [更多...]")
        return 2

    packs: dict[str, dict[str, str]] = {}
    for p in sorted(root.glob("*.tsv")):
        packs[p.stem] = load(p)
    cols = [c for c in ORDER if c in packs] + [c for c in sorted(packs) if c not in ORDER]

    keys: list[str] = []
    for pat in pats:
        if pat in packs.get(cols[0], {}) or any(pat in packs[c] for c in cols):
            keys.append(pat)
        else:
            for c in cols:
                for k in packs[c]:
                    if k.startswith(pat) and k not in keys:
                        keys.append(k)

    print("列: " + " | ".join(cols))
    for k in keys:
        print("=" * 100)
        print("KEY: " + k)
        for c in cols:
            v = packs[c].get(k)
            print("  %-14s %s" % (c, "(缺失)" if v is None else v))
    print("=" * 100)
    print("keys=%d" % len(keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
