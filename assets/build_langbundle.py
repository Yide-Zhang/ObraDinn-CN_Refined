# -*- coding: utf-8 -*-
"""把「某版本 × 和谐 × 单双语」的成品语言包**做成可安装的 lang-zh-s**（字符串 + 图一起）。

为什么两步：
  1. 字符串用 `langtool set ... --pack=lzma`（用户既有工具链、游戏里实测可用）
  2. 图（ManifestCrew / FolioSketch）langtool 不管，用 UnityPy 换 Texture2D 再 `packer="lzma"` 存
     （实测这种包 UnityPy 往返无损：11 个对象摘要全一致）
     图存成 **RGBA32 无损**（原来包内是 DXT1；无损可以避免二次压缩把字糊掉，代价是包变大）

用法:
  python CN_Refined\\assets\\build_langbundle.py --version v5 --harm unharm --dialog bi
  python CN_Refined\\assets\\build_langbundle.py --version v5 --harm unharm --dialog bi --install
产物: CN_Refined\\out\\langbundle\\lang-zh-s  +  assets\\out\\langbundle.txt
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import UnityPy
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = Path(r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data")
SA = GAME / "StreamingAssets"
BASE = ROOT / "CN_Refined" / "originalassets" / "langpacks" / "lang-zh-s"
PACKS = ROOT / "CN_Refined" / "out" / "packs"
TEX = ROOT / "CN_Refined" / "out" / "textures"
SRCTEX = ROOT / "CN_Refined" / "Textures"          # 用户做的四张全图（基准）
OUTDIR = ROOT / "CN_Refined" / "out" / "langbundle"
REPORT = HERE / "out" / "langbundle.txt"
LANGTOOL = ROOT / "hardcore" / "langtool" / "bin" / "Release" / "net8.0" / "langtool.dll"

# 版本 -> 姓名列图用哪一套（v1/v2 = 当前名、v3 = 英文名、v4/v5 = 精修名）
NAME_AXIS = {"v1": "zh", "v2": "zh", "v3": "en", "v4": "refined", "v5": "refined"}

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def img_digest(img: Image.Image) -> str:
    return hashlib.sha256(img.convert("RGBA").tobytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v5", choices=sorted(NAME_AXIS))
    ap.add_argument("--harm", default="unharm", choices=["unharm", "harm"])
    ap.add_argument("--dialog", default="bi", choices=["bi", "mono"])
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--keep-step1", action="store_true")
    ap.add_argument("--packer", default="lzma", choices=["lzma", "lz4", "none"],
                    help="成品包的压缩；lzma=与原包一致，none=未压缩（langtool 默认那种，最保险）")
    args = ap.parse_args()

    tag = "zh-s-%s-%s-%s" % (args.version, args.harm, args.dialog)
    pack = PACKS / ("%s.tsv" % tag)
    region = "harm" if args.harm == "harm" else "unharm"
    name_axis = NAME_AXIS[args.version]
    # ★★ 四张图**全部以用户做的全图（CN_Refined/Textures/*.png）为基准**：
    #   · ManifestCrew / FolioSketch：在用户全图上贴碎片（paste_fragments.py 的产物）
    #   · FolioDeck / FolioChart：没有需要本地化的文字 → 直接用用户全图原图
    #   （实测：用户全图与官方包在碎片矩形**之外**也不同 —— FolioDeck 差 329,973 px，
    #     所以绝不能保留官方那两张。）
    tex_map = {
        "ManifestCrew": TEX / ("ManifestCrew-%s-%s.png" % (name_axis, region)),
        "FolioSketch": TEX / ("FolioSketch-%s.png" % region),
        "FolioDeck": SRCTEX / "FolioDeck.png",
        "FolioChart": SRCTEX / "FolioChart.png",
    }

    say("打语言包 bundle: %s" % tag)
    say("=" * 92)
    ok = True
    for p, what in ((BASE, "基准包(官方 zh-s)"), (pack, "成品 TSV"), (LANGTOOL, "langtool")):
        say("  %-16s %s%s" % (what, p, "" if p.exists() else "   ✗ 不存在"))
        ok &= p.exists()
    for k, p in tex_map.items():
        say("  %-16s %s%s" % ("图 " + k, p.name, "" if p.exists() else "   ✗ 不存在"))
        ok &= p.exists()
    if not ok:
        (HERE / "out" / "langbundle.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    say("")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    step1 = OUTDIR / "_step1-lang-zh-s"

    # ---- 1) 字符串：langtool set ----
    dotnet = shutil.which("dotnet") or "dotnet"
    cmd = [dotnet, str(LANGTOOL), "set", str(BASE), str(step1), str(pack), "--pack=lzma"]
    say("1) 写字符串: langtool set --pack=lzma")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    o_lines = [l.rstrip() for l in (r.stdout or "").splitlines() if l.strip()]
    if len(o_lines) > 24:                      # langtool 会逐条打印 985 行，只留头尾
        o_lines = o_lines[:6] + ["   …（中间 %d 行省略）" % (len(o_lines) - 16)] + o_lines[-10:]
    for ln in o_lines:
        say("   " + ln)
    if r.returncode != 0 or not step1.exists():
        say("   ✗ 失败（返回码 %d）" % r.returncode)
        for ln in (r.stderr or "").splitlines()[:12]:
            say("   ! " + ln.rstrip())
        (HERE / "out" / "langbundle.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    say("   → %s  %s" % (step1.name, human(step1.stat().st_size)))
    say("")
    print("  [1/3] langtool set OK -> %s" % human(step1.stat().st_size), flush=True)

    # ---- 2) 图：UnityPy 换 Texture2D ----
    say("2) 换图（UnityPy, 存 RGBA32 无损, packer=lzma）")
    env = UnityPy.load(str(step1))
    done = []
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        nm = getattr(d, "m_Name", "")
        if nm not in tex_map:
            continue
        before = (d.m_Width, d.m_Height, str(d.m_TextureFormat))
        src = Image.open(tex_map[nm])
        if src.size != (d.m_Width, d.m_Height):
            say("   ✗ %s 尺寸不符: 图 %s vs 包内 %sx%s"
                % (nm, src.size, d.m_Width, d.m_Height))
            ok = False
            continue
        d.set_image(src.convert("RGBA"), target_format=UnityPy.enums.TextureFormat.RGBA32)
        d.save()
        after = (d.m_Width, d.m_Height, str(d.m_TextureFormat))
        done.append((nm, before, after))
        say("   %-14s %sx%s %s → %sx%s %s   （源图 %s）"
            % (nm, before[0], before[1], before[2], after[0], after[1], after[2], tex_map[nm].name))
    if not done:
        say("   ✗ 一个图都没换成")
        ok = False
    out = OUTDIR / "lang-zh-s"
    data = env.file.save(packer=(None if args.packer == "none" else args.packer))
    out.write_bytes(data)
    say("   写出 %s  %s（基准 %s，%+d）"
        % (out.name, human(len(data)), human(BASE.stat().st_size), len(data) - BASE.stat().st_size))
    if not args.keep_step1:
        try:
            step1.unlink(missing_ok=True)
        except PermissionError:
            say("   （中间包被 UnityPy 占着，留着不删：%s）" % step1.name)
    print("  [1/3] strings written+repacked, [2/3] textures replaced -> %s" % out.name, flush=True)
    say("")

    # ---- 3) 验证 ----
    say("3) 验证")
    print("  [3/3] verifying ...", flush=True)
    # 3a) 字符串：把成品包再 export 出来，与我们的 TSV 逐字节比
    tmp = OUTDIR / "_verify.tsv"
    getattr_ok = True
    cmd = [dotnet, str(LANGTOOL), "export", str(out), str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.exists():
        say("   ✗ export 失败: %s" % (r.stderr or "").strip()[:200])
        getattr_ok = False
    else:
        exp = tmp.read_text(encoding="utf-8-sig")
        exp_lines = [l for l in exp.splitlines() if l and not l.startswith("#")]
        ours = [l for l in pack.read_text(encoding="utf-8-sig").splitlines() if l]
        same = 0
        diff = []
        d_ours = dict(l.split("\t", 1) for l in ours if "\t" in l)
        for l in exp_lines:
            k, v = l.split("\t", 1)
            if d_ours.get(k) == v:
                same += 1
            else:
                diff.append(k)
        say("   字符串: 回读 %d 条，与成品 TSV 一致 %d 条，不一致 %d 条%s"
            % (len(exp_lines), same, len(diff), ("  例: %s" % diff[:5]) if diff else "  ✓"))
        missing = sorted(set(d_ours) - {l.split("\t", 1)[0] for l in exp_lines})
        if missing:
            say("   ✗ 包里缺键 %d 个: %s" % (len(missing), missing[:5]))
        ok &= (not diff and not missing)
        tmp.unlink(missing_ok=True)
    # 3b) 图：重新读回，像素与源 PNG 比
    env2 = UnityPy.load(str(out))
    n_obj = 0
    for o in env2.objects:
        n_obj += 1
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        nm = getattr(d, "m_Name", "")
        if nm not in tex_map:
            continue
        got = d.image
        want = Image.open(tex_map[nm])
        same = img_digest(got) == img_digest(want)
        say("   图 %-14s 回读 %sx%s %s  像素%s"
               % (nm, got.size[0], got.size[1], str(d.m_TextureFormat),
                  "与源 PNG 完全一致 ✓" if same else "**不一致 ✗**"))
        ok &= same
    say("   对象数 %d（基准 11）%s" % (n_obj, " ✓" if n_obj == 11 else " ✗"))
    ok &= (n_obj == 11)
    # 3c) 备用包：未压缩那版（langtool 默认写出的形式，用户工具链实测可用）
    if args.packer == "lzma":
        alt = OUTDIR / "lang-zh-s-none"
        alt.write_bytes(env.file.save(packer=None))
        say("   备用包（未压缩，游戏不认压缩版时可换！）: %s  %s"
            % (alt.name, human(alt.stat().st_size)))
    say("")

    if args.install:
        say("4) 安装到游戏")
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bk = ROOT / "CN_Refined" / "originalassets" / ("_gamebackup-%s" % ts)
        bk.mkdir(parents=True, exist_ok=True)
        cur = SA / "lang-zh-s"
        if cur.exists():
            shutil.copy2(cur, bk / "lang-zh-s")
            say("   备份 → %s\\lang-zh-s" % bk.name)
        shutil.copy2(out, cur)
        h1, h2 = sha(cur.read_bytes()), sha(out.read_bytes())
        say("   已装入 %s   %s   sha=%s %s"
            % (cur, human(cur.stat().st_size), h1, "✓ 一致" if h1 == h2 else "✗ 不一致"))
        ok &= (h1 == h2)
    say("")
    say("全部通过 ✓" if ok else "⚠ 有问题，见上")
    (HERE / "out" / "langbundle.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
