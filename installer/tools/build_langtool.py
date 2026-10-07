# -*- coding: utf-8 -*-
"""构建随包的 langtool（安装器用它做 DLL wrap 与语言包重建）。

    python CN_Refined\\installer\\tools\\build_langtool.py                # 三个平台都发（默认）
    python CN_Refined\\installer\\tools\\build_langtool.py --rid win-x64  # 只发一个

产物（都放在 assets/langtool/）：
    langtool.exe            Windows（引擎优先找它）
    langtool-macos-arm64    macOS Apple Silicon（M 系）
    langtool-macos-x64      macOS Intel
  ★ 打包时按当前平台把对应那份拷成 **无扩展名的 `langtool`**（引擎第二个候选就是它），
    所以 mac 包里不会白背 10 MB 的 Windows 版。

★ 为什么要裁剪（别改回去）：
  之前用的是**不裁剪**的 self-contained single-file 发布 → 65.36 MB，因为那等于把
  一整个 .NET 8 运行时背进补丁里。而 langtool 自己的代码 + AssetsTools.NET +
  Mono.Cecil + classdata.tpk 合起来才 ~10 MB。「裁剪 + single-file 压缩」后：
  Windows ~10.7 MB / macOS ~11.3 MB（arm64）~12.0 MB（x64），实测 Windows 版
  产出与原版**逐字节一致**。

  ★ 跨平台等价性：Windows 上只能**发布** macOS 版（跨架构发布是支持的），跑不了 ——
    所以 mac 版的等价性靠 `tools/selftest_langtool.py`：它把 language tool 的两条关键
    命令（patchwrap / set）在仓库内固定输入上跑一遍，与 Windows 录下的参考 sha 对比
    （参考值在 assets/langtool/reference.json，不是写死在本文件里的，避免过期）。

  边界：只保证安装器用到的命令（`patchwrap` / `patchwrap --check` / `set`）；
        裁剪会砍反射，`api` 那类命令可能不全 —— 安装器不用它。
        ⚠ 这个二进制是**快照**：改了 hardcore/langtool 源码就要重跑本脚本，
          并重录一次参考值（selftest_langtool.py --record）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
CSPROJ = ROOT / "hardcore" / "langtool" / "LangTool.csproj"
OUT = PKG / "out" / "langtool"
DEST = PKG / "assets" / "langtool"

# RID -> 放进 assets 的文件名（Windows 那份叫 .exe，引擎优先找它；mac 那份无扩展名）
TARGETS = {"win-x64": "langtool.exe",
           "osx-arm64": "langtool-macos-arm64",
           "osx-x64": "langtool-macos-x64"}

# 命令必须在列：裁剪发布曾因源码旧而漏掉 patchwrap（仓库里那个 pub-trim 就是），
# 所以发布完要验一下 exe 自己印出来的用法里有没有它。
REQUIRED_CMDS = ["patchwrap", "set", "revealhook"]

# Mach-O 魔数（64 位 LE/BE、32 位 LE/BE）—— Windows 上跑不了 mac 版，只能这样粗验
MACHO_MAGICS = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def publish(rid: str, verify: bool, compress: bool) -> Path | None:
    """发布一个平台，返回可执行文件路径；失败返回 None。

    verify=True 时才真跑一下（只有 Windows 版能在 Windows 上跑）。"""
    outdir = OUT / rid
    cmd = ["dotnet", "publish", str(CSPROJ), "-c", "Release", "-r", rid,
           "--self-contained", "true",            # 用户机上不该要求装 .NET
           "-p:PublishSingleFile=true",           # 一个文件就够
           "-p:PublishTrimmed=true",              # ★ 砍掉用不到的运行时（65 MB → ~11 MB）
           "-p:IncludeAllContentForSelfExtract=true",   # 否则 classdata.tpk 会漏在 exe 外面
           "-p:DebugType=none",
           "-o", str(outdir)]
    if compress:
        cmd.insert(-2, "-p:EnableCompressionInSingleFile=true")   # 再压一道（启动时解压一次）
    print("[*] dotnet publish %s …（trim 会有反射告警，属预期，api 命令才用得到反射）" % rid)
    r = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        print("[!] %s 发布失败（退出码 %d）" % (rid, r.returncode))
        return None

    exe = outdir / "langtool.exe"          # Windows 产物
    if not exe.is_file():
        exe = outdir / "langtool"          # macOS 产物（无扩展名）
    if not exe.is_file():
        print("[!] %s 没产出可执行文件（看 %s）" % (rid, outdir))
        return None

    if verify:
        # 命令齐不齐（防「源码旧了 / 发布缓存」这类坑）
        # 用法是打**到 stderr** 的（退出码 2），所以两个流都要接
        hp = subprocess.run([str(exe)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        help_out = (hp.stdout or "") + (hp.stderr or "")
        missing = [c for c in REQUIRED_CMDS if c not in help_out]
        if missing:
            print("[!] %s 的用法里没有 %s —— 源码或发布缓存不对" % (rid, ", ".join(missing)))
            return None
        print("[+] %s 命令齐：%s" % (rid, ", ".join(REQUIRED_CMDS)))
    else:
        kind = "Mach-O" if exe.read_bytes()[:4] in MACHO_MAGICS else "?（不是预期的 Mach-O）"
        print("[i] %s 是 %s（跨平台发布只能这么粗验，等价性需在 Mac 上跑 selftest_langtool.py）" % (rid, kind))
    return exe


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # type: ignore[union-attr]
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", choices=sorted(TARGETS), help="只发布这一个平台（默认三个都发）")
    ap.add_argument("--no-install", action="store_true", help="只发布到 out/langtool/，不装进 assets")
    ap.add_argument("--no-compress", action="store_true", help="不做 single-file 压缩（体积大 ~3MB，启动快）")
    a = ap.parse_args()

    if not CSPROJ.is_file():
        print("[!] 找不到 %s" % CSPROJ)
        return 2
    if shutil.which("dotnet") is None:
        print("[!] PATH 里没有 dotnet")
        return 2

    DEST.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for rid in ([a.rid] if a.rid else sorted(TARGETS)):
        name = TARGETS[rid]
        exe = publish(rid, verify=(rid == "win-x64"), compress=not a.no_compress)
        if exe is None:
            failed.append(rid)
            continue
        dst = DEST / name
        was = "（替换前 %.2f MB）" % (dst.stat().st_size / 1048576) if dst.is_file() else "（新增）"
        print("[+] %s  %.2f MB  %s" % (rid, exe.stat().st_size / 1048576, was))
        if not a.no_install:
            shutil.copy2(exe, dst)
            print("    已装入 %s" % dst.relative_to(ROOT))
    if failed:
        print("[!] 这些没成功：%s" % ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
