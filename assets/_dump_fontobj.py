# -*- coding: utf-8 -*-
"""把三个版本里 Font 对象的**所有字段**列出来对比（m_FontData 只报长度）。

目标：找出「能用」和「不能用」的字体对象之间，除了字体数据本身之外的差异
（例如 m_Ascii / m_CharacterRects / m_Texture / m_FontSize …）。

用法: python CN_Refined\\assets\\_dump_fontobj.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = [
    ("原始shs0", ROOT / "CN_Refined" / "originalassets" / "sharedassets0.assets"),
    ("dev shs0", ROOT / "CN_Refined" / "olddevassets" / "sharedassets0.assets"),
    ("我  shs0", ROOT / "CN_Refined" / "out" / "assets" / "sharedassets0.assets"),
    ("原始shs2", ROOT / "CN_Refined" / "originalassets" / "sharedassets2.assets"),
    ("dev shs2", ROOT / "CN_Refined" / "olddevassets" / "sharedassets2.assets"),
    ("我  shs2", ROOT / "CN_Refined" / "out" / "assets" / "sharedassets2.assets"),
]
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def brief(v, depth: int = 0):
    pid = getattr(v, "m_PathID", None)
    if pid is not None:
        return "<PPtr path=%s file=%s>" % (pid, getattr(v, "m_FileID", "?"))
    if isinstance(v, (bytes, bytearray, list)) and len(v) > 8:
        return "<%s len=%d>" % (type(v).__name__, len(v))
    if isinstance(v, list):
        return "[%s]" % ", ".join(str(brief(x, depth + 1)) for x in v[:6])
    if isinstance(v, (str, int, float, bool)) or v is None:
        s = repr(v)
        return s if len(s) < 70 else s[:67] + "..."
    return "<%s>" % type(v).__name__


def main() -> int:
    for tag, p in FILES:
        if not p.exists():
            say("%-10s ✗ 缺 %s" % (tag, p))
            continue
        env = UnityPy.load(str(p))
        say("=" * 88)
        say("%s  (%s)" % (tag, p.name))
        for o in env.objects:
            if o.type.name != "Font":
                continue
            d = o.read()
            say("  pathId=%s  byteSize=%d" % (o.path_id, o.byte_size))
            for name in sorted(vars(d)):
                if name.startswith("_"):
                    continue
                try:
                    v = getattr(d, name)
                except Exception as e:                    # noqa: BLE001
                    say("    %-22s <读取失败 %s>" % (name, e))
                    continue
                if name == "m_FontData":
                    say("    %-22s <%d 字节>" % (name, len(v)))
                else:
                    say("    %-22s %s" % (name, brief(v)))
        say("")
    text = "\n".join(lines)
    (HERE / "out" / "fontobj.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
