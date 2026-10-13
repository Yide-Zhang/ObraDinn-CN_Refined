# -*- coding: utf-8 -*-
"""清单分析：游戏原始 sharedassets{0,2,6} vs 旧开发产物（替换过字体的）。

目的：找出「注入字体后体积从 28/34MB 涨到 87MB」到底是哪些对象撑起来的。

用法: python CN_Refined\\assets\\inventory_assets.py
产物: CN_Refined\\assets\\out\\inventory.txt
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets"
OLD = ROOT / "CN_Refined" / "olddevassets"
OUTDIR = ROOT / "CN_Refined" / "assets" / "out"
REPORT = OUTDIR / "inventory.txt"

FILES = ["sharedassets0.assets", "sharedassets2.assets", "sharedassets6.assets"]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def fmt_of(v) -> str:
    try:
        return v.name
    except Exception:
        return str(v)


def inventory(path: Path):
    """-> (总字节, [ {type,name,pathid,size,extra} ])"""
    env = UnityPy.load(str(path))
    rows = []
    for obj in env.objects:
        t = obj.type.name
        size = obj.byte_size
        name, extra = "", ""
        try:
            d = obj.read()
        except Exception as e:                      # noqa: BLE001
            rows.append({"type": t, "name": "<?>", "pathid": obj.path_id,
                         "size": size, "extra": "读取失败 %s" % e})
            continue
        name = getattr(d, "m_Name", None) or getattr(d, "name", "") or ""
        if t == "Font":
            fd = getattr(d, "m_FontData", b"") or b""
            extra = ("fontData=%s  ascii=%d  size=%s  spc=%s  tex=%s"
                     % (human(len(fd)), len(getattr(d, "m_Ascii", b"") or b""),
                        getattr(d, "m_FontSize", "?"),
                        getattr(d, "m_CharacterSpacing", "?"),
                        int(getattr(d, "m_Texture", None).m_PathID
                            if getattr(d, "m_Texture", None) else 0)))
        elif t == "Texture2D":
            sd = getattr(d, "m_StreamData", None)
            sp = getattr(sd, "path", "") if sd else ""
            ss = getattr(sd, "size", 0) if sd else 0
            so = getattr(sd, "offset", 0) if sd else 0
            extra = ("%dx%d  fmt=%s  mip=%s  imgSize=%s  stream=%s"
                     % (d.m_Width, d.m_Height, fmt_of(d.m_TextureFormat),
                        getattr(d, "m_MipCount", "?"),
                        human(getattr(d, "m_CompleteImageSize", 0) or 0),
                        ("%s @%d +%s" % (Path(sp).name, so, human(ss))) if sp else "内嵌"))
            size = size + (0 if sp else (getattr(d, "m_CompleteImageSize", 0) or 0))
        elif t == "TextAsset":
            extra = "script=%s" % human(len(getattr(d, "m_Script", b"") or b""))
        elif t == "MonoBehaviour":
            extra = getattr(d, "m_Name", "") or ""
        rows.append({"type": t, "name": name, "pathid": obj.path_id,
                     "size": size, "extra": extra})
    return path.stat().st_size, rows


def human(n: int) -> str:
    for u, d in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        ops, ods = ORIG / f, OLD / f
        if not ops.exists():
            say("缺 %s（原始）" % ops)
            continue
        # 同时报出伴生的 .resS
        for p in (ORIG / (f + ".resS"), OLD / (f + ".resS")):
            say("  %-52s %s" % (p, human(p.stat().st_size) if p.exists() else "（无）"))
        s_o, r_o = inventory(ops)
        say("=" * 92)
        say("%s" % f)
        say("=" * 92)
        if not ods.exists():
            say("  （没有对应的旧产物）")
            say("")
            continue
        s_d, r_d = inventory(ods)

        say("  文件大小: 原始 %s   →   旧产物 %s   （%+s）"
            % (human(s_o), human(s_d), human(s_d - s_o)))
        say("  对象数  : 原始 %d   →   旧产物 %d" % (len(r_o), len(r_d)))
        say("")

        say("  【按类型汇总】（对象序列化字节数之和）")
        co, cd = Counter(), Counter()
        for r in r_o:
            co[r["type"]] += r["size"]
        for r in r_d:
            cd[r["type"]] += r["size"]
        say("    %-18s %14s %14s %14s" % ("类型", "原始", "旧产物", "增量"))
        for t in sorted(set(co) | set(cd), key=lambda t: -(cd[t] - co[t])):
            say("    %-18s %14s %14s %14s"
                % (t, human(co[t]), human(cd[t]), human(cd[t] - co[t])))
        say("")

        # 逐个对象对比（按「类型+名字」匹配）
        mo = defaultdict(list)
        for r in r_o:
            mo[(r["type"], r["name"])].append(r)
        md = defaultdict(list)
        for r in r_d:
            md[(r["type"], r["name"])].append(r)
        diff = []
        for k in set(mo) | set(md):
            so = sum(r["size"] for r in mo.get(k, []))
            sd = sum(r["size"] for r in md.get(k, []))
            if sd != so:
                diff.append((sd - so, k, so, sd, mo.get(k, []), md.get(k, [])))
        diff.sort(reverse=True)
        say("  【体积变化最大的对象】（原始 → 旧产物）")
        for d, (t, n), so, sd, ro, rd in diff[:15]:
            say("    %+12s  %-14s %s" % (human(d), t, n or "<无名>"))
            say("                 原始 %s ×%d   →   旧产物 %s ×%d"
                % (human(so), len(ro), human(sd), len(rd)))
            for r in (rd or ro)[:1]:
                if r["extra"]:
                    say("                 旧产物详情: %s" % r["extra"])
            for r in (ro or rd)[:1]:
                if r["extra"] and rd:
                    say("                 原始详情  : %s" % r["extra"])
        say("")
        say("  【字体对象明细】")
        for label, rows in (("原始", r_o), ("旧产物", r_d)):
            for r in rows:
                if r["type"] == "Font":
                    say("    %-6s pathId=%-22s %-30s size=%-9s %s"
                        % (label, r["pathid"], r["name"], human(r["size"]), r["extra"]))
        say("  【Texture2D 明细】（按体积降序，前 12）")
        for label, rows in (("原始", r_o), ("旧产物", r_d)):
            ts = sorted([r for r in rows if r["type"] == "Texture2D"],
                        key=lambda r: -r["size"])
            say("    -- %s 共 %d 个，合计 %s"
                % (label, len(ts), human(sum(r["size"] for r in ts))))
            for r in ts[:12]:
                say("       pathId=%-22s %-34s size=%-9s %s"
                    % (r["pathid"], r["name"] or "<无名>", human(r["size"]), r["extra"]))
        say("  【TextAsset 明细】")
        for label, rows in (("原始", r_o), ("旧产物", r_d)):
            for r in rows:
                if r["type"] == "TextAsset":
                    say("    %-6s pathId=%-22s %-30s size=%-9s %s"
                        % (label, r["pathid"], r["name"], human(r["size"]), r["extra"]))
        say("")

    text = "\n".join(lines)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    # 控制台只输出 ASCII-安全的摘要
    print("\n".join(l for l in lines if l.isascii()))
    print("\n报告已写入 %s" % REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
