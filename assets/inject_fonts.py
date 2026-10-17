# -*- coding: utf-8 -*-
"""把「子集化的字体」注入回游戏原始 assets —— 产出可安装的 sharedassets{0,2}.assets。

做法（关键三点）：
  1. **源用游戏自带的字体**（`out/fonts/orig-*.otf|ttf`），保证格式与字形完全一致
  2. **保持原格式**：SourceHanSerif 留 OTF/CFF、851tegaki 留 TTF/glyf；**绝不 desubroutinize**
  3. 只替换 `m_FontData` 一个字段，其它一个字节都不动

档位（默认 B，安全优先）：
  A 只切字形   B +丢垂直/DSIG/BASE 等   C +丢 OpenType 排版表   D +丢 hinting

用法: python CN_Refined\\assets\\inject_fonts.py [--level B] [--all-fonts]
产物: CN_Refined\\out\\assets\\sharedassets{0,2}.assets  +  CN_Refined\\assets\\out\\inject.txt
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

import UnityPy
from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402  复用字符集口径

ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets"
FONTS = HERE / "out" / "fonts"
OUTDIR = ROOT / "CN_Refined" / "out" / "assets"
REPORT = HERE / "out" / "inject.txt"

# assets 文件 -> 其中要处理的字体名 -> 字体源文件
#
# ★ 正文/手写体的字体源必须是**项目自己的那两支**，不是游戏自带的：
#   游戏自带的 `SourceHanSerif-SemiBold` 是多语言（日文形态）版，与项目要的
#   `font_src\SOURCEHANSERIFSC-SEMIBOLD.OTF`（思源宋体 **SC**）**字形完全不同**
#   （实测 直骨次令包化强每海温真者具角… 22 个探针字轮廓全不同；
#     gui\fonts 里那个子集的字形哈希 == SC 版，证实项目用的就是 SC 版）
#   手写体两支本来就是同一支（851tegaki，游戏自带即 851 手写体），所以用抠出来的原件。
JOBS = {
    "sharedassets0.assets": {
        "SourceHanSerif-SemiBold": ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF",
    },
    "sharedassets2.assets": {
        # ★ 用户 2026-10-17 决定：手写体改用他**翻新过的那支** `851tegakizatsu-Regular.otf`
        #   （此前用的是项目根 `851tegakizatsu.otf`，80.32 MB / 60876 字形；
        #     新支 31.48 MB / 60874 字形，同为 CFF 轮廓，家族名依旧是 '851tegakizatsu'）
        #   ⚠️ 两支都与**游戏内嵌**那份（out/fonts/orig-851tegaki_zatsu_normal_0883.ttf）
        #      不是同一份：有 21 个字的形状不同（海船博将所迪詹达直毒敷屠航溺画舵窦角底睹包）。
        #      想回到与未改动版游戏完全一致，把这行换成
        #      HERE / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf" 即可。
        "851tegaki_zatsu_normal_0883": ROOT / "851tegakizatsu-Regular.otf",
    },
}

# 扁平视图：字体名 -> 源文件（check_fonts.py 用同一份，避免两边基准跑偏）
SOURCE_BY_FONT = {fn: src for jobs in JOBS.values() for fn, src in jobs.items()}

LEVELS = {
    "A": (True, True, False),
    "B": (True, True, True),
    "C": (True, False, True),
    "D": (False, False, True),
}

# 身份名 donor：一律用**游戏原始内嵌的同名字体**。
# Unity 会拿字体内部 family 名去对 Font 对象的 m_FontNames（如 Serif 是 ['Source Han Serif']），
# 对不上就丢弃整支字体 → 回落系统字体（中文 Windows = Microsoft YaHei）。
# 我把源换成 SC 版后 family 变成 'Source Han Serif Simplified Chinese'，正好踩这个坑。
IDENT = {
    "SourceHanSerif-SemiBold": FONTS / "orig-SourceHanSerif-SemiBold.otf",
    "851tegaki_zatsu_normal_0883": FONTS / "orig-851tegaki_zatsu_normal_0883.ttf",
}

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def make_subset(src: Path, chars: set[str], level: str,
                ident: Path | None = None) -> tuple[bytes, dict]:
    hinting, layout, drop_extra = LEVELS[level]
    opts = subset.Options()
    opts.hinting = hinting
    opts.desubroutinize = False
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
    # ★ 关键 1：把 fontTools 剪掉的 cmap 子表结构与 OS/2 码页位，按源字体补回来
    MS.restore_like_source(font, src)
    # ★ 关键 2：把身份名恢复成游戏原始字体的（Unity 靠它认字体，对不上就回落系统字体）
    idn = {}
    if ident is not None and ident.exists():
        idn = MS.restore_identity(font, ident)
    buf = io.BytesIO()
    font.save(buf, reorderTables=opts.canonical_order)
    font.close()
    return buf.getvalue(), idn


def snapshot(path: Path):
    env = UnityPy.load(str(path))
    snap = {}
    for o in env.objects:
        try:
            h = sha(bytes(o.get_raw_data()))
        except Exception as e:                            # noqa: BLE001
            h = "ERR:%s" % type(e).__name__
        snap[o.path_id] = (o.type.name, o.byte_size, h)
    return snap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="B", choices=sorted(LEVELS))
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    charset, stat = MS.collect_chars()
    say("字体注入（档位 %s）" % args.level)
    say("=" * 88)
    say("  字符集 %d 个（CJK %d 个），来自 20 个语言包 + 官方包 + 标点保险 + C# 字面量 + assets 二进制"
        % (len(charset), MS.cjk_count(charset)))
    for k, v in stat.items():
        say("      %-26s +%d" % (k, v))

    # 关键串覆盖自检（这些不在语言包里，是从 DLL / assets 里挖出来的）
    ok = True
    CRIT = ["日本語", "简体中文", "繁體中文", "奥伯拉丁号", "下落", "申诉", "理赔"]
    missing_crit = [s for s in CRIT
                    if any(c not in charset for c in s)]
    say("  关键串自检: %s"
        % ("全部已覆盖 ✓" if not missing_crit
           else "✗ 缺字符的串: %s" % missing_crit))
    if missing_crit:
        ok = False

    # shs6 里的中文字串（含你改的本地化名字）
    for tag, p in (("原始", ORIG / "sharedassets6.assets"),
                   ("你的", ROOT / "CN_Refined" / "olddevassets" / "sharedassets6.assets")):
        if not p.exists():
            continue
        found = sorted(MS.scan_bytes(p))
        say("  shs6(%s) 里的中文串字符 %d 个: %s"
            % (tag, len(found), "".join(found[:60])))
    say("")

    for fn, jobs in JOBS.items():
        src_assets = ORIG / fn
        if not src_assets.exists():
            say("✗ 缺 %s" % src_assets)
            ok = False
            continue
        dst_assets = OUTDIR / fn
        say("=" * 88)
        say("%s" % fn)
        say("  原始 %s   sha=%s" % (human(src_assets.stat().st_size), sha(src_assets.read_bytes())))

        # 1) 先把所有要替换的字体准备好
        subs: dict[str, bytes] = {}
        for fname, fsrc in jobs.items():
            if not fsrc.exists():
                say("  ✗ 缺字体源 %s" % fsrc)
                ok = False
                continue
            data, idn = make_subset(fsrc, charset, args.level, IDENT.get(fname))
            subs[fname] = data
            say("  字体 %-32s %s → %s" % (fname, human(fsrc.stat().st_size), human(len(data))))
            if idn:
                b, a = idn["before"], idn["after"]
                say("       身份名 before: family=%r name1=%r name6=%r"
                    % (b["cff_family"], b["name1"], b["name6"]))
                say("       身份名 after : family=%r name1=%r name6=%r"
                    % (a["cff_family"], a["name1"], a["name6"]))
            f = TTFont(io.BytesIO(data), lazy=True)
            cov: set[int] = set()
            for t in f["cmap"].tables:
                cov |= set(t.cmap.keys())
            miss_cjk = [c for c in charset if MS.CJK_CHAR(c) and ord(c) not in cov]
            say("       子集 cmap %d 码位  字形 %d  **缺 CJK %d 个**%s"
                % (len(cov), f["maxp"].numGlyphs, len(miss_cjk),
                   ("  例: " + "".join(miss_cjk[:16])) if miss_cjk else ""))
            cm = [(hex(t.platformID), hex(t.platEncID), t.format) for t in f["cmap"].tables]
            try:
                o2 = f["OS/2"]
                bits = "Uni=%08X/%08X/%08X/%08X  CP=%04X%04X" % (
                    o2.ulUnicodeRange1, o2.ulUnicodeRange2, o2.ulUnicodeRange3, o2.ulUnicodeRange4,
                    o2.ulCodePageRange1, o2.ulCodePageRange2)
                gb = bool(o2.ulCodePageRange1 & (1 << 18))
            except Exception:                          # noqa: BLE001
                bits, gb = "?", False
            say("       cmap 子表: %s" % cm)
            say("       OS/2 %s   简体中文位(bit18)=%s %s"
                % (bits, gb, "✓" if gb else "✗ 会回落系统字体"))
            f.close()
            if miss_cjk:
                ok = False

        # 2) 注入
        env = UnityPy.load(str(src_assets))
        hit = []
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            d = obj.read()
            nm = getattr(d, "m_Name", "")
            if nm not in subs:
                continue
            old = len(d.m_FontData)
            d.m_FontData = list(subs[nm])
            d.save()
            hit.append((nm, old, len(subs[nm])))
        for nm, a, b in hit:
            say("  注入 %-32s fontData %s → %s" % (nm, human(a), human(b)))
        missing = set(jobs) - {h[0] for h in hit}
        if missing:
            say("  ✗ 没找到字体对象: %s" % ", ".join(sorted(missing)))
            ok = False
            continue

        # 3) 存盘
        data = env.file.save()
        dst_assets.write_bytes(data)
        say("  存盘 %s   %s → %s   (%+s)"
            % (dst_assets.name, human(src_assets.stat().st_size), human(len(data)),
               human(len(data) - src_assets.stat().st_size)))

        # 4) 验证：只有目标字体变了
        s0, s1 = snapshot(src_assets), snapshot(dst_assets)
        only1 = [k for k in s1 if k not in s0]
        only0 = [k for k in s0 if k not in s1]
        # 找出真正变了的对象（排除我们注入的字体）
        font_pids = set()
        env2 = UnityPy.load(str(dst_assets))
        for o in env2.objects:
            if o.type.name == "Font":
                try:
                    if getattr(o.read(), "m_Name", "") in subs:
                        font_pids.add(o.path_id)
                except Exception:                          # noqa: BLE001
                    pass
        diff = [k for k in s0 if k in s1 and s0[k] != s1[k] and k not in font_pids]
        say("  验证: 对象 %d→%d  仅在原始 %d  仅在成品 %d  **非字体对象的改动 %d**"
            % (len(s0), len(s1), len(only0), len(only1), len(diff)))
        for k in diff[:8]:
            say("      ✗ pathId=%s %s %d→%d" % (k, s0[k][0], s0[k][1], s1[k][1]))
        if only0 or only1 or diff:
            ok = False

        # 5) 回读字体确认长度
        got = {}
        for o in env2.objects:
            if o.type.name == "Font":
                try:
                    dd = o.read()
                    if getattr(dd, "m_Name", "") in subs:
                        got[dd.m_Name] = len(dd.m_FontData)
                except Exception:                          # noqa: BLE001
                    pass
        for nm, n in got.items():
            good = (n == len(subs[nm]))
            say("  回读 %-32s fontData=%s  %s"
                % (nm, human(n), "✓" if good else "✗ 与预期不符"))
            ok &= good

        # 6) ★ 身份名交叉校验：字体内部 family 名必须能对上 Font 对象的 m_FontNames
        #    （对不上 Unity 就用系统字体 —— 这正是用户看到 Microsoft YaHei 的原因）
        for o in env2.objects:
            if o.type.name != "Font":
                continue
            try:
                dd = o.read()
            except Exception:                              # noqa: BLE001
                continue
            if getattr(dd, "m_Name", "") not in subs:
                continue
            fn = TTFont(io.BytesIO(bytes(dd.m_FontData)), lazy=True)
            idf = MS.identity_of(fn)
            fn.close()
            want = list(getattr(dd, "m_FontNames", []) or [])
            cand = [idf["cff_family"], idf["name1"], idf["cff_font"], idf["name6"]]
            hitname = next((c for c in cand if c and c in want), None)
            say("  身份名校验 %-30s m_FontNames=%s" % (dd.m_Name, want))
            say("       字体声明 family=%r name1=%r name6=%r → %s"
                % (idf["cff_family"], idf["name1"], idf["name6"],
                   ("命中 %r ✓" % hitname) if hitname
                   else "✗ 一个都对不上，Unity 会回落系统字体"))
            if not hitname:
                ok = False
        say("")

    say("=" * 88)
    say("全部通过 ✓" if ok else "⚠ 有问题，见上")
    say("")
    say("产物: %s" % OUTDIR)
    text = "\n".join(lines)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
