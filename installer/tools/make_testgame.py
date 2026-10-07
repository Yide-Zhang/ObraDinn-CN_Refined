# -*- coding: utf-8 -*-
"""搭一个「玩家机器」沙盒：用**原版**文件拼出一份假的游戏目录，用来端到端试安装/还原。

    python CN_Refined\\installer\\tools\\make_testgame.py

沙盒 = CN_Refined/out/testgame/ ，里面只放引擎会碰的 5 个文件 + DLL 依赖目录：
    ObraDinn_Data/Managed/            （整目录复制，patchwrap/dll 需要同目录的依赖才能加载）
    ObraDinn_Data/sharedassets0/2/6   来自 originalassets/_pristine（真原版）
    ObraDinn_Data/StreamingAssets/lang-zh-s   来自 originalassets/langpacks（官方原版）

这样测出来的结论才能代表玩家机器 —— 也才敢对你的真游戏动手。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
CR = ROOT / "CN_Refined"
ORIG = CR / "originalassets"

SRC_GAME = Path("F:/AceAttorneySeries/gameFiles/steamapps/common/ObraDinn")
SB = CR / "out" / "testgame"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    return "%.2f MB" % (n / (1 << 20)) if n >= (1 << 20) else "%d B" % n


def main() -> int:
    d = SB / "ObraDinn_Data"
    if SB.exists():
        shutil.rmtree(SB)
    (d / "StreamingAssets").mkdir(parents=True)

    # 1) Managed 整目录（DLL + 依赖，patchwrap 要用）
    src_managed = SRC_GAME / "ObraDinn_Data" / "Managed"
    if not src_managed.is_dir():
        say("✗ 找不到 %s" % src_managed)
        return 1
    shutil.copytree(src_managed, d / "Managed")
    n = sum(1 for p in (d / "Managed").rglob("*") if p.is_file())
    say("  ✓ Managed/  %d 个文件" % n)

    # 2) DLL 换成**原版**（现网那份已被 wrap 过）
    vdll = ORIG / "_gamebackup-20261006-220426" / "Assembly-CSharp.dll"
    shutil.copy2(vdll, d / "Managed" / "Assembly-CSharp.dll")
    say("  ✓ Managed/Assembly-CSharp.dll  原版 %s" % human(vdll.stat().st_size))

    # 3) 三份 assets 用 _pristine（真原版，含 .resS）
    for nm in ("sharedassets0.assets", "sharedassets0.assets.resS",
               "sharedassets2.assets", "sharedassets2.assets.resS",
               "sharedassets6.assets"):
        p = ORIG / "_pristine" / nm
        if p.is_file():
            shutil.copy2(p, d / nm)
            say("  ✓ %-28s %s（原版）" % (nm, human(p.stat().st_size)))

    # 4) 官方语言包
    lp = ORIG / "langpacks" / "lang-zh-s"
    shutil.copy2(lp, d / "StreamingAssets" / "lang-zh-s")
    say("  ✓ StreamingAssets/lang-zh-s  官方 %s" % human(lp.stat().st_size))

    say("")
    say("沙盒: %s" % SB)
    (PKG / "out").mkdir(parents=True, exist_ok=True)
    (PKG / "out" / "testgame.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    for ln in lines:
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
