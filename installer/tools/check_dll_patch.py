# -*- coding: utf-8 -*-
"""把「我们自己打的难度补丁」与 hardcore 的预编译基准逐字节比。

    python CN_Refined\\installer\\tools\\check_dll_patch.py

比什么：
  1) 尺寸 / sha256
  2) 首个与全部差异区段（起止偏移 + 长度），并列出差异区段里前后各若干字节
  3) 规格里的锚点 `11 06 1a 3b 08 00 00 00 11 06 18 40` 出现几次、紧邻其前是什么字节
     —— 原版应当是 `19`(=ldc.i4.3)，58 档应当是 `1f 3a`(=ldc.i4.s 58)

结论写成 out/dllpatch.txt（utf-8-sig；控制台是 GBK，中文会乱）。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
CR = ROOT / "CN_Refined"
OUT = PKG / "out"

VANILLA = CR / "originalassets" / "_gamebackup-20261006-220426" / "Assembly-CSharp.dll"
MINE = OUT / "lv58-only.dll"
BASE = ROOT / "hardcore" / "_patched" / "lc-lv58.dll"
ANCHOR = bytes.fromhex("11061a3b080000 0011061840".replace(" ", ""))

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def diff_runs(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """返回 [(start, end)]，长度不同的尾部也算一段"""
    n = min(len(a), len(b))
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    if len(a) != len(b):
        runs.append((n, max(len(a), len(b))))
    return runs


def anchor_info(tag: str, data: bytes) -> None:
    at = []
    i = data.find(ANCHOR)
    while i >= 0:
        at.append(i)
        i = data.find(ANCHOR, i + 1)
    say("  %s: 锚点出现 %d 次 %s" % (tag, len(at), [hex(x) for x in at]))
    for off in at:
        pre = data[max(0, off - 4):off]
        say("      @%s 锚点前 4 字节 = %s   （原版应为 ...19，58 档应为 ...1f 3a）"
            % (hex(off), pre.hex(" ")))


def main() -> int:
    for p, tag in ((VANILLA, "原版"), (MINE, "我们打 lv58"), (BASE, "hardcore 基准 lv58")):
        say("%-20s %s  %s  %s" % (tag, p.name, p.stat().st_size if p.is_file() else "缺失",
                                  sha(p)[:16] if p.is_file() else ""))
    if not (VANILLA.is_file() and MINE.is_file()):
        say("✗ 缺文件，无法比对")
        return 1
    v = VANILLA.read_bytes()
    m = MINE.read_bytes()
    say("")
    say("锚点定位（用于确认档位常量真的换了）")
    anchor_info("原版", v)
    anchor_info("我们打 lv58", m)
    if BASE.is_file():
        b = BASE.read_bytes()
        anchor_info("hardcore 基准 lv58", b)
        say("")
        say("我们 vs hardcore 基准")
        say("  sha: %s  vs  %s  %s"
            % (hashlib.sha256(m).hexdigest()[:16], hashlib.sha256(b).hexdigest()[:16],
               "完全一致 ✓" if m == b else "不一致 ✗"))
        say("  尺寸: %d vs %d （差 %+d）" % (len(m), len(b), len(m) - len(b)))
        runs = diff_runs(m, b)
        say("  差异区段 %d 段（总计 %d 字节）"
            % (len(runs), sum(e - s for s, e in runs)))
        for s, e in runs[:12]:
            say("    @0x%08X..0x%08X (%d B)" % (s, e, e - s))
            say("       ours: %s" % m[s:min(e, s + 24)].hex(" "))
            say("       base: %s" % b[s:min(e, s + 24)].hex(" "))
        if len(runs) > 12:
            say("    ... 还有 %d 段" % (len(runs) - 12))
        say("")
        say("我们 vs 原版：差异 %d 段（应含 A/B1/B2/C 四处）"
            % len(diff_runs(v, m)))
        say("基准 vs 原版：差异 %d 段" % len(diff_runs(v, b)))
    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / "dllpatch.txt"
    rp.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("报告: %s" % rp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
