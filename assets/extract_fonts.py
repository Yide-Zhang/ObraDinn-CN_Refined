# -*- coding: utf-8 -*-
"""把 assets 里的字体抠出来并体检（fontTools）。

目的：看清旧产物里那两个 80MB 的字体到底是什么，以及原始游戏字体的字形数/cmap 覆盖。

用法: python CN_Refined\\assets\\extract_fonts.py
产物: CN_Refined\\assets\\out\\fonts\\<来源>-<名字>.<ext>  +  CN_Refined\\assets\\out\\fonts.txt
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import UnityPy
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets"
OLD = ROOT / "CN_Refined" / "olddevassets"
OUTDIR = HERE / "out"
FDIR = OUTDIR / "fonts"
REPORT = OUTDIR / "fonts.txt"

SOURCES = [("orig", ORIG, "sharedassets0.assets"), ("orig", ORIG, "sharedassets2.assets"),
           ("old", OLD, "sharedassets0.assets"), ("old", OLD, "sharedassets2.assets")]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


def sniff(data: bytes) -> str:
    """猜字体格式（取扩展名用）"""
    if data[:4] == b"\x00\x01\x00\x00" or data[:4] == b"true":
        return "ttf"
    if data[:4] == b"OTTO":
        return "otf"
    if data[:4] == b"ttcf":
        return "ttc"
    if data[:2] == b"wOFF":
        return "woff"
    if data[:4] == b"wOF2":
        return "woff2"
    return "bin"


def main() -> int:
    FDIR.mkdir(parents=True, exist_ok=True)
    for tag, base, fn in SOURCES:
        p = base / fn
        if not p.exists():
            say("缺 %s" % p)
            continue
        env = UnityPy.load(str(p))
        say("=" * 84)
        say("%s :: %s" % (p.relative_to(ROOT), human(p.stat().st_size)))
        say("=" * 84)
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            d = obj.read()
            name = getattr(d, "m_Name", "") or "?"
            fd = bytes(getattr(d, "m_FontData", b"") or b"")
            ext = sniff(fd)
            dst = FDIR / ("%s-%s.%s" % (tag, name, ext))
            dst.write_bytes(fd)
            say("")
            say("  名字      : %s   （pathId=%s）" % (name, obj.path_id))
            say("  fontData  : %s   → %s" % (human(len(fd)), dst.name))
            say("  头部      : %s" % ext)
            try:
                f = TTFont(io.BytesIO(fd), fontNumber=0, lazy=True)
            except Exception as e:                       # noqa: BLE001
                say("  ✗ fontTools 打不开: %s" % e)
                continue
            tbls = sorted(f.keys())
            cmap = set()
            for t in f["cmap"].tables:
                cmap |= set(t.cmap.keys())
            cjk = sum(1 for c in cmap if 0x3400 <= c <= 0x9FFF or 0xF900 <= c <= 0xFAFF)
            fam = ""
            try:
                nm = f["name"]
                for nid in (1, 4, 6):
                    r = nm.getDebugName(nid)
                    if r:
                        fam += (" | " if fam else "") + r
            except Exception:                            # noqa: BLE001
                pass
            say("  字形数    : %d" % f["maxp"].numGlyphs)
            say("  cmap 码位 : %d （其中 CJK 区 %d）" % (len(cmap), cjk))
            say("  名称      : %s" % fam)
            say("  表        : %s" % ", ".join(tbls))
            # 各表体积，找大头
            try:
                sizes = sorted(((len(f.reader.tables[t].data) if hasattr(f.reader.tables[t], "data")
                                 else 0), t) for t in tbls)
                big = [t for t in tbls if t in ("CFF ", "glyf", "loca", "hmtx", "GSUB", "GPOS", "GDEF")]
                parts = []
                for t in big:
                    try:
                        parts.append("%s=%.2fMB" % (t.strip(), len(f.reader.tables[t].data) / 1048576))
                    except Exception:                    # noqa: BLE001
                        pass
                if parts:
                    say("  大表      : %s" % ", ".join(parts))
            except Exception:                            # noqa: BLE001
                pass
        say("")

    text = "\n".join(lines)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    print("\n报告 -> %s" % REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
