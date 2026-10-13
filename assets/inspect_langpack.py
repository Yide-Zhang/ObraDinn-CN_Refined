# -*- coding: utf-8 -*-
"""看语言包（StreamingAssets/lang-*）里到底装了什么 —— 尤其是**带字的图**。

用法:
  python CN_Refined\\assets\\inspect_langpack.py                # 看游戏全部 lang-*
  python CN_Refined\\assets\\inspect_langpack.py zh-s en        # 只看指定语言
  python CN_Refined\\assets\\inspect_langpack.py --dump zh-s    # 把包里的图导到 out\\langimg\\
产物: CN_Refined\\assets\\out\\langpack_content.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = Path(r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data")
SA = GAME / "StreamingAssets"
OUTIMG = HERE / "out" / "langimg"
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def inspect(p: Path, dump: bool = False) -> None:
    say("=" * 100)
    say("%s   %.1f KB" % (p.name, p.stat().st_size / 1024))
    try:
        env = UnityPy.load(str(p))
    except Exception as e:                                     # noqa: BLE001
        say("  ✗ 打不开: %s" % e)
        return
    counts: dict[str, int] = {}
    interesting = []
    for o in env.objects:
        counts[o.type.name] = counts.get(o.type.name, 0) + 1
        try:
            d = o.read()
        except Exception:                                      # noqa: BLE001
            continue
        nm = str(getattr(d, "m_Name", "") or "")
        if o.type.name in ("Texture2D", "Sprite", "Font", "TextAsset", "MonoBehaviour"):
            info = ""
            if o.type.name == "Texture2D":
                info = " %sx%s fmt=%s size=%s" % (getattr(d, "m_Width", "?"),
                                                  getattr(d, "m_Height", "?"),
                                                  getattr(d, "m_TextureFormat", "?"),
                                                  getattr(d, "m_CompleteImageSize", "?"))
            interesting.append((o.type.name, o.path_id, nm, info))
            if dump and o.type.name in ("Texture2D", "Sprite"):
                try:
                    img = d.image
                    OUTIMG.mkdir(parents=True, exist_ok=True)
                    f = OUTIMG / ("%s-%s-%s.png" % (p.name, o.type.name, nm or o.path_id))
                    img.save(f)
                    say("    → 导出 %s  %s" % (f.name, img.size))
                except Exception as e:                          # noqa: BLE001
                    say("    ✗ 导出图失败 %s: %s" % (nm, e))
    say("  对象统计: %s" % ", ".join("%s×%d" % (k, v) for k, v in sorted(counts.items())))
    for t, pid, nm, info in interesting[:40]:
        say("    %-13s pathId=%-8s %-40r%s" % (t, pid, nm, info))
    if len(interesting) > 40:
        say("    …另有 %d 个" % (len(interesting) - 40))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dump = "--dump" in sys.argv
    if not SA.exists():
        say("✗ 找不到 %s" % SA)
        (HERE / "out" / "langpack_content.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    pats = args or ["zh-s", "en", "ja", "zh-t"]
    say("语言包内容检查（StreamingAssets/lang-*）")
    for pat in pats:
        for p in sorted(SA.glob("lang-%s" % pat)):
            if p.name.endswith(".manifest") or not p.is_file():
                continue
            inspect(p, dump)
    (HERE / "out" / "langpack_content.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
