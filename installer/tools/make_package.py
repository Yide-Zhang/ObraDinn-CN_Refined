# -*- coding: utf-8 -*-
"""把随包资源组装进 CN_Refined/installer/ ，并生成 data/known-hashes.json。

    python CN_Refined\\installer\\tools\\make_package.py            # 全量（会重建字体子集，慢）
    python CN_Refined\\installer\\tools\\make_package.py --skip-fonts

产物（全部随安装包发布）::

    assets/fonts/A-*.otf             字体子集 A（注入游戏用；身份名已按游戏 donor 恢复）
    assets/lang-zh-s-official        官方 zh-s 包 —— 重建 lang-zh-s 的**唯一基线**
    assets/packs/zh-s-*.tsv          20 个字符串替换表（5 版本 x 和谐 x 双语）
    assets/textures/*.png            4 张贴图 / 10 个文件（名字轴 x 和谐/未和谐）
    assets/sharedassets6.assets      预生成整文件（UnityPy 写这个文件会丢类型树，必须预生成）
    assets/langtool/langtool.exe     自包含 single-file（另建，本脚本不碰）
    data/known-hashes.json           已知哈希（原版 / 我们的）→ 安装器状态判定用

★ 每份资源都记 sha/size 到 out/package.txt（GBK 控制台会把中文弄乱，读文件才准）。
★ 幂等：重复跑只是覆盖同一份文件，不产生增量垃圾。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                                  # CN_Refined/installer/
ROOT = PKG.parents[1]                              # ObraDinnSave/
CR = ROOT / "CN_Refined"
ORIG = CR / "originalassets"

A = PKG / "assets"
D = PKG / "data"
OUT = PKG / "out"

sys.path.insert(0, str(CR / "assets"))
import inject_fonts as INJ                          # noqa: E402  字体口径与游戏内注入**必须同一份**

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def copy(src: Path, dst: Path, note: str = "") -> bool:
    if not src.is_file():
        say("  ✗ 缺源 %s" % src)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    say("  ✓ %-46s <- %s  %s%s"
        % (dst.relative_to(PKG).as_posix(), src.relative_to(ROOT).as_posix(),
           human(dst.stat().st_size), ("  " + note) if note else ""))
    return True


# ---------------------------------------------------------------------------
def do_fonts(level: str) -> bool:
    """重建字体子集 A（口径 = inject_fonts，身份名 donor = 游戏原始内嵌那支）"""
    say("字体子集 A（档位 %s，身份名按游戏 donor 恢复）" % level)
    charset, stat = INJ.MS.collect_chars()
    say("  字符集 %d 个（CJK %d）" % (len(charset), INJ.MS.cjk_count(charset)))
    ok = True
    for fn, jobs in INJ.JOBS.items():
        for fname, fsrc in jobs.items():
            if not fsrc.exists():
                say("  ✗ 缺字体源 %s" % fsrc)
                ok = False
                continue
            data, idn = INJ.make_subset(fsrc, charset, level, INJ.IDENT.get(fname))
            tag = "SC" if "Serif" in fname else "851"
            dst = A / "fonts" / ("A-%s-subset.otf" % ("SourceHanSerifSC-SemiBold"
                                                      if "Serif" in fname
                                                      else "851tegaki_zatsu_normal_0883"))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            af = (idn or {}).get("after", {})
            say("  ✓ %-46s %s  源 %s" % (dst.relative_to(PKG).as_posix(),
                                         human(len(data)), human(fsrc.stat().st_size)))
            say("      身份名 family=%r name1=%r name6=%r"
                % (af.get("cff_family"), af.get("name1"), af.get("name6")))
            say("      sha=%s" % hashlib.sha256(data).hexdigest()[:16])
            # 自检：字体内部家族名必须能对上 Font 对象的 m_FontNames，否则 Unity 整支回落
            want = {"SourceHanSerif-SemiBold": "Source Han Serif",
                    "851tegaki_zatsu_normal_0883": "851tegakizatsu"}.get(fname, "")
            got = af.get("cff_family") or af.get("name1") or ""
            if want and want not in str(got):
                say("      ✗ 身份名对不上（要含 %r，实得 %r）—— Unity 会回落系统字体！" % (want, got))
                ok = False
            elif want:
                say("      身份名自检 ✓（m_FontNames 认 %r）" % want)
    return ok


def do_langpack() -> bool:
    say("官方语言包（重建基线）")
    return copy(ORIG / "langpacks" / "lang-zh-s", A / "lang-zh-s-official")


def do_packs() -> bool:
    say("字符串替换表（20 个）")
    ok = True
    n = 0
    for v in ("v1", "v2", "v3", "v4", "v5"):
        for harm in ("harm", "unharm"):
            for dlg in ("bi", "mono"):
                nm = "zh-s-%s-%s-%s.tsv" % (v, harm, dlg)
                if copy(CR / "out" / "packs" / nm, A / "packs" / nm):
                    n += 1
                else:
                    ok = False
    say("  共 %d/20" % n)
    return ok


def do_textures() -> bool:
    """4 张贴图 / 10 个文件 —— **全部以我做的全图为基准**
       ManifestCrew / FolioSketch 有名字轴与和谐两个维度，FolioDeck / FolioChart 只有全图
    """
    say("贴图（4 张全图派生 10 个文件）")
    ok = True
    for axis in ("zh", "refined", "en"):
        for harm in ("harm", "unharm"):
            nm = "ManifestCrew-%s-%s.png" % (axis, harm)
            ok &= copy(CR / "out" / "textures" / nm, A / "textures" / nm)
    for harm in ("harm", "unharm"):
        nm = "FolioSketch-%s.png" % harm
        ok &= copy(CR / "out" / "textures" / nm, A / "textures" / nm)
    for nm in ("FolioDeck.png", "FolioChart.png"):
        ok &= copy(CR / "Textures" / nm, A / "textures" / nm)
    return ok


def do_shs6() -> bool:
    say("sharedassets6（预生成整文件，13 KB 级）")
    return copy(CR / "out" / "assets" / "sharedassets6.assets", A / "sharedassets6.assets",
                note="UnityPy 不能写这个文件，所以随包预生成")


def do_hashes() -> bool:
    """已知哈希表：让安装器能判「原版 / 我们的 / 他方」"""
    say("已知哈希表")
    kh: dict = {
        "note": "各文件已知 sha256。official_* = 原版；shs/langpack = 我们的历史产物（状态判定用）",
        "official": {},
        "shs": {},
        "shs_alt": {},
        "langpack": {},
    }
    # 原版：_pristine 是真·原版；_gamebackup-* 是我们动手前的中间态
    pris = ORIG / "_pristine"
    for nm in ("sharedassets0.assets", "sharedassets2.assets", "sharedassets6.assets"):
        p = pris / nm
        if p.is_file():
            kh["official"][nm] = sha_file(p)
            say("  原版 %-28s %s" % (nm, kh["official"][nm][:16]))
    # 原版 DLL（wrap 补丁前）→ 安装器用它判「这 DLL 是不是动过」
    dll = ORIG / "_gamebackup-20261006-220426" / "Assembly-CSharp.dll"
    if dll.is_file():
        kh["official_dll"] = sha_file(dll)
        say("  原版 %-28s %s" % ("Assembly-CSharp.dll", kh["official_dll"][:16]))
    # 官方语言包
    lp = ORIG / "langpacks" / "lang-zh-s"
    if lp.is_file():
        kh["official_lang"] = sha_file(lp)
        say("  官方 %-28s %s" % ("lang-zh-s", kh["official_lang"][:16]))
    # 我们的产物（当前 + 历史）：list 形式，安装器用 in 判定
    ours = {
        "sharedassets0.assets": [CR / "out" / "assets" / "sharedassets0.assets",
                                 ORIG / "_gamebackup-20261006-204418" / "sharedassets0.assets",
                                 ORIG / "_gamebackup-20261006-203106" / "sharedassets0.assets"],
        "sharedassets2.assets": [CR / "out" / "assets" / "sharedassets2.assets",
                                 ORIG / "_gamebackup-20261006-204418" / "sharedassets2.assets",
                                 ORIG / "_gamebackup-20261006-203106" / "sharedassets2.assets"],
        "sharedassets6.assets": [CR / "out" / "assets" / "sharedassets6.assets",
                                 ORIG / "_gamebackup-20261006-204418" / "sharedassets6.assets"],
    }
    for nm, cands in ours.items():
        seen = []
        for p in cands:
            if p.is_file():
                h = sha_file(p)
                if h not in seen and h not in kh["official"].values():
                    seen.append(h)
        kh["shs"][nm] = seen
        say("  我们的 %-26s %s" % (nm, [h[:10] for h in seen]))
    # 语言包：我们建过的版本（_gamebackup 里的即历史产物；当前安装的那份让引擎报 ours 靠哈希表）
    for tag, p in (("215911", ORIG / "_gamebackup-20261006-215911" / "lang-zh-s"),
                   ("224009", ORIG / "_gamebackup-20261006-224009" / "lang-zh-s")):
        if p.is_file():
            kh["langpack"][sha_file(p)] = "我们的产物（%s 备份）" % tag
    # 当前游戏里那份也记住（本机自测用；别人机器上不会命中，无副作用）
    gl = Path("F:/AceAttorneySeries/gameFiles/steamapps/common/ObraDinn/ObraDinn_Data/"
              "StreamingAssets/lang-zh-s")
    if gl.is_file():
        kh["langpack"][sha_file(gl)] = "我们的产物（本机自测）"
    say("  语言包已知产物 %d 个" % len(kh["langpack"]))

    D.mkdir(parents=True, exist_ok=True)
    p = D / "known-hashes.json"
    p.write_text(json.dumps(kh, ensure_ascii=False, indent=1), encoding="utf-8")
    say("  ✓ %s" % p.relative_to(PKG).as_posix())
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="B", choices=sorted(INJ.LEVELS),
                    help="字体子集档位（游戏内注入用 B）")
    ap.add_argument("--skip-fonts", action="store_true", help="字体子集已就绪时跳过（省几分钟）")
    a = ap.parse_args()

    ok = True
    if not a.skip_fonts:
        ok &= do_fonts(a.level)
    else:
        say("字体子集：已跳过（--skip-fonts）")
    ok &= do_langpack()
    ok &= do_packs()
    ok &= do_textures()
    ok &= do_shs6()
    ok &= do_hashes()

    say("")
    say("包内资源汇总")
    for p in sorted(A.rglob("*")):
        if p.is_file():
            say("  %-52s %s" % (p.relative_to(A).as_posix(), human(p.stat().st_size)))
    tot = sum(p.stat().st_size for p in A.rglob("*") if p.is_file())
    say("  合计 %s" % human(tot))
    say("")
    say("组装%s" % ("完成 ✓" if ok else "有缺项 ✗"))

    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / "package.txt"
    rp.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("报告: %s" % rp)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
