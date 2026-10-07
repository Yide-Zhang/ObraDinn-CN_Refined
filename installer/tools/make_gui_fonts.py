# -*- coding: utf-8 -*-
"""给安装向导的界面生成**子集化字体**（"字体 B"）—— 只留界面真会用到的字。

    python CN_Refined\\installer\\tools\\make_gui_fonts.py
    python CN_Refined\\installer\\tools\\make_gui_fonts.py --check-only     # 只体检当前子集
    python CN_Refined\\installer\\tools\\make_gui_fonts.py --report         # 顺带把语料统计打出来

为什么：界面原来直接吃**全字体**（思源 Heavy 22.95 MB + SemiBold 23.56 MB ≈ 46.6 MB），
而整个向导会显示的字（含进度页把引擎日志整行打出来）也就几百个 → 子集化后 ~1 MB，
发布件直接省 ~45 MB。注意这与注入游戏内的**子集 A 完全不同**（A 要给游戏用、名字要和
donor 一致）。

语料 = 界面上可能出现的一切文字：
  · gui/{wizard,progress,theme,server}.py、run_gui.py —— 页面里的中文字符串
  · engine.py —— 进度页会逐行显示引擎日志，所以引擎的措辞也算语料；里面有文件路径、
    大小、编号（ASCII + 数字，已含）
  · data/difficulty.json —— 难度档位的 label/desc（会进日志与 /api/options）
  · ASCII 可打印字符 + 常用中英标点 + 符号（★✓✗⚠→…）+ 全角数字字母（保险起见）

关于用户自己填的游戏路径：里面的生僻字不在子集里时，浏览器会**自动回落到字体栈里的
下一个**（宋体 / 黑体 / Noto Serif CJK），**不会出现豆腐块**，只是那个字字形不同。
所以子集不用（也不该）去追求覆盖全部汉字。

字体原件：全字体在 `font_src/`（SemiBold 与 Heavy 各一份）。本脚本**就地覆盖**
`gui/fonts/` 里的两份（IMFe 只有 0.11 MB，原样保留），并在覆盖前确保全字体有备份 ——
所以脚本可以反复跑，不会拿子集去再子集。
"""
from __future__ import annotations

import argparse
import json
import shutil
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
GUI_FONTS = PKG / "gui" / "fonts"
FONT_SRC = ROOT / "font_src"

# (目标文件, 全字体候选：先 font_src，最后才是 gui/fonts 自分 ——
#  后者用「字形数 < 3000 就拒绝再子集」拦住)
TARGETS = [
    ("SourceHanSerifSC-SemiBold-subset.otf",
     ["font_src/SOURCEHANSERIFSC-SEMIBOLD.OTF", "font_src/SourceHanSerifSC-SemiBold.otf",
      "CN_Refined/installer/gui/fonts/SourceHanSerifSC-SemiBold-subset.otf"]),
    ("SourceHanSerifSC-Heavy.otf",
     ["font_src/SOURCEHANSERIFSC-HEAVY.OTF", "font_src/SourceHanSerifSC-Heavy.otf",
      "CN_Refined/installer/gui/fonts/SourceHanSerifSC-Heavy.otf"]),
]
# 全字体里没有、只能走系统回落的那几个字记在这里（体检时不当成缺字）
FALLBACK_NOTE = GUI_FONTS / "_fallback-chars.txt"
# 语料来源（相对仓库根）
CORPUS_FILES = ["CN_Refined/installer/engine.py",
                "CN_Refined/installer/run_gui.py",
                "CN_Refined/installer/gui/wizard.py",
                "CN_Refined/installer/gui/progress.py",
                "CN_Refined/installer/gui/theme.py",
                "CN_Refined/installer/gui/server.py",
                "CN_Refined/installer/data/difficulty.json"]
# 可能在运行期冒出来、但源码里没有的符号（保险集）
EXTRA = "　、。〈〉《》「」『』【】〔〕（）［］｛｝：；！？，．…—–～·×÷±≈≤≥°′″※√∞§¶†‡•●○■□◆◇▲△▼▽★☆✓✔✗✘→←↑↓↔⚠♪№％＃＆＠｜/"
MIN_GLYPHS_OF_FULL_FONT = 3000          # 小于这个数说明拿到的已经是个子集 → 拒绝再子集


def corpus(report: bool = False) -> str:
    chars = set(string.printable) | set(EXTRA)
    for rel in CORPUS_FILES:
        p = ROOT / rel
        if not p.is_file():
            print("[!] 缺语料文件 %s" % rel)
            continue
        chars |= set(p.read_text(encoding="utf-8"))
    chars = {c for c in chars if c.isprintable() and c not in "\r\n\t"}
    if report:
        cjk = [c for c in chars if "\u4e00" <= c <= "\u9fff"]
        print("    语料 %d 个字（其中汉字 %d 个）" % (len(chars), len(cjk)))
    return "".join(sorted(chars))


def full_font(cands: list[str]) -> Path | None:
    for rel in cands:
        p = ROOT / rel
        if p.is_file():
            return p
    return None


def glyph_count(p: Path) -> int:
    from fontTools.ttLib import TTFont                        # noqa: PLC0415
    with TTFont(str(p), fontNumber=0, lazy=True) as f:
        return len(f.getBestCmap())


def ensure_backup(src: Path) -> None:
    """把全字体备份到 font_src/（原名），这样脚本可以反复跑

    注意这里用的是**源文件自己的名字**：早期版本错用了 CSS 那个 `-subset` 名字，
    结果 font_src 里出现一个叫 subset 的 23 MB 全字体，很容易看糊。
    """
    if src.parent == FONT_SRC or (FONT_SRC / src.name).exists():
        return
    FONT_SRC.mkdir(parents=True, exist_ok=True)
    dst = FONT_SRC / src.name
    shutil.copy2(src, dst)
    print("    全字体已备份 → %s (%.2f MB)" % (dst.relative_to(ROOT), dst.stat().st_size / 1048576))


def allowed_fallback() -> set[str]:
    if FALLBACK_NOTE.is_file():
        return set(FALLBACK_NOTE.read_text(encoding="utf-8"))
    return set()


def check_only(text: str) -> int:
    allow = allowed_fallback()
    bad = 0
    for name, _ in TARGETS:
        p = GUI_FONTS / name
        if not p.is_file():
            print("[!] 缺 %s" % p.relative_to(ROOT))
            bad += 1
            continue
        from fontTools.ttLib import TTFont                    # noqa: PLC0415
        with TTFont(str(p), lazy=True) as f:
            cmap = set(f.getBestCmap())
        miss = sorted({c for c in text if ord(c) not in cmap and c not in allow})
        print("    %-40s %6.2f MB  缺 %d 个字 %s"
              % (name, p.stat().st_size / 1048576, len(miss), "".join(miss[:40])))
        bad += bool(miss)
    return 1 if bad else 0


def subset_one(src: Path, dst: Path, text: str) -> tuple[float, str]:
    from fontTools import subset                              # noqa: PLC0415
    from fontTools.ttLib import TTFont                        # noqa: PLC0415
    # 先按**全字体真实字形**过滤语料：全字体本身就没有的字（如 ✗），
    # 子集里当然也不会有 —— 浏览器会回落到系统字体，不算失败。
    with TTFont(str(src), lazy=True) as f:
        full_cmap = set(f.getBestCmap())
    usable = "".join(c for c in text if ord(c) in full_cmap)
    absent = "".join(sorted({c for c in text if ord(c) not in full_cmap}))

    opts = subset.Options()
    opts.layout_features = ["*"]              # 中日韩标点的 palt/vpal/kern 都留着
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["DSIG"]
    opts.recalc_bounds = True
    font = subset.load_font(str(src), opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=usable)
    sub.subset(font)
    subset.save_font(font, str(dst), opts)
    with TTFont(str(dst), lazy=True) as f:
        cmap = set(f.getBestCmap())
    miss = sorted({c for c in usable if ord(c) not in cmap})
    if miss:
        print("    [!] %s 缺 %d 个字：%s" % (dst.name, len(miss), "".join(miss[:40])))
    return dst.stat().st_size / 1048576, absent


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")    # type: ignore[union-attr]
    except Exception:                                         # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    print("[*] 收集语料…")
    text = corpus(report=a.report or True)
    if a.check_only:
        return check_only(text)

    GUI_FONTS.mkdir(parents=True, exist_ok=True)
    total_before = sum((GUI_FONTS / n).stat().st_size for n, _ in TARGETS if (GUI_FONTS / n).is_file())
    absent: set[str] = set()
    for name, cands in TARGETS:
        dst = GUI_FONTS / name
        src = full_font(cands)
        if src is None:
            print("[!] 找不到全字体（%s）—— 跳过 %s" % (" / ".join(cands), name))
            continue
        n_glyphs = glyph_count(src)
        if n_glyphs < MIN_GLYPHS_OF_FULL_FONT:
            print("[!] %s 只有 %d 个字形，像是子集本身 —— 拒绝再子集（把全字体放回 font_src/）"
                  % (src.relative_to(ROOT), n_glyphs))
            continue
        ensure_backup(src)
        mb, absent_here = subset_one(src, dst, text)
        absent |= set(absent_here)
        print("    %-40s ← %s (%d 字形)  →  %.2f MB"
              % (name, src.name, n_glyphs, mb))
    FALLBACK_NOTE.write_text("".join(sorted(absent)), encoding="utf-8")
    if absent:
        print("    （这些字全字体里本就没有，界面上一律走系统字体回落：%s）" % "".join(sorted(absent)))
    total_after = sum((GUI_FONTS / n).stat().st_size for n, _ in TARGETS if (GUI_FONTS / n).is_file())
    print("[+] gui/fonts 两份合计：%.2f MB → %.2f MB（省 %.2f MB）"
          % (total_before / 1048576, total_after / 1048576, (total_before - total_after) / 1048576))
    return check_only(text)


if __name__ == "__main__":
    raise SystemExit(main())
