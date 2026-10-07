#!/usr/bin/env python3
"""逐「格」比对模板与参照包，判断哪些 key 还没处理完。

模板里很多值是 `A|B` 这种两格结构（如 crew_name_* 的 `全名|简称`）。
本脚本对指定前缀的每个 key，把各包的格子拆开，只输出 ASCII 的布尔状态 ——
不用看中文就能知道「第一格是不是已经换成 [Token]、第二格是否还等于 dev/官方」。

用法: python slot_state.py <目录> <key 前缀>
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
    return (a, b if sep else "")


def is_tok(s: str) -> str:
    return "Y" if s.startswith("[") and s.endswith("]") else "-"


def main() -> int:
    root = Path(sys.argv[1])
    prefix = sys.argv[2]

    packs = {p.stem: load(p) for p in sorted(root.glob("*.tsv"))}
    tpl = packs.get("template-zh-s", {})
    dev = packs.get("dev-zh-s", {})
    off = packs.get("original-zh-s", {})

    keys = [k for k in tpl if k.startswith(prefix)]
    print("%-30s %s" % ("key", "tpl1 tpl2 | s1==dev s1==off | s2==dev s2==off | en-slots"))
    unfinished = []
    for k in keys:
        t1, t2 = slots(tpl.get(k))
        d1, d2 = slots(dev.get(k))
        o1, o2 = slots(off.get(k))
        row = "%-30s %s%s   |   %s      %s     |   %s      %s     | %s" % (
            k, is_tok(t1), is_tok(t2),
            "Y" if t1 == d1 else "-", "Y" if t1 == o1 else "-",
            "Y" if t2 == d2 else "-", "Y" if t2 == o2 else "-",
            "2" if t2 else "1")
        print(row)
        if is_tok(t1) != "Y":
            unfinished.append(k)
    print("")
    print("keys=%d  slot1 还是裸文本（未换 Token）的 = %d" % (len(keys), len(unfinished)))
    if unfinished:
        print("未完成: " + ", ".join(unfinished))
    return 0


if __name__ == "__main__":
    sys.exit(main())
