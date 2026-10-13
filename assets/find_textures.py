# -*- coding: utf-8 -*-
"""定位那 4 张带文字的图（ManifestCrew / FolioSketch / FolioDeck / FolioChart）住在哪个文件里，
并报告它们的 Texture2D 参数（尺寸/格式/是否 streamed 到 .resS）。

用法: python CN_Refined\\assets\\find_textures.py
产物: CN_Refined\\assets\\out\\texture_hosts.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = Path(r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data")
NAMES = ["ManifestCrew", "FolioSketch", "FolioDeck", "FolioChart"]
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def main() -> int:
    say("那 4 张图住在哪里")
    say("=" * 96)
    hits: list[Path] = []
    for p in sorted(GAME.rglob("*")):
        if not p.is_file() or p.stat().st_size < 1024:
            continue
        if p.name.startswith("lang-") or p.suffix.lower() in (".dll", ".exe", ".json", ".txt"):
            continue
        try:
            d = p.read_bytes()
        except Exception:                                      # noqa: BLE001
            continue
        found = [n for n in NAMES if n.encode() in d]
        if found:
            hits.append(p)
            say("  %-44s %10d B   %s" % (p.relative_to(GAME), len(d), ",".join(found)))
    say("")

    for p in hits:
        say("-" * 96)
        say("%s" % p.relative_to(GAME))
        try:
            env = UnityPy.load(str(p))
        except Exception as e:                                 # noqa: BLE001
            say("  ✗ 打不开: %s" % e)
            continue
        n = 0
        for o in env.objects:
            if o.type.name not in ("Texture2D", "Sprite"):
                continue
            try:
                d = o.read()
            except Exception:                                  # noqa: BLE001
                continue
            nm = getattr(d, "m_Name", "")
            if nm not in NAMES:
                continue
            n += 1
            sd = getattr(d, "m_StreamData", None)
            sdinfo = "-"
            if sd is not None:
                sdinfo = "path=%r offset=%s size=%s" % (getattr(sd, "path", None),
                                                        getattr(sd, "offset", None),
                                                        getattr(sd, "size", None))
            img = None
            try:
                img = d.image
            except Exception as e:                             # noqa: BLE001
                sdinfo += "  (取图失败 %s)" % type(e).__name__
            say("  %-10s pathId=%-8s %sx%s fmt=%s mip=%s size=%s B  streamed: %s"
                % (o.type.name, o.path_id, getattr(d, "m_Width", "?"), getattr(d, "m_Height", "?"),
                   getattr(d, "m_TextureFormat", "?"), getattr(d, "m_MipCount", "?"),
                   getattr(d, "m_CompleteImageSize", "?"), sdinfo))
            if img is not None:
                say("      实际图 %s %s" % (img.size, img.mode))
        if not n:
            say("  （没找到这 4 个名字的 Texture2D/Sprite 对象）")
    say("")
    (HERE / "out" / "texture_hosts.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
