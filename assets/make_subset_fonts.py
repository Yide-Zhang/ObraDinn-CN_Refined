# -*- coding: utf-8 -*-
"""字体子集化实验：从「游戏自带的原始字体」出发，切出够用的字符集，比较几种压缩档位。

★ 关键：**保持原格式**（SourceHanSerif 是 OTF/CFF、851tegaki 是 TTF/glyf），
  并且 **绝不 desubroutinize**（旧产物 82MB 就是被展平 CFF 子程序撑爆的）。

字符集来源（游戏能显示的中文只可能来自这些）：
  1. 我们构建出的全部 20 个语言包（最终出货文本）
  2. 官方中文包（保险）
  3. ASCII 可打印 + 常用中文标点/符号（数字、金额、书名号、省略号…）

用法: python CN_Refined\\assets\\make_subset_fonts.py
产物: CN_Refined\\assets\\out\\subset\\*.otf|ttf  +  CN_Refined\\assets\\out\\subset.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTDIR = HERE / "out"
SDIR = OUTDIR / "subset"
PACKS = ROOT / "CN_Refined" / "out" / "packs"
EX = ROOT / "CN_Refined" / "langpack" / "extracted"
REPORT = OUTDIR / "subset.txt"

# 要处理的字体： (原始字体文件, 输出名, 说明)
FONTS = [
    ("orig-SourceHanSerif-SemiBold.otf", "SourceHanSerif-SemiBold",
     "正文字体（书页/菜单/名单）"),
    ("orig-851tegaki_zatsu_normal_0883.ttf", "851tegaki_zatsu_normal_0883",
     "手写体（序言/信件/理赔单）"),
]

# 额外保险字符：ASCII 可打印 + 常用中文标点/符号
EXTRA = "".join(chr(c) for c in range(0x20, 0x7F))
EXTRA += ("　，。、；：？！（）【】《》〈〉「」『』“”‘’…—～·×÷°£¥€$‰№"
          "－＝＋＜＞±§¶†‡●○◆◇■□▲△★☆→←↑↓↔ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
          "０１２３４５６７８９％＃＠＆＊（）［］｛｝；：，．！？")

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


# UTF-8 里的 CJK/全角区：E3–EF 开头的三字节序列，连续 ≥N 个才算真文本
# ⚠ 大二进制（字体/贴图）里随机字节也会凑出合法 UTF-8 —— 阈值调到 ≥6 才滤得掉噪声
#    （实测：shs0 用 ≥2 会多出 120 个假字符，其中 12 个连 851tegaki 都没有）
CJK_UTF8 = lambda n: re.compile(rb"(?:[\xe3-\xef][\x80-\xbf]{2}){%d,}" % n)  # noqa: E731
CJK_LIT = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def scan_bytes(p: Path, min_run: int = 2) -> set[str]:
    """从二进制里挖 UTF-8 中文串（≥min_run 连字）。"""
    out: set[str] = set()
    for m in CJK_UTF8(min_run).finditer(p.read_bytes()):
        out |= set(m.group(0).decode("utf-8", "ignore"))
    return out


def scan_cs(p: Path) -> set[str]:
    """从 C# 源码里挖字符串字面量里的中文。"""
    out: set[str] = set()
    txt = p.read_bytes().decode("utf-8", "ignore")
    for m in CJK_LIT.finditer(txt):
        out |= {c for c in m.group(0) if CJK_CHAR(c)}
    return out


def collect_chars() -> tuple[set[str], dict]:
    """-> (字符集合, 各来源统计)"""
    chars: set[str] = set()
    stat = {}
    packs = sorted(PACKS.glob("*.tsv"))
    for p in packs:
        for ln in p.read_bytes().decode("utf-8-sig").splitlines():
            if "\t" in ln:
                chars |= set(ln.split("\t", 1)[1])
    stat["20 个语言包"] = len(chars)

    # 2) ★ 游戏全部 14 个语言包 —— 同一套字体是**所有语言共用**的！
    #    （玩 zh-t/ja 会直接用这支字体；其它语言包里也有 88 个汉字 = 闽南语台词原文）
    n_lp = len(chars)
    lpdir = HERE / "out" / "langpacks"
    lps = sorted(lpdir.glob("*.tsv"))
    if len(lps) < 14:
        raise SystemExit("语言包只找到 %d 个（应为 14）—— 先跑 export_langpacks.py" % len(lps))
    for p in lps:
        for ln in p.read_bytes().decode("utf-8-sig", "ignore").splitlines():
            if "\t" in ln:
                chars |= set(ln.split("\t", 1)[1])
    stat["+ 游戏全部语言包(%d 个)" % len(lps)] = len(chars) - n_lp

    n0 = len(chars)
    for p in (EX / "original-zh-s.tsv", EX / "original-en.tsv"):
        if p.exists():
            for ln in p.read_bytes().decode("utf-8-sig").splitlines():
                if "\t" in ln:
                    chars |= set(ln.split("\t", 1)[1])
    stat["+ 官方中英包"] = len(chars) - n0

    n1 = len(chars)
    chars |= set(EXTRA)
    stat["+ 标点/ASCII 保险"] = len(chars) - n1

    # 4) DLL 源码里写死的中文（语言菜单名等）
    n2 = len(chars)
    cs = list((ROOT / "css" / "Assembly-CSharp").rglob("*.cs"))
    for p in cs:
        chars |= scan_cs(p)
    stat["+ C# 里的中文字面量(%d 文件)" % len(cs)] = len(chars) - n2

    # 5) assets 二进制里的中文串（含你改的本地化名字）
    #    shs6 很小且确实是文本 → ≥2 连字；shs0/shs2 是 28/34MB 字体贴图二进制 → ≥6 连字滤噪声
    n3 = len(chars)
    for p, mr in ((ROOT / "CN_Refined" / "olddevassets" / "sharedassets6.assets", 2),
                  (ROOT / "CN_Refined" / "originalassets" / "sharedassets6.assets", 2),
                  (ROOT / "CN_Refined" / "originalassets" / "sharedassets0.assets", 6),
                  (ROOT / "CN_Refined" / "originalassets" / "sharedassets2.assets", 6)):
        if p.exists():
            chars |= scan_bytes(p, mr)
    stat["+ assets 二进制里的中文"] = len(chars) - n3

    # 6) ★ shs6 里的**鸣谢文本** —— 既要能注入，注入后就**必须能显示**
    #    （含各语言译者的名字：繁中/韩文/日文…）
    n4 = len(chars)
    import inject_credits as IC                                    # noqa: PLC0415
    for p in (ROOT / "CN_Refined" / "olddevassets" / "sharedassets6.assets",
              ROOT / "CN_Refined" / "originalassets" / "sharedassets6.assets"):
        if p.exists():
            for e in IC.find_entries(p.read_bytes()):
                chars |= set(e[1]) | set(e[3])                    # ID 与文本
    stat["+ shs6 鸣谢文本"] = len(chars) - n4

    # 7) ★ 难度补丁会**写进游戏语言包**的中文数字（installer/data/difficulty.json）
    #    TSV 里那 4 个键（welldone_3_first/_more、help_faceclear_fates0/1）写死的是原版「三」，
    #    安装时引擎按玩家档位把它改写成「五十八」「二十九」……所以这些字**必须**在子集里。
    #    （2026-10-13 用户发现漏了：五/九/〇/百 都不在集里 ——
    #      硬核档 58 → 「五十八」的「五」、极难档 29 → 「二十九」的「九」在游戏里会回落系统字体）
    n5 = len(chars)
    dj = ROOT / "CN_Refined" / "installer" / "data" / "difficulty.json"
    if dj.exists():
        import json as _json                                    # noqa: PLC0415
        d = _json.loads(dj.read_text(encoding="utf-8"))
        chars |= set(d.get("num_chars", ""))
        for lv in d.get("levels", []):
            chars |= set(str(lv.get("zh", "")))
    stat["+ 难度数字(difficulty.json)"] = len(chars) - n5
    return chars, stat


def CJK_CHAR(c: str) -> bool:
    o = ord(c)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF


def cjk_count(chars: set[str]) -> int:
    return sum(1 for c in chars if CJK_CHAR(c))


OS2_RANGES = ("ulUnicodeRange1", "ulUnicodeRange2", "ulUnicodeRange3", "ulUnicodeRange4",
              "ulCodePageRange1", "ulCodePageRange2")


def restore_like_source(sub_font, src_path: Path) -> dict:
    """把 fontTools 剪掉的东西按**源字体**补回来 —— 这是让 Unity 接受的关键。

    实测（2026-10-06，用户报「字体全回落到微软雅黑」）：
      · fontTools 会把 `cmap` 子表剪成只剩 3 个，丢掉源字体里的
        **(0,4) fmt12 / (3,10) fmt12 / (1,1) fmt6**
      · 还会重算 `OS/2` 的 ulUnicodeRange / ulCodePageRange，
        **丢掉 bit18 = 简体中文(GB2312)** 这类"支持哪个码页"的声明
    两支能用的字体（游戏原始、用户 dev）都带着这些 → 推断 Unity 据此判断可用性。
    """
    import copy
    from fontTools.ttLib import TTFont, newTable
    src = TTFont(str(src_path), lazy=False)
    info = {}

    # 1) OS/2 的 Unicode/CodePage 位：直接照抄源字体
    if "OS/2" in sub_font and "OS/2" in src:
        s2, s1 = sub_font["OS/2"], src["OS/2"]
        for a in OS2_RANGES:
            if hasattr(s1, a):
                setattr(s2, a, getattr(s1, a))
        info["os2"] = "已照抄源字体"

    # 2) cmap：按源字体的「子表结构」重建，码位只保留子集有的，字形名用子集的
    sub_map: dict[int, str] = {}
    for t in sub_font["cmap"].tables:
        sub_map.update(t.cmap)
    newcmap = newTable("cmap")
    newcmap.tableVersion = 0
    newcmap.tables = []
    for t in src["cmap"].tables:
        if t.format == 14:
            continue                                  # fmt14(变体选择符) 用子集自己的
        cps = [cp for cp in t.cmap if cp in sub_map]
        if not cps:
            continue
        nt = copy.deepcopy(t)
        nt.cmap = {cp: sub_map[cp] for cp in cps}
        newcmap.tables.append(nt)
    for t in sub_font["cmap"].tables:
        if t.format == 14:
            newcmap.tables.append(t)
    sub_font["cmap"] = newcmap
    info["cmap"] = [(hex(t.platformID), hex(t.platEncID), t.format) for t in newcmap.tables]
    src.close()
    return info


def identity_of(font) -> dict:
    """字体对外声明的**身份名** —— Unity 加载 m_FontData 后拿它去对 Font 对象的 m_FontNames。

    · CFF 字体：FreeType 的 family_name 来自 CFF top dict 的 FamilyName
    · 有 name 表的：name ID 1(family) / 4(full) / 6(postscript)
    """
    out: dict = {"cff_font": None, "cff_family": None,
                 "name1": None, "name4": None, "name6": None}
    for k in ("CFF ", "CFF2"):
        if k in font:
            cff = font[k].cff
            out["cff_font"] = cff.fontNames[0] if cff.fontNames else None
            if cff.fontNames:
                top = cff[cff.fontNames[0]]
                out["cff_family"] = getattr(top, "FamilyName", None)
    if "name" in font:
        for rec in font["name"].names:
            if rec.platformID != 3 or rec.nameID not in (1, 4, 6):
                continue
            try:
                v = rec.toUnicode()
            except Exception:                             # noqa: BLE001
                v = None
            out["name%d" % rec.nameID] = v
    return out


def restore_identity(sub_font, donor_path: Path) -> dict:
    """把子集的**身份名**改成和游戏内嵌字体一模一样 —— Unity 认字体的第二条硬条件。

    实测（2026-10-06，用户两次报「还是旧字体 / 全回落到微软雅黑」）：
      游戏原始 Serif   CFF FamilyName = 'Source Han Serif'   ← Font 对象 m_FontNames=['Source Han Serif'] ✓
      用户 dev Serif   CFF FamilyName = 'Source Han Serif'   ✓（他取出字体改字形再放回，身份名没变）
      我的 SC 子集     CFF FamilyName = 'Source Han Serif Simplified Chinese'
                       name1          = 'Source Han Serif SC SemiBold'      ✗ 对不上
      → Unity 判定该字体不可用，全部中文回落到系统字体（中文 Windows = Microsoft YaHei）
      对照 851tegaki：name1 = '851tegakizatsu' == m_FontNames=['851tegakizatsu'] ✓ 正常

    这一条同时解释了用户遇到的两个现象：UABEA 直接替换也失败（同样对不上），
    而「把 shs 里的字体取出、改字形、再塞回」能成功（身份名保持原样）。
    注意 SourceHanSerif 的 Font 对象还被其它拉丁字体挂在 m_FallbackFonts 里，
    所以它一对不上，**全游戏的中文**都回落。
    """
    import copy
    from fontTools.ttLib import TTFont
    donor = TTFont(str(donor_path), lazy=False)
    before = identity_of(sub_font)

    # 1) CFF 身份字段与字体名：照抄 donor
    for k in ("CFF ", "CFF2"):
        if k in sub_font and k in donor:
            cff, dcff = sub_font[k].cff, donor[k].cff
            if cff.fontNames and dcff.fontNames:
                top = cff[cff.fontNames[0]]
                dtop = dcff[dcff.fontNames[0]]
                for a in ("FamilyName", "FullName", "Notice", "Copyright", "Weight"):
                    if hasattr(dtop, a):
                        setattr(top, a, getattr(dtop, a))
                cff.fontNames[0] = dcff.fontNames[0]       # CID 字体里 FontName 只是标识

    # 2) name 表整体照抄 donor：让身份表面与游戏原始字体完全一致
    if "name" in donor:
        sub_font["name"] = copy.deepcopy(donor["name"])

    donor.close()
    return {"before": before, "after": identity_of(sub_font)}


def subset_font(src: Path, dst: Path, chars: set[str], *, hinting: bool,
                layout: bool, drop_extra: bool) -> tuple[int, int]:
    """切子集 -> (字节数, cmap 覆盖数)"""
    opts = subset.Options()
    opts.hinting = hinting
    opts.desubroutinize = False          # ★ 绝不展平 CFF 子程序
    opts.retain_gids = False
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.recalc_timestamp = False
    opts.name_IDs = ["*"]
    opts.layout_features = ["*"] if layout else []
    drop = ["DSIG"]
    if drop_extra:
        drop += ["BASE", "VORG", "vhea", "vmtx", "FFTM", "Gasp", "mort"]
    opts.drop_tables += drop

    font = subset.load_font(str(src), opts)
    s = subset.Subsetter(options=opts)
    s.populate(unicodes=[ord(c) for c in chars])
    s.subset(font)
    subset.save_font(font, str(dst), opts)
    font.close()

    f = TTFont(str(dst), lazy=True)
    cmap: set[int] = set()
    for t in f["cmap"].tables:
        cmap |= set(t.cmap.keys())
    n = len(cmap)
    f.close()
    return dst.stat().st_size, n


def main() -> int:
    SDIR.mkdir(parents=True, exist_ok=True)
    charset, stat = collect_chars()
    say("字符集统计")
    say("=" * 84)
    for k, v in stat.items():
        say("  %-20s +%d" % (k, v))
    say("  ── 合计 %d 个字符，其中 CJK 区 %d 个" % (len(charset), cjk_count(charset)))
    say("  样例: %s" % "".join(sorted(charset & set("奥伯拉丁号船员下落判决书索赔"))))
    say("")

    # 档位： (名字, hinting, layout, 额外丢表)
    LEVELS = [
        ("A 只切字形（全保留）", True, True, False),
        ("B +丢垂直/DSIG等", True, True, True),
        ("C +丢 OpenType 排版表", True, False, True),
        ("D +丢 hinting", False, False, True),
    ]

    for fn, outname, desc in FONTS:
        src = SDIR / fn if (SDIR / fn).exists() else OUTDIR / "fonts" / fn
        if not src.exists():
            say("缺字体源 %s" % src)
            continue
        say("=" * 84)
        say("%s   —— %s" % (outname, desc))
        say("  源: %s  %s" % (src.name, human(src.stat().st_size)))
        f0 = TTFont(str(src), lazy=True)
        c0: set[int] = set()
        for t in f0["cmap"].tables:
            c0 |= set(t.cmap.keys())
        say("  源 cmap %d 码位 / %d 字形  格式=%s"
            % (len(c0), f0["maxp"].numGlyphs, "CFF" if "CFF " in f0 else "glyf"))
        miss = [c for c in charset if ord(c) not in c0]
        say("  源字体缺我们的字符: %d 个%s" % (len(miss), ("  例: " + "".join(miss[:20])) if miss else ""))
        f0.close()
        say("")
        say("  %-24s %12s %12s %10s %8s" % ("档位", "大小", "占原字体", "覆盖", "缺字"))
        for name, hint, lay, de in LEVELS:
            dst = SDIR / ("%s_%s" % (name.split()[0], fn))
            size, cov = subset_font(src, dst, charset, hinting=hint, layout=lay, drop_extra=de)
            lack = len(charset) - cov
            say("  %-24s %12s %11.1f%% %10d %8d"
                % (name, human(size), 100.0 * size / src.stat().st_size, cov, lack))
        say("")

    text = "\n".join(lines)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    print("\n报告 -> %s" % REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
