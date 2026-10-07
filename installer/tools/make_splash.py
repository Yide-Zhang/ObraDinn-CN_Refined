# -*- coding: utf-8 -*-
"""生成打包用的**启动画面**（PyInstaller `--splash`）。

    python CN_Refined\\installer\\tools\\make_splash.py

为什么需要：打成单文件后，**双击到界面出来要 ~8.6 秒**（bootloader 先把 ~40 MB 解到
`%TEMP%`）。这段时间屏幕上什么都没有 —— 小白会以为没双击上、再双击一次。
`splash` 是 bootloader 在**解压之前**就显示的窗口，正好把这段空白填上；
服务起来后由 `server.py` 里的 `pyi_splash.close()` 关掉。

配色沿用游戏色系（与 gui/theme.py 同一套值）：
    背景 #333319 · 描边 #c9c2a8 · 标题 #E5FFFF · 正文 #e8e2cf · 小字 paper 的 62%
输出：`CN_Refined/installer/assets/splash.png`（1600×1000，PyInstaller 会缩到 400×250）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
OUT = PKG / "assets" / "splash.png"
ICON = PKG / "assets" / "icon.png"
FONT_CANDIDATES = [ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF",
                   ROOT / "font_src" / "SourceHanSerifSC-SemiBold.otf"]

BG = "#333319"          # 深橄榄（页头色）
LINE = "#c9c2a8"        # 纸色描边
TITLE = "#E5FFFF"       # 青白
BODY = "#e8e2cf"        # 纸色正文
DIM = (232, 226, 207, 158)   # paper @62%


def font(size: int) -> ImageFont.FreeTypeFont:
    for c in FONT_CANDIDATES:
        if c.is_file():
            return ImageFont.truetype(str(c), size)
    print("[!] 找不到思源宋体 SemiBold，退回默认字体（不好看但能跑）")
    return ImageFont.load_default()


def centered(d: ImageDraw.ImageDraw, y: int, text: str, f, fill, w: int) -> None:
    box = d.textbbox((0, 0), text, font=f)
    d.text(((w - (box[2] - box[0])) / 2 - box[0], y), text, font=f, fill=fill)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
    except Exception:                                          # noqa: BLE001
        pass
    # 4 倍超采样再缩，边缘干净（PyInstaller 会把它缩到 --splash 的尺寸）
    S, W, H = 2, 800, 500
    w, h = W * S, H * S
    img = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(img)
    for i in range(S * 2):                                     # 2px 描边（缩放后 1px）
        d.rectangle([i, i, w - 1 - i, h - 1 - i], outline=LINE)
    # 图标
    if ICON.is_file():
        ic = Image.open(ICON).convert("RGBA")
        side = int(h * 0.34)
        ic = ic.resize((side, side), Image.LANCZOS)
        img.alpha_composite(ic, ((w - side) // 2, int(h * 0.16)))
    centered(d, int(h * 0.57), "《奥伯拉丁的回归》", font(38 * S), TITLE, w)
    centered(d, int(h * 0.72), "中文精修补丁 · 安装向导", font(24 * S), BODY, w)
    centered(d, int(h * 0.86), "正在解开程序，请稍候……", font(16 * S), DIM, w)
    img = img.resize((W, H), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print("[+] %s  %dx%d  %.1f KB" % (OUT.relative_to(ROOT), W, H, OUT.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
