# -*- coding: utf-8 -*-
"""诊断：某些字符到底来自哪一路来源（判断是"真文本"还是"二进制噪声"）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402

ROOT = HERE.parents[1]
EX = ROOT / "CN_Refined" / "langpack" / "extracted"
PACKS = ROOT / "CN_Refined" / "out" / "packs"
OLD = ROOT / "CN_Refined" / "olddevassets"
ORIG = ROOT / "CN_Refined" / "originalassets"

SUSPECT = "㨟㨠㫚䃓䅘䞡䨥䨦䨧䨿䲧䲨"


def from_text(paths) -> set[str]:
    out: set[str] = set()
    for p in paths:
        out |= set(p.read_bytes().decode("utf-8-sig", "ignore"))
    return out


def main() -> int:
    srcs = {}
    srcs["20 个语言包"] = from_text(sorted(PACKS.glob("*.tsv")))
    srcs["官方中英包"] = from_text([EX / "original-zh-s.tsv", EX / "original-en.tsv"])
    srcs["模板"] = from_text([EX / "template-zh-s.tsv"])
    srcs["C# 字面量"] = set()
    for p in (ROOT / "css" / "Assembly-CSharp").rglob("*.cs"):
        srcs["C# 字面量"] |= MS.scan_cs(p)
    srcs["shs6(原始)"] = MS.scan_bytes(ORIG / "sharedassets6.assets")
    srcs["shs6(你的)"] = MS.scan_bytes(OLD / "sharedassets6.assets")
    srcs["shs0 大二进制"] = MS.scan_bytes(ORIG / "sharedassets0.assets")
    srcs["shs2 大二进制"] = MS.scan_bytes(ORIG / "sharedassets2.assets")

    out = ["字符来源诊断", "=" * 70]
    out.append("每个可疑字符出现在哪些来源里：")
    for c in SUSPECT:
        hit = [k for k, v in srcs.items() if c in v]
        out.append("  %s  U+%04X   ← %s" % (c, ord(c), "、".join(hit) if hit else "（都没有？）"))

    out.append("")
    out.append("各来源的字符数：")
    for k, v in srcs.items():
        out.append("  %-16s %5d 个（CJK %d）" % (k, len(v), MS.cjk_count(v)))

    # 只看「大二进制」独有的字符（= 噪声嫌疑）
    big = srcs["shs0 大二进制"] | srcs["shs2 大二进制"]
    real = (srcs["20 个语言包"] | srcs["官方中英包"] | srcs["模板"]
            | srcs["C# 字面量"] | srcs["shs6(原始)"] | srcs["shs6(你的)"])
    noise = big - real
    out.append("")
    out.append("只在「大二进制」里出现的字符（噪声嫌疑）: %d 个" % len(noise))
    out.append("  CJK 区里的是: %s" % "".join(sorted(c for c in noise if MS.CJK_CHAR(c))[:80]))
    out.append("")
    out.append("真文本来源需要的 CJK 字符数: %d"
               % MS.cjk_count(real))

    text = "\n".join(out)
    (HERE / "out" / "diag_chars.txt").write_text(text + "\n", encoding="utf-8-sig")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
