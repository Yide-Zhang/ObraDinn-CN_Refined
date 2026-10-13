# -*- coding: utf-8 -*-
"""把所有语言包收进基线并导出成 TSV —— 供字体子集化算字符集用。

★ 同一套字体资源是**所有语言共用**的：玩家选 zh-t / ja / ko 时，
  照样是那支 SourceHanSerif / 851tegaki 在渲染 —— 所以字符集必须涵盖全部语言。

用法: python CN_Refined\\assets\\export_langpacks.py
产物: CN_Refined\\originalassets\\langpacks\\lang-*          （原始包，只读基线）
      CN_Refined\\assets\\out\\langpacks\\<lang>.tsv          （导出文本）
      CN_Refined\\assets\\out\\langpacks.txt                  （统计）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = Path(r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data")
SRC = GAME / "StreamingAssets"
BASE = ROOT / "CN_Refined" / "originalassets" / "langpacks"
OUTD = HERE / "out" / "langpacks"
LANGTOOL = ROOT / "hardcore" / "langtool" / "bin" / "Release" / "net8.0" / "langtool.exe"
LANGS = ["ar", "de", "en", "es", "fr", "it", "ja", "ko", "pl", "pt", "ru", "uk",
         "zh-s", "zh-t"]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    OUTD.mkdir(parents=True, exist_ok=True)
    if not LANGTOOL.exists():
        print("找不到 langtool: %s" % LANGTOOL)
        return 2
    ok = True
    say("语言包收取与导出")
    say("=" * 78)
    say("  %-8s %10s %10s %8s %8s" % ("语言", "原始包", "导出 TSV", "键数", "字符数"))
    for lang in LANGS:
        src = SRC / ("lang-" + lang)
        if not src.exists():
            say("  %-8s ✗ 找不到 %s" % (lang, src))
            ok = False
            continue
        # 1) 收进基线（连同 manifest）
        for suffix in ("", ".manifest"):
            s = SRC / ("lang-" + lang + suffix)
            if s.exists():
                d = BASE / ("lang-" + lang + suffix)
                if not d.exists() or d.stat().st_size != s.stat().st_size:
                    d.write_bytes(s.read_bytes())
        # 2) 导出
        dst = OUTD / ("%s.tsv" % lang)
        p = subprocess.run([str(LANGTOOL), "export", str(src), str(dst)],
                           capture_output=True)
        if p.returncode != 0 or not dst.exists():
            say("  %-8s ✗ 导出失败 rc=%d %s"
                % (lang, p.returncode, p.stderr.decode("utf-8", "replace")[:120]))
            ok = False
            continue
        raw = dst.read_bytes().decode("utf-8-sig", "ignore")
        vals = [ln.split("\t", 1)[1] for ln in raw.splitlines() if "\t" in ln]
        chars = set("".join(vals))
        cjk = sum(1 for c in chars if 0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)
        say("  %-8s %10d %10d %8d %8d  (CJK %d)"
            % (lang, src.stat().st_size, dst.stat().st_size, len(vals), len(chars), cjk))

    text = "\n".join(lines)
    (HERE / "out" / "langpacks.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    print("\n报告 -> %s" % (HERE / "out" / "langpacks.txt"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
