# -*- coding: utf-8 -*-
"""定位：替换字体缺的字**落在哪些词条**上（只看我们自制的简体中文包）。

比只看"缺 N 字"有用得多：能一眼看出缺的是「语言菜单里的外文」还是「正文里的汉字」。

用法: python CN_Refined\\assets\\_q_weird_hits.py [包名]
默认包: zh-s-v1-harm-bi.tsv
产物: CN_Refined\\assets\\out\\weirdhits.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NEWDIR = ROOT / "CN_Refined" / "weirdFonts"
PACKS = ROOT / "CN_Refined" / "out" / "packs"

sys.path.insert(0, str(HERE))
import check_weird_fonts as CW  # noqa: E402

FONTS = [("宋体替换 郑庆科南北词宫谱宋体", NEWDIR / "郑庆科南北词宫谱宋体.ttf"),
         ("手写体替换 乐米拾光手札体", NEWDIR / "乐米拾光手札体.ttf")]
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def parse(p: Path) -> list[tuple[str, str]]:
    out = []
    for ln in p.read_text(encoding="utf-8-sig").splitlines():
        if not ln or ln.startswith("#") or "\t" not in ln:
            continue
        k, v = ln.split("\t", 1)
        for a, b in (("\\n", "\n"), ("\\t", "\t"), ("\\\\", "\\")):
            v = v.replace(a, b)
        out.append((k, v))
    return out


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "zh-s-v1-harm-bi.tsv"
    p = PACKS / name
    if not p.exists():
        say("✗ 缺包 %s" % p)
        (HERE / "out" / "weirdhits.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    kv = parse(p)
    allchars = sorted({c for _k, v in kv for c in v if not c.isspace()})
    say("词条命中定位：%s（%d 个词条，去重非空白字 %d）" % (name, len(kv), len(allchars)))
    say("=" * 96)
    for label, path in FONTS:
        ok, nocmap, blank = CW.coverage(path, allchars)
        miss = set(nocmap) | set(blank)
        say("")
        say("【%s】缺 %d 字（其中汉字 %d、非汉字 %d）"
            % (label, len(miss),
               sum(1 for c in miss if CW.MS.CJK_CHAR(c)),
               sum(1 for c in miss if not CW.MS.CJK_CHAR(c))))
        hits = [(k, sorted(set(v) & miss)) for k, v in kv if set(v) & miss]
        say("  命中词条 %d 个：" % len(hits))
        for k, ch in hits[:45]:
            v = dict(kv)[k]
            say("    %-34s 缺 %-14s  %s" % (k, "".join(ch), v[:46].replace("\n", "⏎")))
        if len(hits) > 45:
            say("    …另有 %d 个词条" % (len(hits) - 45))
        # 汉字缺口单独总结
        cjk_hits = [(k, [c for c in ch if CW.MS.CJK_CHAR(c)]) for k, ch in hits]
        cjk_hits = [(k, ch) for k, ch in cjk_hits if ch]
        if cjk_hits:
            say("  ★ **缺汉字**的 %d 个词条（这些位置的汉字会出问题）：" % len(cjk_hits))
            for k, ch in cjk_hits[:30]:
                say("    %-34s 缺 %s" % (k, "".join(ch)))
        else:
            say("  ★ 没有缺任何汉字 ✓（缺的全是外文/标点，只出现在语言菜单或原文行）")
    (HERE / "out" / "weirdhits.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
