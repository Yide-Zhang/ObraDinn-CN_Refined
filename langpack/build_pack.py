#!/usr/bin/env python3
"""按「版本 × 是否和谐」全量展开模板，生成可安装的完整语言包 TSV。

★ 版本即调色板：整列取 vN 就对 —— 表里已经做了镜像设计
    全名行: v1=当前全名  v2=v1  v3=英文名  v4=精修全名  v5=v4
    Short 行: v1=当前全名 v2=缩写 v3=英文短名 v4=精修全名 v5=精修缩写
    Dia 行:   v1=当前称呼 v2=v1  v3=英文称呼 v4=精修称呼 v5=v4
  所以「整列 v1」= 当前版（不缩写）、「整列 v2」= 当前版+缩写、
  「整列 v4」= 精修版、「整列 v5」= 精修版+缩写 ✓

★ 另一条正交的轴：对话单语/双语（`--dialog`）
    双语 = 模板原样（`原文 | 译文`）
    单语 = 把 dialog_* 行第一条 `|` 及其前面的原文删掉
  ⚠ `|` 在别的行**还有别的用途**（`crew_name_*` 是「全名|短名」、
    `fate_parts_*`/`fate_ent_*` 是多段数据、`glossary_*` 是「词条 | 释义」），
    所以**只能动 dialog_***，见 `analyze_pipes.py` 的结论（347 个 dialog 竖线无例外）。

用法:
    python CN_Refined/langpack/build_pack.py --all
    python CN_Refined/langpack/build_pack.py --version v4 --harmonized --dialog mono
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tokens as T  # noqa: E402

TPL = HERE / "extracted" / "template-zh-s.tsv"
# ★ 单语模板（由 make_mono_review.py 生成，**用户可手改**）：单语包以它为准，
#   因为有些行的原文不能删 —— 例：`dialog_d2_m0_fa` 的 `Signor`（意大利语）是确定籍贯的**线索**，
#   官方 zh-s 也写成「尼柯斯先生（Signor）」。所以**有单语模板时不再无脑删竖线前缀**。
MONO_TPL = HERE / "extracted" / "template-zh-s-mono.tsv"
# ★ 官方 zh-s：用来判定「单语下这一行的原文能不能删」
OFFICIAL = HERE / "extracted" / "original-zh-s.tsv"
TBL = HERE / "extracted" / "crew_name_variants.tsv"
DEFAULT_OUTDIR = HERE.parent / "out" / "packs"


def load_template(path: Path):
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    if lines and lines[-1] == "":
        lines.pop()
        tail = True
    else:
        tail = False
    return lines, eol, tail


def strip_original(key: str, val: str) -> str:
    """把「原文 | 译文」变成只有译文。

    ★ 只对 `dialog_*` 生效 —— 别的键里的 `|` 是数据分隔（crew_name_* / fate_* /
      glossary_*），删了就把数据弄坏了。规则的安全性见 analyze_pipes.py：
      dialog_* 里含 `|` 的 347 个键**全部**是「原文 | 译文」。
    """
    if not key.startswith("dialog_") or "|" not in val:
        return val
    return val.split("|", 1)[1].lstrip(" \t\u3000")


def mono_value(key: str, bi_val: str, official_val: str) -> str:
    """单语模式下这一行该是什么。

    ★★ 规则（用户 2026-10-06 定）：**官方 zh-s 自己那一行带 `|` 的，单语也保留原文**。
       那些原文是线索（外语台词如 `Signor`、闽南语原句如 `慢且！伊無做毋著代誌！`），
       删了就丢了推理依据；官方那一行没带 `|` 的，才按「删竖线前缀」处理。
       （实测：347 个含竖线的 dialog 行里有 **29** 行属于这类。）
    """
    if not key.startswith("dialog_"):
        return bi_val
    if "|" in (official_val or ""):
        return bi_val
    return strip_original(key, bi_val)


def load_map(path: Path) -> dict:
    if not path or not path.exists():
        return {}
    m = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#") or "\t" not in ln:
            continue
        k, v = ln.split("\t", 1)
        m[k] = v
    return m


# 兼容旧名（make_mono_review.py 曾用 load_mono_map）
def load_mono_map(path: Path) -> dict:
    return load_map(path)


def build(version: str, harmonized: bool, names, lines, missing,
          dialog: str = "bilingual", mono_map: dict | None = None,
          official: dict | None = None, kept: list | None = None) -> list:
    out = []
    for ln in lines:
        if not ln.strip() or ln.startswith("#"):
            out.append(ln)
            continue
        f = ln.split("\t", 1)
        if len(f) != 2:
            out.append(ln)
            continue
        key, val = f
        if dialog == "mono":
            strict = mono_value(key, val, (official or {}).get(key, ""))
            mv = (mono_map or {}).get(key)
            if mv is not None:
                if mv != strict and kept is not None:
                    # 单语模板与「规则值」不同 = 手改有意保留原文（如 Signor）
                    kept.append((key, strict, mv))
                val = mv
            else:
                val = strict
        out.append(key + "\t" + T.expand(val, names, harmonized, T.difficulty_of(key),
                                        palette="refined", forced_version=version,
                                        missing=missing))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v4", choices=["v1", "v2", "v3", "v4", "v5"])
    ap.add_argument("--harmonized", action="store_true")
    ap.add_argument("--unharmonized", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="生成 5 版本 × 2 和谐 × 2 对话 = 20 个包")
    ap.add_argument("--dialog", default="bilingual", choices=["bilingual", "mono"],
                    help="bilingual=原文 | 译文（默认）；mono=只留译文")
    ap.add_argument("--out", help="单个输出文件（--all 时忽略）")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--template", default=str(TPL),
                    help="改用别的模板（如 template-zh-s-mono.tsv）")
    ap.add_argument("--mono-template", default=str(MONO_TPL),
                    help="单语包以此为权威（保留用户手改的行）；不存在则回退到严格删前缀")
    ap.add_argument("--no-mono-template", action="store_true",
                    help="忽略单语模板，强制按「删竖线前缀」生成")
    args = ap.parse_args()

    lines, eol, tail = load_template(Path(args.template))
    names = T.load_names(TBL)
    mono_map = {} if args.no_mono_template else load_map(Path(args.mono_template))
    official = load_map(OFFICIAL)
    if any(d == "mono" for _v, _h, d in
           ([(v, h, d) for v in ("v1", "v2", "v3", "v4", "v5") for h in (True, False)
             for d in ("bilingual", "mono")] if args.all
            else [(args.version, args.harmonized or not args.unharmonized, args.dialog)])):
        print("单语模板: %s%s" % (args.mono_template,
                                "（%d 键）" % len(mono_map) if mono_map else " —— 读不到，回退到严格删前缀"))

    jobs = []
    if args.all:
        for v in ("v1", "v2", "v3", "v4", "v5"):
            for h in (True, False):
                for d in ("bilingual", "mono"):
                    jobs.append((v, h, d))
    else:
        h = args.harmonized or not args.unharmonized
        jobs.append((args.version, h, args.dialog))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rep = []
    ok = True
    for v, h, d in jobs:
        missing = set()
        kept: list = []
        built = build(v, h, names, lines, missing, dialog=d,
                      mono_map=mono_map if d == "mono" else None,
                      official=official, kept=kept)
        if args.out and len(jobs) == 1:
            dst = Path(args.out)
            dst.parent.mkdir(parents=True, exist_ok=True)
        else:
            dst = outdir / ("zh-s-%s-%s-%s.tsv"
                            % (v, "harm" if h else "unharm", "bi" if d == "bilingual" else "mono"))
        dst.write_bytes((eol.join(built) + (eol if tail else "")).encode("utf-8"))
        keys = sum(1 for x in built if x.strip() and not x.startswith("#"))
        rep.append("%-6s %-7s %-5s -> %-30s %d 键%s"
                   % (v, "和谐" if h else "未和谐", "双语" if d == "bilingual" else "单语",
                      dst.name, keys,
                      "" if not missing else "  !! 未展开: %s" % ", ".join(sorted(missing))))
        if kept:
            say_kept = "       ★ 按单语模板**保留原文**的行 %d 个（与严格删不同）:" % len(kept)
            rep.append(say_kept)
            for k, st, mv in kept:
                rep.append("         %-22s 严格删=%r → 模板=%r" % (k, st[:28], mv[:48]))
        if missing:
            ok = False

    text = "\n".join(rep) + "\n"
    Path(outdir / "BUILD.txt").write_text(text, encoding="utf-8-sig")
    sys.stdout.write(text)
    print("（清单也写在 %s）" % (outdir / "BUILD.txt"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
