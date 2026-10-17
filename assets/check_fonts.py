# -*- coding: utf-8 -*-
"""成品字体的独立验证：从**产出的 assets** 里抠出字体，交给 FreeType（PIL）真实光栅化。

Unity 的动态字体运行时用 FreeType 解析 m_FontData，所以这一步比 fontTools 更接近真实行为：
  · FreeType 能不能打开（格式/子程序是否有效）
  · 字符集里每个 CJK 字能否真的渲染出墨迹（不是空白/异常）

用法: python CN_Refined\\assets\\check_fonts.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import UnityPy
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402
import inject_fonts as INJ  # noqa: E402  ★ 字体源与注入脚本共用一处，别各写一份

ROOT = HERE.parents[1]
PROD = ROOT / "CN_Refined" / "out" / "assets"
ORIGF = HERE / "out" / "fonts"
TMP = HERE / "out" / "verify"
REPORT = HERE / "out" / "check_fonts.txt"

TARGETS = {"sharedassets0.assets": "SourceHanSerif-SemiBold",
           "sharedassets2.assets": "851tegaki_zatsu_normal_0883"}

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def has_ink(font, c: str) -> bool:
    img = Image.new("L", (48, 48), 0)
    ImageDraw.Draw(img).text((6, 6), c, font=font, fill=255)
    return img.getbbox() is not None


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    charset, _ = MS.collect_chars()
    chars = sorted(c for c in charset if MS.CJK_CHAR(c))
    say("成品字体 FreeType 实测")
    say("=" * 84)
    say("  待测 CJK 字符 %d 个" % len(chars))
    say("")
    ok = True

    for fn, fname in TARGETS.items():
        p = PROD / fn
        if not p.exists():
            say("✗ 缺成品 %s" % p)
            ok = False
            continue
        say("%s" % fn)
        env = UnityPy.load(str(p))
        data = None
        want: list = []
        for o in env.objects:
            if o.type.name != "Font":
                continue
            d = o.read()
            if getattr(d, "m_Name", "") == fname:
                data = bytes(d.m_FontData)
                want = list(getattr(d, "m_FontNames", []) or [])
        if data is None:
            say("  ✗ 找不到字体 %s" % fname)
            ok = False
            continue
        ext = MS.sniff_ext(data) if hasattr(MS, "sniff_ext") else "otf"
        f = TMP / ("%s.%s" % (fname, ext))
        f.write_bytes(data)
        say("  fontData %s → %s" % ("%.2f MB" % (len(data) / 1048576), f.name))

        # 1) fontTools 复核
        tt = TTFont(str(f), lazy=True)
        cmap: set[int] = set()
        for t in tt["cmap"].tables:
            cmap |= set(t.cmap.keys())
        say("  fontTools: cmap %d 码位 / %d 字形" % (len(cmap), tt["maxp"].numGlyphs))
        tt.close()

        # 2) 必测集合 = **字体源画得出墨迹**的字符
        #    ⚠ 基准必须是**实际用的字体源**（`inject_fonts.JOBS`）：
        #      正文用 font_src 的 SC 版（不是抠出来的游戏原字体 —— 字形不同）；
        #      手写体用根目录 `851tegakizatsu-Regular.otf`（2026-10-17 起换成用户翻新的那支；
        #      也不是游戏内嵌那份 —— 21 个字不同）
        #    ⚠ 不能用「cmap 里有没有」—— 851tegaki 的 cmap 声称有阿拉伯文/天城文/谚文，
        #    但画出来是空白（不是它能渲染的东西），用 cmap 判会误报。
        orig = INJ.SOURCE_BY_FONT.get(fname)
        must: list[str] = []
        if orig.exists():
            ofont = ImageFont.truetype(str(orig), 24)
            must = [c for c in sorted(charset) if not c.isspace() and has_ink(ofont, c)]
            say("  原字体有墨迹的字 %d 个 —— 子集必须全都能" % len(must))
        else:
            say("  ⚠ 找不到原字体 %s，退化为只查 CJK 区" % orig)
            must = sorted(c for c in charset if MS.CJK_CHAR(c))
        try:
            font = ImageFont.truetype(str(f), 24)
        except Exception as e:                            # noqa: BLE001
            say("  ✗ FreeType 打不开: %s: %s" % (type(e).__name__, e))
            ok = False
            continue
        blank, err = [], []
        for c in must:
            try:
                if not has_ink(font, c):
                    blank.append(c)
            except Exception as e:                        # noqa: BLE001
                err.append("%s(%s)" % (c, type(e).__name__))
        say("  FreeType : 渲染 %d 字 →  空白 %d  异常 %d%s"
            % (len(must), len(blank), len(err),
               ("   空白: " + "".join(blank[:24])) if blank else ""))
        if err:
            say("     异常例: %s" % ", ".join(err[:10]))
        ok &= (not blank and not err)
        # 3) ★ 回归检查：cmap 子表结构 与 OS/2 码页位 是否被 fontTools 剪掉了
        #    这两处被剪 → Unity 判定字体不可用 → **全部文字回落系统字体（微软雅黑）**
        #    （2026-10-06 踩过；Mac 平台 platformID=1 的遗留子表不要求保留）
        if orig.exists():
            tf = TTFont(str(f), lazy=True)
            ts = TTFont(str(orig), lazy=True)

            def shape(x):
                return sorted((t.platformID, t.platEncID, t.format)
                              for t in x["cmap"].tables if t.platformID != 1)

            shs_, shp_ = shape(ts), shape(tf)
            miss = [x for x in shs_ if x not in shp_]
            try:
                bit = bool(tf["OS/2"].ulCodePageRange1 & (1 << 18))
            except Exception:                              # noqa: BLE001
                bit = False
            say("  cmap 子表 源=%s" % shs_)
            say("            子集=%s   缺=%s" % (shp_, miss if miss else "无 ✓"))
            say("  OS/2 简体中文码页位(bit18) = %s   %s"
                % (bit, "✓" if bit else "✗ **会回落系统字体**"))
            tf.close()
            ts.close()
            if miss or not bit:
                say("  ✗ 缺了源字体的 cmap 子表 / 码页位声明 —— 检查 restore_like_source()")
                ok = False
        # 3.5) ★ 回归检查：身份名必须能对上 Font 对象的 m_FontNames
        #      Unity 加载 m_FontData 后用字体内部 family 名去对 m_FontNames
        #      （CFF 字体看 CFF top dict 的 FamilyName，glyf 看 name ID1，再退 postscript 名）；
        #      对不上就丢弃整支字体 → **全游戏中文回落系统字体（微软雅黑）**
        #      （2026-10-06 踩过：换了 SC 字体源，family 变成 'Source Han Serif Simplified Chinese'）
        tj = TTFont(str(f), lazy=True)
        idf = MS.identity_of(tj)
        tj.close()
        cand = [idf["cff_family"], idf["name1"], idf["cff_font"], idf["name6"]]
        hit = next((c for c in cand if c and c in want), None)
        say("  身份名校验 m_FontNames=%s" % want)
        say("             family=%r name1=%r name6=%r → %s"
            % (idf["cff_family"], idf["name1"], idf["name6"],
               ("命中 %r ✓" % hit) if hit else "✗ 对不上，Unity 会回落系统字体"))
        if not hit:
            ok = False
        # 4) 抽样渲染一张图，肉眼可看
        sample = "奥伯拉丁号船员下落判决书索赔保险调查员明叔箱仔简伯德小姐"
        sheet = Image.new("L", (len(sample) * 26 + 8, 40), 255)
        dr = ImageDraw.Draw(sheet)
        for i, c in enumerate(sample):
            dr.text((4 + i * 26, 6), c, font=font, fill=0)
        sheet.save(TMP / ("sample-%s.png" % fname))
        say("  抽样图: %s" % (TMP / ("sample-%s.png" % fname)))
        say("")

    say("=" * 84)
    say("FreeType 逐字渲染全部通过 ✓" if ok else "⚠ 有问题，见上")
    text = "\n".join(lines)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
