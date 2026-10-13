# -*- coding: utf-8 -*-
"""检查 `CN_Refined/weirdFonts/` 里那两份替换字体，能否**完全覆盖**我们现在的子集。

判定要两层（851 那次的教训：cmap 里有码位 ≠ 画得出墨迹）：
  ① 码位在不在 cmap 里
  ② FreeType 真渲染，有没有墨迹

对照口径：
  · 必测集合 = `make_subset_fonts.collect_chars()`（20 个语言包 + 游戏 14 包 + 官方包 +
    标点/ASCII 保险 + C# 字面量 + assets 二进制 + shs6 鸣谢），当前 **3225 字**
  · 同时逐字比「**我们现在的字体画得出的字** vs 新字体画得出的字」→ 差集就是真正的缺口
  · 另外单独点名关键串（语言菜单名、鸣谢里的名字）与全部人名串

用法: python CN_Refined\\assets\\check_weird_fonts.py
产物: CN_Refined\\assets\\out\\weirdfonts.txt
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NEWDIR = ROOT / "CN_Refined" / "weirdFonts"
VER = HERE / "out" / "verify"

# (替换目标, 新字体, 我们现在那支成品子集)
PAIRS = [
    ("思源宋体(正文)", NEWDIR / "郑庆科南北词宫谱宋体.ttf",
     VER / "SourceHanSerif-SemiBold.otf"),
    ("851tegaki(手写)", NEWDIR / "乐米拾光手札体.ttf",
     VER / "851tegaki_zatsu_normal_0883.otf"),
]

sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402

lines: list[str] = []
CRIT = ["日本語", "简体中文", "繁體中文", "奥伯拉丁号", "下落", "申诉", "理赔",
        "翼德大大", "奥伯拉丁", "保险", "调查员", "船员", "船长", "女士", "先生"]
NAME_TABLE = ROOT / "CN_Refined" / "langpack" / "extracted" / "crew_name_variants.tsv"


def say(m: str = "") -> None:
    lines.append(m)


def font_info(p: Path) -> dict:
    f = TTFont(str(p), lazy=True)
    cmap: dict[int, str] = {}
    for t in f["cmap"].tables:
        try:
            cmap.update(t.cmap)
        except Exception:                                  # noqa: BLE001
            pass
    info = {
        "sfnt": f.sfntVersion.strip(),
        "upem": f["head"].unitsPerEm,
        "glyphs": f["maxp"].numGlyphs,
        "cmap": cmap,
        "tables": sorted(f.keys()),
        "family": None, "ps": None,
        "cp1": None,
    }
    if "name" in f:
        for rec in f["name"].names:
            if rec.platformID != 3:
                continue
            if rec.nameID == 1:
                info["family"] = rec.toUnicode()
            elif rec.nameID == 6:
                info["ps"] = rec.toUnicode()
    if "OS/2" in f:
        info["cp1"] = f["OS/2"].ulCodePageRange1
    f.close()
    return info


def coverage(path: Path, chars: list[str]) -> tuple[set[str], list[str], list[str]]:
    """能真的画出来的字符 → (ok, 无码位, 有码位但空字形)

    ⚠ 不要用 PIL 渲染去判（踩过）：不少中文字体的 `.notdef` 是**可见方框**，
      缺字时会画出一个方框 → PIL 以为「有墨迹」，把缺字误报成覆盖。
      851tegaki 的 `.notdef` 恰好空白，所以那个方向又会把「有码位但画不出」误报成缺。
    正解：码位在不在 cmap；在的话那个字形**有没有轮廓点**（BoundsPen 求 bounds）。
    """
    f = TTFont(str(path), lazy=True)
    cmap: dict[int, str] = {}
    for t in f["cmap"].tables:
        try:
            cmap.update(t.cmap)
        except Exception:                                  # noqa: BLE001
            pass
    gs = f.getGlyphSet()
    ok: set[str] = set()
    nocmap: list[str] = []
    blank: list[str] = []
    for c in chars:
        g = cmap.get(ord(c))
        if not g:
            nocmap.append(c)
            continue
        pen = BoundsPen(gs)
        try:
            gs[g].draw(pen)
        except Exception:                                  # noqa: BLE001
            blank.append(c)
            continue
        if pen.bounds is None:
            blank.append(c)
        else:
            ok.add(c)
    f.close()
    return ok, nocmap, blank


def kind(c: str) -> str:
    o = ord(c)
    if o < 0x80:
        return "ASCII"
    if 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF or o in (0x2018, 0x2019, 0x201C, 0x201D,
                                                              0x2013, 0x2014, 0x2026, 0x00B7,
                                                              0x3001, 0x3002, 0x00A3):
        return "标点/符号"
    if MS.CJK_CHAR(c):
        return "CJK"
    if 0x3040 <= o <= 0x30FF:
        return "日文假名"
    if 0xAC00 <= o <= 0xD7AF:
        return "谚文"
    return "其它"


def main() -> int:
    charset, _ = MS.collect_chars()
    req = sorted(c for c in charset if not c.isspace())
    say("weirdFonts 替换字体 —— 覆盖面检查")
    say("=" * 100)
    say("必测集合 %d 字（= make_subset_fonts.collect_chars()）" % len(req))
    say("")

    # 人名串里的字（单独看一眼，用户很在意）
    names = ""
    if NAME_TABLE.exists():
        names = "\n".join(l for l in NAME_TABLE.read_text(encoding="utf-8-sig").splitlines()
                          if l and not l.startswith("#"))
    name_chars = sorted({c for c in names if not c.isspace() and not c.isascii()})
    say("人名表里的非 ASCII 字 %d 个" % len(name_chars))
    say("")

    for label, new, ours in PAIRS:
        say("-" * 100)
        say("【%s】" % label)
        if not new.exists():
            say("  ✗ 缺新字体 %s" % new)
            continue
        if not ours.exists():
            say("  ⚠ 缺我们现有子集 %s（先跑 check_fonts.py）" % ours)
        ni = font_info(new)
        say("  新字体 %s" % new.name)
        say("    %.2f MB  sfnt=%s  upem=%d  %d 字形  cmap %d 码位"
            % (new.stat().st_size / 1048576, ni["sfnt"], ni["upem"], ni["glyphs"], len(ni["cmap"])))
        say("    family=%r  postscript=%r  OS/2 码页位1=0x%04X%s"
            % (ni["family"], ni["ps"], ni["cp1"] or 0,
               "（含简体中文 bit18 ✓）" if (ni["cp1"] or 0) & (1 << 18) else "（**无** bit18 简体中文）"))
        say("    表: %s" % " ".join(ni["tables"]))

        # 1) cmap 覆盖
        new_ink, nocmap, blank_glyph = coverage(new, req)
        if not new_ink and not nocmap and not blank_glyph:
            say("  ✗ 无法解析字体")
            continue

        def by_kind(lst):
            d: dict[str, list[str]] = {}
            for c in lst:
                d.setdefault(kind(c), []).append(c)
            return "  ".join("%s %d" % (k, len(v)) for k, v in sorted(d.items()))

        say("")
        say("  【cmap 里没有】    %d 字   %s" % (len(nocmap), by_kind(nocmap) or "-"))
        if nocmap:
            say("      %s" % "".join(nocmap[:80]))
        say("  【有码位但字形空】 %d 字   %s" % (len(blank_glyph), by_kind(blank_glyph) or "-"))
        if blank_glyph:
            say("      %s" % "".join(blank_glyph[:80]))

        # 3) 与我们现在那支比：我们画得出的，新字体画不出 = 真缺口
        if ours.exists():
            ours_ink, _, _ = coverage(ours, req)
            gap = [c for c in req if c in ours_ink and c not in new_ink]
            say("")
            say("  【真缺口】我们现有子集画得出、新字体画不出的字: **%d** 字   %s"
                % (len(gap), by_kind(gap) or "-"))
            if gap:
                say("      %s" % "".join(gap[:120]))
            extra = [c for c in req if c not in ours_ink and c in new_ink]
            say("  （反向：我们画不出、新字体画得出的 %d 字，属新增覆盖，不是问题）" % len(extra))

        # 4) 点名关键串
        say("")
        bad_crit = []
        for s in CRIT:
            miss = [c for c in s if c not in new_ink]
            if miss:
                bad_crit.append("%s(缺 %s)" % (s, "".join(miss)))
        say("  关键串: %s" % ("全部可渲染 ✓" if not bad_crit else "✗ " + "; ".join(bad_crit)))
        bad_name = [c for c in name_chars if c not in new_ink]
        say("  人名用字: %s" % ("%d 字全部可渲染 ✓" % len(name_chars) if not bad_name
                              else "✗ 缺 %s" % "".join(bad_name)))

        # 5) 缺的字里有没有「本来就不该有」的（不可打印 / 装饰）
        unprintable = [c for c in list(nocmap) + list(blank_glyph)
                       if unicodedata.category(c).startswith("C") or c in " \u3000"]
        if unprintable:
            say("  其中控制/空白类（可忽略）: %s" % "".join(unprintable))
        say("")

    say("=" * 100)
    per_language()
    say("")
    say("=" * 100)
    (HERE / "out" / "weirdfonts.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


def pack_chars(p: Path) -> set[str]:
    """语言包 TSV（langtool export 格式：首行 # 注释，之后 key<TAB>value，值里转义）"""
    out: set[str] = set()
    for ln in p.read_text(encoding="utf-8-sig").splitlines():
        if not ln or ln.startswith("#") or "\t" not in ln:
            continue
        val = ln.split("\t", 1)[1]
        for a, b in (("\\n", "\n"), ("\\t", "\t"), ("\\\\", "\\")):
            val = val.replace(a, b)
        out |= {c for c in val if not c.isspace()}
    return out


def per_language() -> None:
    """逐语言包量：新字体在这个包里有多少字画不出来 → 该语言的「字体回落率」"""
    lpd = HERE / "out" / "langpacks"
    built = ROOT / "CN_Refined" / "out" / "packs"
    say("")
    say("=" * 100)
    say("逐语言包：新字体画不出的字（这些字会回落系统字体）")
    say("=" * 100)
    for label, new, ours in PAIRS:
        if not new.exists():
            continue
        say("")
        say("【%s】%s" % (label, new.name))
        new_ink, _nc, _bg = coverage(new, sorted({c for p in lpd.glob("*.tsv") for c in pack_chars(p)}
                                                 | {c for p in built.glob("*.tsv") for c in pack_chars(p)}))
        ours_ink: set[str] = set()
        if ours.exists():
            ours_ink, _, _ = coverage(ours, sorted({c for p in lpd.glob("*.tsv") for c in pack_chars(p)}))
        say("  %-10s %-8s %-8s %-8s %s" % ("包", "去重字", "新字体缺", "占缺比例", "我们现有字体缺"))
        for p in sorted(lpd.glob("*.tsv")):
            ch = pack_chars(p)
            miss = sorted(c for c in ch if c not in new_ink)
            mine = sorted(c for c in ch if c not in ours_ink) if ours_ink else []
            say("  %-10s %-8d %-8d %-8s 我们缺: %-3d %-14s %s"
                % (p.stem, len(ch), len(miss),
                   "%.1f%%" % (100.0 * len(miss) / max(len(ch), 1)),
                   len(mine), "".join(mine[:12]),
                   ("  新缺: " + "".join(miss[:20])) if miss else ""))
        bl = sorted(built.glob("zh-s-*.tsv"))
        if bl:
            worst, best = 0, 10 ** 9
            for p in bl:
                ch = pack_chars(p)
                m = len([c for c in ch if c not in new_ink])
                worst = max(worst, m)
                best = min(best, m)
            say("  %-10s %d 个包：单包缺字 最多 %d / 最少 %d  ← 我们自制的 20 个中文包"
                % ("自制中文包", len(bl), worst, best))


if __name__ == "__main__":
    sys.exit(main())
