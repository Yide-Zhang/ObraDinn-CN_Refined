# -*- coding: utf-8 -*-
"""把安装向导打包成可发布的程序（PyInstaller）。

    Windows：默认**单文件**（用户要的是「一个 exe」）
    python CN_Refined\\installer\\tools\\build_release.py             # 单文件（就一个 exe）
    python CN_Refined\\installer\\tools\\build_release.py --onedir    # 目录版（启动快、不写 tmp）
    python CN_Refined\\installer\\tools\\build_release.py --console   # 调试用：带上黑窗看报错

    macOS：默认**目录版 → .app 包**（双击即用、瞬间启动、Dock 里有自己的图标）
    python3 CN_Refined/installer/tools/build_release.py               # 出 ObraDinnCN-Installer.app + zip
    python3 CN_Refined/installer/tools/build_release.py --dmg         # 另外再出个 .dmg

产物：
    单文件：CN_Refined/out/release/ObraDinnCN-Installer.exe   ← 就这一个文件，双击即用
    目录版：CN_Refined/out/release/ObraDinnCN-Installer/      ← exe + runtime/（拷走要拷整个文件夹）
    macOS： CN_Refined/out/release/ObraDinnCN-Installer.app   ← 双击即用（另出 _macOS.zip）

macOS 的五个不同（都是平台硬约束，不是偏好）：
  1. **图标不能用 .ico**，要用 .icns → `icon-CNRefined.png` 会另生成一份多尺寸 .icns
     （用纯 Python 写容器，不依赖 macOS 的 iconutil，所以本脚本在 Windows 上也能预生成）。
  2. **没有 `--version-file`**（那是 Windows PE 资源），改用 Info.plist 的
     CFBundleShortVersionString/CFBundleVersion —— 由这里的 mac_finish() 写。
  3. **没有 `--splash`**（PyInstaller 的启动画面不支持 macOS）。也不需要：
     .app 是目录版，不从 tmp 解压，启动本来就是瞬间的。
  4. **必须 ad-hoc 重签名**：改过 Info.plist 后原有签名就废了，而 Apple Silicon 上
     未签名的二进制会被系统直接杀掉（连报错都来不及）。所以 mac_finish() 里
     `codesign --force --deep --sign -`。
  5. **压缩包必须用 ditto**（`ditto -c -k --keepParent`）：.app 里有一堆相对 symlink，
     普通 zip 会把它们变成实体文件或丢失权限，解开后跑不起来。

  ⚠ 分发与 Gatekeeper：没买开发者证书、做不了公证（notarization），所以用户从网上下来的
     zip 解压后会提示「无法验证开发者」。告诉用户：**右键 → 打开**（或系统设置里允许）。
     这是未公证应用的必然，不是包做错了。

打包时的资源裁剪（两个平台共用）：只把**当前平台**的 langtool 放进包里
     （assets/langtool/ 下三个二进制共 34 MB，不裁就是白背 23 MB），
     macOS 上还会把它改名成无扩展名的 `langtool` 并补上可执行权限
     （engine.langtool() 的第二个候选就是它）。

Windows 单文件的两个固有代价 —— 用户选了单文件（对小白来说"一个 exe"更像个普通软件），
所以两个都上了药：
  1. 每次启动要把 ~40 MB 解到 %TEMP%\\_MEIxxxx → 界面约 8.6 秒后才出来。
     这 8.6 秒屏幕上本来什么都没有（小白会以为没双击上、再双击一次），
     所以默认带 **`--splash` 启动画面**：bootloader 在解压**之前**就把它画出来，
     服务起来后再由 `server.py` 里的 `pyi_splash.close()` 收掉。
     （`--no-splash` 可关。）
  2. 这种 exe 容易被杀软启发式盯上、右键「属性 → 详细信息」里还空空如也 →
     已补 `assets/version_info.txt`（产品名/版本/描述），看着像个正经软件。

打进包里的东西：
    assets/      字体子集 A、官方语言包、20 个 TSV、贴图、预生成 shs6、langtool.exe、
                 窗口图标（icon.png）、启动画面（splash.png）、版本信息
    data/        难度表（difficulty.json）、已知哈希（known-hashes.json）
    gui/fonts/   界面字体（子集 B：IMFe + 思源 Heavy + 思源 SemiBold）
不进包：installer/out/（测试沙盒、报告）、开发树上的 ../ 回退路径（font_src 等）。

两个容易漏的点（都在这脚本里处理了）：
  1. engine.step_fonts 里是 `importlib.import_module("make_subset_fonts")` ——
     动态导入，PyInstaller 静态分析看不到 → 必须 --paths + --hidden-import 手动带上。
  2. 界面正文的中文字体，CSS 请求的名字是 `SourceHanSerifSC-SemiBold-subset.otf`，
     开发期是靠 FONT_DIRS 里的 `../font_src` 兜住的 —— 打包后那条路不存在，
     所以这里先把字体收进 gui/fonts（改名成 CSS 要的那个名字）。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import plistlib
import shutil
import struct
import subprocess
import sys
from io import BytesIO
from pathlib import Path

IS_MAC = sys.platform == "darwin"

HERE = Path(__file__).resolve().parent            # installer/tools/
PKG = HERE.parent                                 # installer/
ROOT = PKG.parents[1]                             # 仓库根
OUT = PKG / "out"
RELEASE = OUT / "release"
ENTRY = PKG / "run_gui.py"
APP = "ObraDinnCN-Installer"

# ---- 版本 / 包标识（Windows 在 assets/version_info.txt，macOS 在 Info.plist）----
APP_VERSION = "1.0.0"                             # ★ 跟 version_info.txt 里的 filevers 保持一致
BUNDLE_ID = "com.obradinn.cnrefined"              # 没买证书，这个 id 只是让系统能区分身份

# ---- 图标：icon-CNRefined.png → .ico（Windows）/ .icns（macOS）----
# ★ .ico 必须含 16×16 —— 资源管理器「小图标」视图只认那一档，缺了就回落成默认图标（踩过一次）
ICON_PNG = ROOT / "icon-CNRefined.png"
ICON_ICO = ROOT / "icon-CNRefined.ico"
ICON_ICNS = ROOT / "icon-CNRefined.icns"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# ICNS 的 PNG 型条目码（16/32/64 用 icp4/5/6，128 起用 ic07…ic10）
ICNS_TYPES = ((16, b"icp4"), (32, b"icp5"), (64, b"icp6"), (128, b"ic07"),
              (256, b"ic08"), (512, b"ic09"), (1024, b"ic10"))

# 随包的 langtool：按平台只留一份（assets/langtool/ 三个共 34 MB）
LT_DIR = PKG / "assets" / "langtool"
WIN_LT = "langtool.exe"


def mac_lt_name() -> str:
    """本机 mac 该用哪份 langtool（与 tools/build_langtool.py 的 TARGETS 对应）"""
    m = platform.machine().lower()
    return "langtool-macos-arm64" if m in ("arm64", "aarch64") else "langtool-macos-x64"

SPLASH_PNG = PKG / "assets" / "splash.png"          # tools/make_splash.py 生成
VERSION_FILE = PKG / "assets" / "version_info.txt"  # 右键属性里显示的产品名/版本

# 装了才 --collect-all（没装的话 PyInstaller 会对每个模块各报一条 warning，看着像出错）
# ★ fmod_toolkit 必须在列：真装时 step_langpack 会用 UnityPy 遍历语言包对象，
#   其中某类对象会连带 import UnityPy.export.AudioClipConverter → 它在模块级
#   `import fmod_toolkit`；而这个包的原生 fmod.dll（libfmod/Windows/x64/）是个
#   **二进制**，不 collect 就会在冻结环境里报 "Failed to load dynlib/dll"。
#   （demo 模式跳过这段，所以只有真装才暴露 —— 别把它从列表里去掉）
# ★ archspec 也是同理：etcpak 会在运行期 import 它来判断 CPU 特性，而它的
#   json/cpu/microarchitectures.json 是**数据文件**，不 collect 就 FileNotFoundError。
COLLECT_ALL = ["UnityPy", "fmod_toolkit", "archspec", "typetreegeneratorapi", "tpk_ar",
               "texture2ddecoder", "etcpak", "lz4", "brotli"]
HIDDEN = ["make_subset_fonts",                       # engine 里动态导入的
          "tkinter", "tkinter.filedialog", "tkinter.messagebox"]

# ★ 必须排掉。这台机器全局 Python 里 fontTools / etcpak 的**可选依赖**（lxml、matplotlib、
#   scipy、imagehash…）会把一大串跟本向导无关的重家伙拖进依赖图，而且 PyQt5 与 PyQt6
#   同时被收集时 PyInstaller 会直接中止构建（"multiple Qt bindings"）。
EXCLUDES = [
    "PyQt5", "PyQt6", "PySide2", "PySide6", "shiboken2", "shiboken6", "qtpy",
    # ★ fsspec（UnityPy 依赖）那条链会把下面这些整套拖进来，实测占了 110 MB 以上 ——
    #   逐条实测不需要（真装全流程能过），列在这是为了让发布件别肿一倍。
    "pyarrow", "numpy", "pandas", "cryptography", "Crypto", "nacl",
    "matplotlib", "scipy", "sympy", "imagehash", "pywt", "skimage", "sklearn",
    "networkx", "torch", "torchvision", "IPython", "jupyter", "notebook",
    "nbformat", "nbconvert", "jedi", "parso", "zmq", "tornado", "lxml", "fs",
    "zopfli", "pycairo", "cairo", "skia", "uharfbuzz", "brotlicffi", "olefile",
    "defusedxml", "markdown2", "coverage", "pytest", "sphinx", "docutils",
]
DS = os.pathsep                                   # add-data 的分隔符（Windows 上是 ;）


def icon() -> Path | None:
    """icon-CNRefined.png → 多尺寸 .ico（已经不比 png 旧就复用）"""
    if ICON_ICO.is_file() and (not ICON_PNG.is_file()
                               or ICON_ICO.stat().st_mtime >= ICON_PNG.stat().st_mtime):
        return ICON_ICO
    if not ICON_PNG.is_file():
        print("[!] 没有 %s，exe 用默认图标" % ICON_PNG.name)
        return None
    try:
        from PIL import Image                          # noqa: PLC0415
    except ImportError:
        print("[!] 没装 Pillow，生成不了 .ico，exe 用默认图标")
        return None
    img = Image.open(ICON_PNG).convert("RGBA")
    if max(img.size) < ICO_SIZES[-1]:                  # 源图不到 256 就先补到 256，
        img = img.resize(                            # 否则 256 那档会直接缺掉
            (ICO_SIZES[-1], ICO_SIZES[-1]), Image.LANCZOS)
    img.save(ICON_ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print("[+] 生成图标 %s  %s" % (ICON_ICO.name, ICO_SIZES))
    return ICON_ICO


def icon_icns() -> Path | None:
    """icon-CNRefined.png → 多尺寸 .icns（macOS 用）

    ★ 自己写 ICNS 容器（=「icns」+ 长度 + 一串 [类型码, 长度, PNG]），不用 macOS 的
      iconutil 也不依赖 Pillow 的 icns 写出支持（它只写单个条目，小尺寸档会缺）——
      这样在 Windows 上也能把图标预生成好，且能当场用 Pillow 回读校验。

    ★ 源图小于 1024 时大尺寸档是放大出来的（会略微发虚）：只有 Dock/访达放大预览
      才用得到，代价可接受；128 及以下都是**缩小**，那才是真正天天看到的样子。
    """
    if ICON_ICNS.is_file() and (not ICON_PNG.is_file()
                                or ICON_ICNS.stat().st_mtime >= ICON_PNG.stat().st_mtime):
        return ICON_ICNS
    if not ICON_PNG.is_file():
        print("[!] 没有 %s，app 用默认图标" % ICON_PNG.name)
        return None
    try:
        from PIL import Image                          # noqa: PLC0415
    except ImportError:
        print("[!] 没装 Pillow，生成不了 .icns，app 用默认图标")
        return None
    img = Image.open(ICON_PNG).convert("RGBA")
    body = b""
    for size, code in ICNS_TYPES:
        buf = BytesIO()
        src = img if img.size == (size, size) else img.resize((size, size), Image.LANCZOS)
        src.save(buf, format="PNG")
        png = buf.getvalue()
        body += code + struct.pack(">I", len(png) + 8) + png
    ICON_ICNS.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    print("[+] 生成图标 %s  %s" % (ICON_ICNS.name, tuple(s for s, _ in ICNS_TYPES)))
    return ICON_ICNS


def icon_for_platform() -> Path | None:
    return icon_icns() if IS_MAC else icon()


def _link_or_copy(src: str, dst: str, *, follow_symlinks: bool = True) -> str:
    """copytree 的 copy_function：优先**硬链接**（同盘瞬间完成、不额外占盘），失败就真拷"""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    return dst


def stage_assets(work: Path) -> Path | None:
    """把 assets/ 收进临时目录，并且**只留当前平台的 langtool**。拿不到必需的
    langtool 就返回 None（它缺了装不了东西，不能默默打出个残包）。

    assets/ 一共 47 MB，其中 langtool 三个平台的二进制就占 34 MB —— 把另外两个平台的
    塞进发布包里纯属白背（Windows 用户不需要 mac 的 Mach-O，反之亦然）。
    macOS 上还会把本平台那份**改名成无扩展名的 `langtool`** 并补上可执行位
    （engine.langtool() 先找 langtool.exe、再找 langtool）。
    """
    stage = work / "stage-assets" / "assets"          # ★ 和字体那个 stage 分开放
    shutil.rmtree(stage.parent, ignore_errors=True)    #   （共用一个父目录时 rmtree 会把对方删掉）
    stage.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PKG / "assets", stage, copy_function=_link_or_copy)

    lt = stage / "langtool"
    want = mac_lt_name() if IS_MAC else WIN_LT
    if not (lt / want).is_file():
        print("[!] 缺 %s —— 先跑 tools/build_langtool.py 把三个平台都发布出来" % (lt / want))
        return None
    saved = 0
    for p in sorted(lt.iterdir()):
        if p.name in ("reference.json", want):
            continue                                      # 参考值不随包发
        saved += p.stat().st_size
        p.unlink()
    if IS_MAC:
        src, dst = lt / want, lt / "langtool"
        if dst.exists():
            dst.unlink()
        src.rename(dst)
        os.chmod(dst, 0o755)                              # ★ 少了这步 mac 上 Permission denied
        print("[+] assets 裁剪：%s → %s（可执行位已补）" % (want, dst.name))
    else:
        print("[+] assets 裁剪：langtool → %s" % want)
    print("    精简掉 %.1f MB（三个平台共 34 MB，只带当前平台那份）" % (saved / 1048576))
    return stage


def tree_size(p: Path) -> int:
    """目录的**真实**体积。

    ★ 不把符号链接的目标算进去：mac 的 .app 里 `Contents/Resources` 有大量指向
      `Contents/Frameworks` 的 symlink（PIL、Python、各个 .so…），而 `Path.stat()`
      **会跟随**symlink → 同一份文件被算两遍。实测：真实 79 MB 被报成 143.8 MB（踩过）。
    """
    total = 0
    for q in p.rglob("*"):
        try:
            if q.is_symlink() or not q.is_file():
                continue
            total += q.stat().st_size
        except OSError:
            continue
    return total


def make_win_zip(exe: Path) -> Path | None:
    """把单文件 exe 压成发布用的 zip（里面就一层：那个 exe）。

    ★ 为什么要写进脚本：以前这一步是手工压的，于是出现过「exe 已经重建、zip 还是上一版」
      —— 发出去的包和验证过的产物不是同一个东西（和碎片/资源那个闸是同一类坑）。
    """
    import zipfile
    zp = RELEASE / (APP + "_Windows.zip")
    zp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe, arcname=exe.name)
    except OSError as e:
        print("[!] 压 zip 失败：%s" % e)
        return None
    print("[+] %s  %.1f MB（内含 %s）" % (zp.name, zp.stat().st_size / 1048576, exe.name))
    return zp


def mac_finish(app: Path, zip_it: bool, dmg: bool) -> list[Path]:
    """macOS 收尾：写 Info.plist → ad-hoc 重签 → 出 zip / dmg。返回额外产物列表。"""
    plist = app / "Contents" / "Info.plist"
    made: list[Path] = []
    if plist.is_file():
        try:
            d = plistlib.loads(plist.read_bytes())
            d["CFBundleName"] = APP
            d["CFBundleDisplayName"] = APP
            d["CFBundleIdentifier"] = BUNDLE_ID
            d["CFBundleShortVersionString"] = APP_VERSION   # Windows 那边是 version_info.txt
            d["CFBundleVersion"] = APP_VERSION
            d["LSMinimumSystemVersion"] = "10.15"           # PyInstaller 的 mac 最低就是 10.15
            d["NSHighResolutionCapable"] = True             # 否则界面是模糊的放大版
            # ★ 图标名必须等于**包里实际存在的那个文件名**：PyInstaller 是用源文件名把图标
            #   放进 Contents/Resources 的（实测是 icon-CNRefined.icns），而它自己写进 plist 的
            #   名字又是另一套 → 对不上就变成通用图标（踩过：app 没有图标）。
            res = app / "Contents" / "Resources"
            icons = sorted(res.glob("*.icns")) if res.is_dir() else []
            if icons:
                d["CFBundleIconFile"] = icons[0].name
            else:
                print("[!] Contents/Resources 里没有 .icns —— 访达会显示通用图标")
                d.pop("CFBundleIconFile", None)
            plist.write_bytes(plistlib.dumps(d))
            print("[+] Info.plist：%s %s（%s）图标=%s"
                  % (APP, APP_VERSION, BUNDLE_ID, d.get("CFBundleIconFile", "（无）")))
        except Exception as e:                                # noqa: BLE001
            print("[!] 改 Info.plist 失败（不影响能不能跑）：%s" % e)

    # ★ 改过 plist 之后原签名必失效；Apple Silicon 上未签名（或签名失效）的二进制
    #   会被内核直接杀掉，所以必须 ad-hoc（`-`）重签一次。
    subprocess.run(["xattr", "-cr", str(app)], check=False)
    r = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print("[+] 已 ad-hoc 重签名（未公证，用户首次打开需右键 → 打开）")
    else:
        print("[!] codesign 失败（可能这台上没有 Xcode 命令行工具）：%s"
              % ((r.stderr or r.stdout or "").strip()[:300]))

    v = subprocess.run(["codesign", "-dv", str(app)], capture_output=True, text=True)
    print("[i] 签名自检：" + ((v.stderr or v.stdout or "").strip().splitlines() or ["?"])[0][:160])

    if zip_it:
        # ★ 必须 ditto：.app 里有相对 symlink，普通 zip（含 Python zipfile）会把它们
        #   变成实体文件/丢权限，解压后就跑不起来了。
        zp = RELEASE / (APP + "_macOS.zip")
        zp.unlink(missing_ok=True)
        r = subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                            str(app), str(zp)], capture_output=True, text=True)
        if r.returncode == 0 and zp.is_file():
            made.append(zp)
            print("[+] %s  %.1f MB（ditto，symlink/权限都保住了）" % (zp.name, zp.stat().st_size / 1048576))
        else:
            print("[!] ditto 打包失败：%s" % ((r.stderr or "").strip()[:200]))
    if dmg:
        dp = RELEASE / (APP + "_macOS.dmg")
        dp.unlink(missing_ok=True)
        r = subprocess.run(["hdiutil", "create", "-volname", APP, "-srcfolder", str(app),
                            "-ov", "-format", "UDZO", str(dp)], capture_output=True, text=True)
        if r.returncode == 0 and dp.is_file():
            made.append(dp)
            print("[+] %s  %.1f MB" % (dp.name, dp.stat().st_size / 1048576))
        else:
            print("[!] hdiutil 做 dmg 失败：%s" % ((r.stderr or "").strip()[:200]))
    return made


def stage_fonts(work: Path) -> Path:
    """把界面字体收进临时目录：gui/fonts/* + 正文用的思源 SemiBold（改成 CSS 要的名字）

    ★ 目录名跟 stage_assets 分开（work/stage-fonts vs work/stage-assets）—— 两边都有
      〘先清空父目录〙的动作，共用父目录时后跑的会把先跑的整个删掉。
    """
    stage = work / "stage-fonts"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    src = PKG / "gui" / "fonts"
    n = 0
    for p in sorted(src.glob("*")):
        if p.is_file():
            shutil.copy2(p, stage / p.name)
            n += 1
    want = stage / "SourceHanSerifSC-SemiBold-subset.otf"
    if not want.is_file():
        for cand in (ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF",
                     ROOT / "font_src" / "SourceHanSerifSC-SemiBold.otf"):
            if cand.is_file():
                shutil.copy2(cand, want)
                n += 1
                break
        else:
            print("[!] 找不到思源宋体 SemiBold（font_src\\SOURCEHANSERIFSC-SEMIBOLD.OTF）——\n"
                  "    界面正文的中文会回落到系统字体（宋体/黑体），观感会变。")
    print("[+] 界面字体 %d 个：%s" % (n, ", ".join(sorted(p.name for p in stage.glob("*")))))
    return stage


def collect_flags() -> list[str]:
    flags: list[str] = []
    for m in COLLECT_ALL:
        try:
            if importlib.util.find_spec(m) is not None:
                flags += ["--collect-all", m]
        except (ImportError, ValueError):
            pass                                   # 没装就跳过（运行期用不到）
    return flags


def check_assets() -> bool:
    lt_here = LT_DIR / (mac_lt_name() if IS_MAC else WIN_LT)   # 本平台那份 langtool
    need = [lt_here,
            PKG / "assets" / "lang-zh-s-official",
            PKG / "assets" / "sharedassets6.assets",
            PKG / "assets" / "packs" / "zh-s-v5-unharm-bi.tsv",
            PKG / "data" / "known-hashes.json",
            PKG / "data" / "difficulty.json"]
    miss = [str(p.relative_to(ROOT)) for p in need if not p.exists()]
    if miss:
        print("[!] 随包资源不全，先跑 tools/make_package.py（缺 langtool 另跑 tools/build_langtool.py）：")
        for m in miss:
            print("      " + m)
        return False
    if not lt_here.is_file():
        print("[!] 本平台（%s）的 langtool 还没发布，跑 tools/build_langtool.py"
              % ("macOS " + mac_lt_name() if IS_MAC else "Windows"))
        return False
    return True


def _sha(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_freshness() -> list[str]:
    """★ 打“输入比产物新/没同步”的闸 —— 踩过的坑：碎片还没更新完就打包，发出去的贴图是旧的

    两条链，各自的比法不一样：
      · 碎片 → 成品：碎片文件有比成品（out/textures）新的 → 先跑 paste_fragments.py
      · 成品/语言包 → 随包：**按内容比 sha**（别看时间！make_package 用 copy2 会保留源文件时间，
        看时间会误判成“没同步”）→ 不一致就跑 make_package.py
      · 人名表 → 语言包：表比 out/packs 新 → 先跑 build_pack.py --all
    """
    CR = PKG.parent                                   # CN_Refined/
    frag = CR / "Textures" / "fragments"
    composed = CR / "out" / "textures"
    assets_tex = PKG / "assets" / "textures"
    out_packs = CR / "out" / "packs"
    assets_packs = PKG / "assets" / "packs"
    bad: list[str] = []

    # ① 碎片 → 成品
    if frag.is_dir() and composed.is_dir():
        newest = max((p.stat().st_mtime for p in frag.rglob("*") if p.is_file()), default=0)
        stale = sorted(p.name for p in composed.glob("*.png") if p.stat().st_mtime < newest)
        if stale:
            bad.append("碎片比成品图新（%d 张，如 %s）\n"
                       "      → python CN_Refined\\langpack\\paste_fragments.py"
                       % (len(stale), ", ".join(stale[:3])))

    # ①b 人名表 → 语言包
    tbl = CR / "langpack" / "extracted" / "crew_name_variants.tsv"
    newest_pack = max((p.stat().st_mtime for p in out_packs.glob("*.tsv")), default=0)
    if tbl.is_file() and newest_pack and newest_pack < tbl.stat().st_mtime:
        bad.append("语言包比人名表旧\n"
                   "      → fill_v4 → fill_v45 → fill_v5 → check_table → build_pack.py --all")

    # ② 成品/语言包 → 随包（按内容）
    #    ⚠ 包这里只比正式的那 20 个（zh-s-v*.tsv）—— out/packs 里还有 REVIEW-mono.tsv
    #      之类的复核草稿，make_package 本来就不拷，比它会误报
    for src_dir, dst_dir, pat, what, fix in (
            (composed, assets_tex, "*.png", "贴图", "make_package.py"),
            (out_packs, assets_packs, "zh-s-v*.tsv", "语言包", "make_package.py")):
        if not src_dir.is_dir() or not dst_dir.is_dir():
            continue
        diff = [p.name for p in sorted(src_dir.glob(pat))
                if not (dst_dir / p.name).is_file() or _sha(p) != _sha(dst_dir / p.name)]
        if diff:
            bad.append("随包的%s与成品不一致（%d 个，如 %s）\n"
                       "      → python CN_Refined\\installer\\tools\\%s"
                       % (what, len(diff), ", ".join(diff[:3]), fix))
    return bad


def main() -> int:
    try:                                              # 控制台是 GBK，输出全按 utf-8 来
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
    except Exception:                                 # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--onedir", action="store_true",
                    help="打成目录（启动快、不写 tmp，但是一堆文件）；macOS 恒为此模式")
    ap.add_argument("--no-splash", action="store_true", help="不要启动画面（仅 Windows 单文件）")
    ap.add_argument("--console", action="store_true", help="保留黑窗（调试用，能看报错）")
    ap.add_argument("--no-icon", action="store_true", help="不设图标")
    ap.add_argument("--no-zip", action="store_true", help="macOS：不打 _macOS.zip")
    ap.add_argument("--dmg", action="store_true", help="macOS：另外再做一个 .dmg")
    ap.add_argument("--keep-work", action="store_true", help="保留 build 中间产物（PyInstaller 缓存）")
    ap.add_argument("--stale-ok", action="store_true",
                    help="明知输入比产物旧也照打（默认会拦下来）")
    a = ap.parse_args()

    onedir = a.onedir or IS_MAC          # macOS 恒走目录版：--windowed 会顺带产出 .app

    if not ENTRY.is_file():
        print("[!] 找不到入口 %s" % ENTRY)
        return 2
    if not check_assets():
        return 2
    stale = check_freshness()
    if stale and not a.stale_ok:
        print("[X] 随包资源比上游产物旧，先补上再打包（明知如此要强打：--stale-ok）：")
        for s in stale:
            print("    · " + s)
        return 3
    for s in stale:
        print("[!] （--stale-ok）忽略：“%s”" % s.splitlines()[0])

    work = OUT / "build" / ("onedir" if onedir else "onefile")
    ico = None if a.no_icon else icon_for_platform()
    # ★ macOS：传给它一个**改名成 icon.icns** 的副本 —— PyInstaller 把图标放进
    #   Contents/Resources 时用的是源文件名，而 plist 里的 CFBundleIconFile 只认它自己那套
    #   命名，两边对不上访达就显示通用图标（踩过）。mac_finish 里还会再校正一次。
    if IS_MAC and ico is not None:
        work.mkdir(parents=True, exist_ok=True)
        ico_named = work / "icon.icns"
        shutil.copy2(ico, ico_named)
        ico = ico_named
    if IS_MAC and not a.onedir:
        print("[i] macOS 不用单文件：.app 本身是目录，启动瞬间完成、也不写 %%TEMP%%")
    stage_f = stage_fonts(work)
    stage_a = stage_assets(work)         # ★ 只带当前平台的 langtool
    if stage_a is None:
        return 2

    # 上次的产物先清掉（程序还在跑的话删不掉，这里不硬报错）
    old = [RELEASE / APP, RELEASE / (APP + ".exe"), RELEASE / (APP + ".app"),
           RELEASE / (APP + "_macOS.zip"), RELEASE / (APP + "_macOS.dmg")]
    for s in old:
        if not s.exists():
            continue
        try:
            shutil.rmtree(s) if s.is_dir() else s.unlink()
        except OSError as e:
            print("[!] 清不掉上次的 %s（向导是不是还开着？）：%s" % (s.name, e))
            return 2

    cmd = [sys.executable, "-m", "PyInstaller",
           "--noconfirm", "--clean",
           "--name", APP,
           "--distpath", str(RELEASE), "--workpath", str(work), "--specpath", str(work),
           # 三个 sys.path 位置：installer（engine）、gui（wizard/progress/theme）、
           # CN_Refined/assets（make_subset_fonts，engine 里是动态导入）
           "--paths", str(PKG),
           "--paths", str(PKG / "gui"),
           "--paths", str(PKG.parent / "assets")]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    for x in EXCLUDES:
        cmd += ["--exclude-module", x]
    cmd += collect_flags()
    cmd += ["--add-data", "%s%sassets" % (stage_a, DS),
            "--add-data", "%s%sdata" % (PKG / "data", DS),
            "--add-data", "%s%sgui%sfonts" % (stage_f, DS, os.sep)]
    # macOS：不传 --contents-directory（.app 的目录布局由 PyInstaller 自己安排，
    #        Contents/Frameworks 就是它的「runtime」）
    if onedir:
        cmd += ["--onedir"]
        if not IS_MAC:
            cmd += ["--contents-directory", "runtime"]
    else:
        cmd += ["--onefile"]
    if not a.console:
        cmd += ["--windowed"]                      # 不要黑窗（run_gui.py 里已兜住 stdout=None）
    if ico:
        cmd += ["--icon", str(ico)]
    if IS_MAC:
        # .app 的 CFBundleIdentifier（没买证书，这个 id 只让系统能区分身份）
        cmd += ["--osx-bundle-identifier", BUNDLE_ID]
    # ★ 启动画面只在 Windows 单文件下有意义（macOS 不支持 splash；目录版不需要解压）
    if onedir or a.no_splash or IS_MAC:
        pass
    elif SPLASH_PNG.is_file():
        cmd += ["--splash", str(SPLASH_PNG)]
    else:
        print("[!] 没有 %s，单文件启动那几秒会是空白的（跑 tools\\make_splash.py 生成）"
              % SPLASH_PNG.name)
    if VERSION_FILE.is_file() and not IS_MAC:      # Windows PE 资源，macOS 写 Info.plist
        cmd += ["--version-file", str(VERSION_FILE)]
    cmd += [str(ENTRY)]

    print("[*] PyInstaller 开始（%s）…"
          % ("macOS .app" if IS_MAC else ("目录版" if onedir else "单文件")))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")   # 日志里的中文别乱码
    r = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", env=env)
    if r.returncode != 0:
        print("[!] 打包失败（退出码 %d）—— 上面 PyInstaller 的输出里有原因" % r.returncode)
        return r.returncode

    if not a.keep_work:
        shutil.rmtree(work, ignore_errors=True)

    # ★ PyInstaller 自己会拼一层 <distpath>/<name>（目录版）/ <name>.app（macOS windowed）
    if IS_MAC:
        app = RELEASE / (APP + ".app")
        if not app.is_dir():
            print("[!] 没产出 %s（看看 PyInstaller 的日志里 .app 部分）" % app)
            return 2
        extra = mac_finish(app, zip_it=not a.no_zip, dmg=a.dmg)
        total = tree_size(app)
        print("\n[+] 完成：%s" % app)
        print("    %.1f MB（双击即用；启动瞬间完成、不写 %%TEMP%%）" % (total / 1048576))
        for p in extra:
            print("    + %s" % p.name)
        print("    首次打开被 Gatekeeper 拦：**右键 → 打开**（未公证应用的必然）")
        print("    双击后会开一个无地址栏的 app 窗口（Dock 里是自己的图标）")
        return 0

    exe = RELEASE / (APP + ".exe") if not onedir else (RELEASE / APP / (APP + ".exe"))
    if not exe.is_file():
        print("[!] 没产出 %s" % exe)
        return 2

    print("\n[+] 完成：%s" % (exe if not onedir else RELEASE / APP))
    print("    %s  %.1f MB" % (exe.name, exe.stat().st_size / 1048576))
    if onedir:
        total = tree_size(RELEASE / APP)
        print("    整个文件夹 %.1f MB（要只发一个文件就把它压成 zip）" % (total / 1048576))
        print("    启动瞬间完成、不写 %%TEMP%%")
    else:
        print("    单文件：拷走这一个 exe 就行；启动会先解到 %%TEMP%%（此时会显示启动画面），"
              "界面约 8~9 秒后出来")
        if not a.no_zip:
            make_win_zip(exe)          # 发布给用户的就是这个 zip
    print("    双击即用（会开一个无地址栏的 app 窗口）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
