#!/usr/bin/env python3
"""langtool 跨平台等价自检 —— 证明 macOS 版 langtool 与 Windows 版**逐字节一致**。

为什么需要它：
  langtool 是「裁剪 + single-file」发布的 .NET 二进制，Windows 上只能**发布** macOS 版，
  跑不起来；而安装器在 mac 上要靠它做两件大事 ——

      patchwrap <DLL> <out>              （换行修补 wrap-1，改的是游戏 DLL）
      set <官方包> <out> <tsv> --pack=lzma（重建 lang-zh-s 语言包）

  这两件事一旦产出的字节和 Windows 版不同，就等于「mac 版补丁内容与 Windows 版不是同一个东西」。
  所以本脚本把这两条命令**在仓库内固定输入**上跑一遍，拿产出 sha 与参考值比：

      Windows 上：python CN_Refined/installer/tools/selftest_langtool.py --record
                  → 把参考值写进 assets/langtool/reference.json

      Mac 上：    python3 CN_Refined/installer/tools/selftest_langtool.py
                  → 跑同样的命令，与 Windows 录下的 sha 对比，一致才算 PASS

★ 为什么输入要用仓库内的固定文件，而不是各自机器上的游戏文件：
  游戏 DLL 在 mac 上是另一个构建（内容不同），拿它比 sha 只能证明「各自确定性」，
  证明不了「两个平台的 langtool 等价」。用同一个输入 + 同一个期望 sha，才是真等价性。

★ 输入变了怎么办（比如语言包又加了一版 TSV）：
  自检会发现输入的 sha 与参考值不符 → 提示「参考值过期」，此时在 Windows 上重录一次即可。

★ patchwrap 需要 --deps（Unity 程序集目录），否则 Cecil 解不了引用直接报
  AssemblyResolutionException。实测：把整个 Managed 目录拷到别处再跑，产出**字节相同**
  → 所以 --deps 只影响「能不能解到」，不影响产出；mac 上用自己的游戏目录即可。

用法：
    python tools/selftest_langtool.py            # 自检（用当前平台的 langtool）
    python tools/selftest_langtool.py --record   # 记录 / 刷新参考值（一般在 Windows 上做）
    python tools/selftest_langtool.py --langtool <路径>   # 指定二进制
    python tools/selftest_langtool.py --deps <Managed 目录>  # 手动指定 Unity 程序集目录
    python tools/selftest_langtool.py --keep     # 保留临时产物，便于出事时比对
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                       # CN_Refined/installer
ROOT = PKG.parents[1]                   # 仓库根
LT_DIR = PKG / "assets" / "langtool"
REF = LT_DIR / "reference.json"

# 固定输入（都在仓库里，两个平台都能拿到同一份）
# ★ patchwrap 的输入必须是**纯原版**（没打过 wrap 的）DLL，否则参考值对不上语义：
#   \u2022 patcher/assets/original/… 那份不是纯原版（工具判它「等价已打」，是旧工具打过的）；
#   \u2022 这几个是纯原版：仓库根的 originalDLLWin/ 与 CN_Refined/originalassets/_gamebackup-*/。
DEF_DLL_ORDER = [ROOT / "originalDLLWin" / "Assembly-CSharp.dll"]
DEF_BUNDLE = PKG / "assets" / "lang-zh-s-official"


def default_dll() -> Path | None:
    for p in DEF_DLL_ORDER:
        if p.is_file():
            return p
    # 退一步：originalassets 里最新的那份游戏备份
    cands = sorted((PKG / "originalassets").glob("_gamebackup-*/Assembly-CSharp.dll"),
                   key=lambda q: q.parent.name)
    return cands[-1] if cands else None


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def langtool_here() -> Path | None:
    """当前平台该用哪份 langtool（顺序与引擎 engine.langtool() 保持一致）。"""
    if sys.platform == "win32":
        p = LT_DIR / "langtool.exe"
        return p if p.is_file() else None
    # macOS：先看包里那份（打包后叫无扩展名的 langtool），再看开发树里按架构分的
    bundled = LT_DIR / "langtool"
    if bundled.is_file() and bundled.suffix == "":
        return bundled
    m = platform.machine().lower()
    name = "langtool-macos-arm64" if m in ("arm64", "aarch64") else "langtool-macos-x64"
    p = LT_DIR / name
    return p if p.is_file() else None


def latest_tsv() -> Path | None:
    """资产里版本号最大的 zh-s-vN-*.tsv（与 build_release/build_pack 的产出对应）。"""
    cands = []
    for p in sorted((PKG / "assets" / "packs").glob("zh-s-v*.tsv")):
        m = re.search(r"zh-s-v(\d+)-", p.name)
        if m:
            cands.append((int(m.group(1)), p.name, p))
    return max(cands)[2] if cands else None


def resolve_deps(explicit: str | None) -> Path | None:
    """patchwrap 要的 Unity 程序集目录（<游戏>/Data/Managed）。

    实测过：把整个目录拷到别处再跑，产出字节完全相同 → deps 只影响「能不能解到」。
    所以只需要一个**存在且装着游戏程序集**的目录，平台间不必一致。
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("OBRADINN_GAME")
    if env:
        g = Path(env).expanduser()
        if g.is_dir():
            try:
                sys.path.insert(0, str(PKG))          # engine 在上一层
                import engine as E                    # type: ignore[import-not-found]
                d = E.game_root(g) or g
                if E.game_root(g) is not None:
                    return (d / E.DLL_REL).parent
            except Exception:                         # noqa: BLE001
                pass
    try:
        sys.path.insert(0, str(PKG))
        import engine as E                                # type: ignore[import-not-found]
        game, _how = E.detect_game()
        if game:
            return (game / E.DLL_REL).parent
    except Exception as exc:                              # noqa: BLE001
        print("[i] 自动探测游戏失败：%s" % exc)
    return None


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None,
                       encoding="utf-8", errors="replace")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def info(p: Path, base: Path = ROOT) -> dict:
    try:
        rel = p.relative_to(base).as_posix()
    except ValueError:
        rel = str(p)
    return {"path": rel, "sha": sha(p), "size": p.stat().st_size}


def cmds(lt: Path, dll: Path, bundle: Path, tsv: Path, work: Path, deps: Path) -> dict:
    """要跑的两条命令（与 engine.step_dll / step_langpack 里实际用的一致）。"""
    return {
        "patchwrap": [str(lt), "patchwrap", str(dll), str(work / "wrapped.dll"),
                      "--deps=" + str(deps)],
        "set": [str(lt), "set", str(bundle), str(work / "zh-s.assets"), str(tsv), "--pack=lzma"],
    }


def measure(lt: Path, dll: Path, bundle: Path, tsv: Path, work: Path, deps: Path,
            verbose: bool = True) -> dict:
    """跑两条命令，返回产出 sha/尺寸 + 退出码。"""
    work.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    for key, cmd in cmds(lt, dll, bundle, tsv, work, deps).items():
        rc, txt = run(cmd)
        # 产物：patchwrap → work/wrapped.dll；set → work/zh-s.assets
        produced = work / ("wrapped.dll" if key == "patchwrap" else "zh-s.assets")
        if rc != 0 or not produced.is_file():
            out[key] = {"exit": rc, "out": txt[-600:]}
            if verbose:
                print("  ✗ %-9s 退出码=%d\n%s" % (key, rc, txt[-800:]))
            continue
        out[key] = {"exit": rc, "sha": sha(produced), "size": produced.stat().st_size}
        if verbose:
            print("  ✓ %-9s sha=%s  %d B" % (key, out[key]["sha"][:16] + "…", out[key]["size"]))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # type: ignore[union-attr]
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="langtool 跨平台等价自检")
    ap.add_argument("--record", action="store_true", help="记录/刷新参考值（Windows 上做）")
    ap.add_argument("--langtool", help="指定 langtool 可执行文件（默认按当前平台自动找）")
    ap.add_argument("--dll", help="patchwrap 用的输入 DLL（默认仓库内的纯原版 DLL）")
    ap.add_argument("--deps", help="Unity 程序集目录（默认自动探测游戏，或用 OBRADINN_GAME 环境变量）")
    ap.add_argument("--bundle", help="set 用的官方语言包（默认 assets/lang-zh-s-official）")
    ap.add_argument("--tsv", help="set 用的 TSV（默认资产里版本号最大的那份）")
    ap.add_argument("--keep", action="store_true", help="保留临时产物")
    a = ap.parse_args()

    lt = Path(a.langtool).resolve() if a.langtool else langtool_here()
    dll = Path(a.dll).resolve() if a.dll else default_dll()
    bundle = Path(a.bundle).resolve() if a.bundle else DEF_BUNDLE
    tsv = Path(a.tsv).resolve() if a.tsv else latest_tsv()
    deps = resolve_deps(a.deps)

    print("[i] 平台 %s %s / Python %s" % (platform.system(), platform.machine(), platform.python_version()))
    missing = [str(p) for p in (lt, dll, bundle, tsv) if p is None or not Path(p).is_file()]
    if deps is None or not Path(deps).is_dir():
        missing.append("--deps（Unity 程序集目录）")
    if missing:
        for m in missing:
            print("[!] 找不到 %s" % m)
        if deps is None:
            print("    （用 --deps 指定 <游戏>/Data/Managed，或用 OBRADINN_GAME 指定游戏根目录；\n"
                  "     mac 上先装好游戏就会自动找到）")
        return 2
    assert lt and dll and bundle and tsv and deps
    if sys.platform != "win32":
        os.chmod(lt, 0o755)              # 从 zip/git 里出来的可能丢了可执行位
    print("[i] langtool %s  %.2f MB  sha=%s…" % (lt.name, lt.stat().st_size / 1048576, sha(lt)[:16]))
    print("[i] deps     %s" % deps)

    # patchwrap 的输入得是没打过 wrap 的；已经是 wrap 状态就先说一声
    rc_in, _ = run([str(lt), "patchwrap", str(dll), "--check"])
    if rc_in == 0:
        print("[!] 注意：输入 DLL 已是 wrap 状态（--check 返回 0）—— 参考值可能不适用，换一份纯原版的")

    work = Path(tempfile.mkdtemp(prefix="lt-selftest-"))
    try:
        got = measure(lt, dll, bundle, tsv, work, deps)
        inputs = {"dll": info(dll), "bundle": info(bundle), "tsv": info(tsv)}

        if a.record:
            ref = {
                "note": "langtool 跨平台等价参考值 —— 由某一平台的 langtool 实测录得；"
                        "另一个平台跑同样命令必须得到相同的 sha（见 tools/selftest_langtool.py）",
                "recorded_by": {"platform": platform.system(), "machine": platform.machine(),
                                "langtool": lt.name, "langtool_sha": sha(lt)},
                "inputs": inputs,
                "expect": {k: {kk: vv for kk, vv in v.items() if kk != "out"} for k, v in got.items()},
            }
            bad = [k for k, v in ref["expect"].items() if "sha" not in v]
            if bad:
                print("[!] %s 没成功，不能录参考值" % ", ".join(bad))
                return 1
            LT_DIR.mkdir(parents=True, exist_ok=True)
            if REF.is_file():                       # 留个备份，免得录坏了没法回退
                shutil.copy2(REF, REF.with_suffix(".json.bak"))
            REF.write_text(json.dumps(ref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("[+] 已写入 %s" % REF.relative_to(ROOT))
            print("    另一平台执行本脚本（不带 --record）即可验等价性")
            return 0

        # ---- 自检模式 ----
        if not REF.is_file():
            print("[!] 没有 %s —— 先在 Windows 上跑 --record" % REF.relative_to(ROOT))
            return 2
        ref = json.loads(REF.read_text(encoding="utf-8"))
        print("[i] 参考值录于 %s %s（langtool %s sha=%s…）"
              % (ref["recorded_by"]["platform"], ref["recorded_by"].get("machine", "?"),
                 ref["recorded_by"]["langtool"], ref["recorded_by"]["langtool_sha"][:16]))

        stale = [k for k in ref["inputs"]
                 if ref["inputs"][k]["sha"] != inputs[k]["sha"]]
        if stale:
            for k in stale:
                print("[!] 输入 %s 与参考值不符：" % k)
                print("      参考 %s  %s" % (ref["inputs"][k]["sha"][:16] + "…", ref["inputs"][k]["path"]))
                print("      现在 %s  %s" % (inputs[k]["sha"][:16] + "…", inputs[k]["path"]))
            print("[!] 参考值过期（不是 mac 版的问题）→ 在 Windows 上重跑 --record")
            return 2

        ok = True
        for key in ("patchwrap", "set"):
            exp = ref["expect"].get(key, {})
            cur = got.get(key, {})
            if "sha" not in cur:
                print("[✗] %s 在本机没跑成" % key)
                ok = False
                continue
            same = (cur["sha"] == exp.get("sha")) and (cur["size"] == exp.get("size"))
            print("%s %-9s 本机 %s  %d B   %s"
                  % ("[✓]" if same else "[✗]", key, cur["sha"][:16] + "…", cur["size"],
                     "与参考值逐字节一致" if same else
                     "≠ 参考 %s %d B" % (exp.get("sha", "?")[:16] + "…", exp.get("size", -1))))
            ok &= same

        # 顺手验幂等标记：打过 wrap 的 DLL 再 --check 应返回 0
        wrapped = work / "wrapped.dll"
        if wrapped.is_file():
            rc, _ = run([str(lt), "patchwrap", str(wrapped), "--check"])
            print("%s --check 已打好的 DLL 返回 %d（0=已打）" % ("[✓]" if rc == 0 else "[✗]", rc))
            ok &= (rc == 0)

        print("\n%s" % ("[=] PASS —— 本机 langtool 与参考平台产出逐字节一致"
                        if ok else
                        "[!] FAIL —— 见上；把本脚本输出发我，临时产物：%s" % work))
        return 0 if ok else 1
    finally:
        if a.keep:
            print("[i] 临时目录保留：%s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
