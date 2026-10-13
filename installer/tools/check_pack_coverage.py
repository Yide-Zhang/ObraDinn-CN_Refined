# -*- coding: utf-8 -*-
"""语言包文本 ↔ 打包用字体子集（assets/fonts/A-*.otf）的逐字覆盖检查 —— 发布前闸门。

为什么必须有它：
  安装补丁时会向游戏注入**子集化**的字体（`A-*.otf`），而子集只覆盖
  「构建出它的那一刻」语言包里出现过的字。之后再改译文，一旦引入**新字**
  （2026-10-12 就连踩两次：`劈/哎/滚/队` 与 `惟`），游戏里那几个字就会
  回落系统字体 —— 中文出豆腐块/异体，而且只在游戏里才看得见。

  所以流程是：改译文 → `langpack/build_pack.py --all` → **跑本脚本** →
  有缺字就 `installer/tools/make_package.py`（**不能**加 `--skip-fonts`，
  那会跳过字体子集重建）。

判据分两档（关键：不要让它长期变红而失去意义）：
  · **中文（汉字/中文标点）缺失 → 判失败 exit 1**。这是我们自己的内容，必须覆盖。
  · 其它（天城文/西里尔/拉丁…）缺失 → 只提示不判失败。那些是**双语模式下原文侧**
    的外语台词，本来就允许回落（上游 851 手写体自称有天城文但画出来是空白，
    官方 zh-s 也一样）。

用法::

    python CN_Refined\\installer\\tools\\check_pack_coverage.py          # 查 out/packs（刚重出的）
    python CN_Refined\\installer\\tools\\check_pack_coverage.py --old    # 查 installer/assets/packs（已发布那份）
    python CN_Refined\\installer\\tools\\check_pack_coverage.py --src DIR

★ 只有 `installer/` 的机器（比如那台 mac VM）没有 `out/packs`，用 `--old` 即可。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent        # installer/tools
PKG = HERE.parent                             # installer
CR = PKG.parent                               # CN_Refined
FONTS = PKG / "assets" / "fonts"
DJ = PKG / "data" / "difficulty.json"
DEFAULT_SRC = CR / "out" / "packs"
OLD_SRC = PKG / "assets" / "packs"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CJK_PUNCT = re.compile(r"[\u3000-\u303f\uff00-\uffef]")


def engine_chars() -> set:
    """引擎安装时会**写进游戏**、却不在语言包里的文本。

    目前只有一处：难度补丁按玩家档位改写的 4 个键里的中文数字
    （`data/difficulty.json` 的 `num_chars` 与 `levels[].zh`，例：五十八、二十九）。
    ★ 这一来源曾经漏在字体子集之外（`make_subset_fonts.collect_chars()` 已同步补上），
      所以本闸门也一并检查 —— 否则闸门自己也会有这个盲区。
    """
    s: set = set()
    if DJ.exists():
        import json
        d = json.loads(DJ.read_text(encoding="utf-8"))
        s |= set(d.get("num_chars", ""))
        for lv in d.get("levels", []):
            s |= set(str(lv.get("zh", "")))
    return s


def chars_of(d: Path) -> set:
    """目录里所有 *.tsv 的「值」用到的字符（跳过审查表之类多列产物）。"""
    s: set = set()
    for f in sorted(d.glob("*.tsv")):
        if f.name.startswith("REVIEW") or f.name.startswith("_"):
            continue          # 审查表是多列表格，列分隔符是制表符，不是可安装语言包
        for ln in f.read_text(encoding="utf-8-sig").splitlines():
            if not ln.strip() or ln.startswith("#") or "\t" not in ln:
                continue
            s.update(ln.split("\t", 1)[1])
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", action="store_true",
                    help="查 installer/assets/packs（已发布那份），默认查 out/packs")
    ap.add_argument("--src", default=None, help="自定义目录（里面放 *.tsv）")
    a = ap.parse_args()

    src = Path(a.src) if a.src else (OLD_SRC if a.old else DEFAULT_SRC)
    if not src.is_dir():
        print("[X] 目录不存在：%s" % src)
        print("    （--old 查已发布的 installer/assets/packs；没有 out/packs 的机器请加 --old）")
        return 2

    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("[i] 没装 fontTools —— 跳过检查（pip install fonttools）")
        return 0

    fonts = sorted(FONTS.glob("A-*.otf"))
    if not fonts:
        print("[X] 没找到字体子集：%s" % FONTS)
        return 2

    chars = chars_of(src)
    eng = engine_chars()
    chars |= eng
    print("语言包 %s" % src)
    print("  用到 %d 个字符（其中 %d 个来自「引擎写入游戏的文本」：%s）"
          % (len(chars), len(eng), "".join(sorted(eng))))
    hard, soft = {}, {}
    for f in fonts:
        cmap = set(TTFont(str(f), lazy=True).getBestCmap().keys())
        miss = sorted(c for c in chars if ord(c) not in cmap)
        h = [c for c in miss if CJK.match(c) or CJK_PUNCT.match(c)]
        s = [c for c in miss if c not in h]
        print("  %s：缺 %d（中文 %d / 其它 %d）" % (f.name, len(miss), len(h), len(s)))
        if h:
            hard[f.name] = h
        if s:
            soft[f.name] = s

    for name, ks in soft.items():
        print("  [提示] %s 缺的非中文字符（双语原文侧，允许回落）：%s"
              % (name, " ".join("U+%04X" % ord(c) for c in ks)))

    if hard:
        print("")
        print("[X] 中文缺字 —— 游戏里会出豆腐块，必须重建字体子集：")
        for name, ks in hard.items():
            print("    %s：%s" % (name, "".join(ks)))
            print("        码位：%s" % " ".join("U+%04X" % ord(c) for c in ks))
        print("")
        print("    修法：python CN_Refined/installer/tools/make_package.py"
              "   （★ 别加 --skip-fonts）")
        return 1

    print("")
    print("[=] 中文全覆盖 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
