# -*- coding: utf-8 -*-
"""把界面开成一个**独立的 app 窗口**（不是普通浏览器标签页）。

做法与仓库里另外两个工具一致（存档工具 `gui/server.py`、难度补丁器 `patcher/server.py`）：
找 Chromium 系的浏览器（Edge / Chrome / Brave / Vivaldi），用 `--app=<url>` 开一个
**没有地址栏、没有标签栏**的窗口；找不到就退到默认浏览器的普通标签页。

关键细节（都是踩出来的）：
  · `--user-data-dir=<自己的 profile>` —— 不碰用户的浏览器会话与首选项，也不会弹
    "首次运行"设置向导；而且因为是**新进程**，`--start-maximized` / `--window-size`
    才会被真正遵守（浏览器已有实例时，这些启动期标志会被直接丢掉 —— 存档工具那边
    为此还得事后 FindWindow+ShowWindow 补一刀）。
  · 窗口标题 = 页面的 `<title>`；窗口/任务栏图标 = 页面的 `<link rel="icon">`（favicon）。
    两个页面都引了 `/icon.png`，所以任务栏里看起来就是个独立程序。
  · **app 窗口关掉 ≠ 程序退出**（后端服务还在跑，浏览器拦不住）。所以再启动时靠
    `server._is_ours()` 探测到实例还在 → 只把窗口叫回来，不再起第二个服务。
  · 打完包没有控制台，这里的 print 只进日志，失败一律静默降级到普通标签页。

macOS（与存档工具同一套做法）：
  · Chromium 系在 macOS 上不是 PATH 里的命令，而是 .app 包里的可执行文件，
    路径形如 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`；
    所以 `--app=` 能用的浏览器靠扫这些固定位置找。
  · profile 放 `~/Library/Application Support/ObraDinnCN-Installer/browser-profile`。
  · 窗口尺寸用 CoreGraphics 的 CGDisplayBounds 取主屏像素（**不需要任何权限**，
    比问 Finder 少一次「自动化」授权弹窗）；拿到就按屏幕大小 + `--window-position` 开。
  · ⚠ 故意**不用** AppleScript 事后撑窗口（存档工具那边用它兼容旧实例）：
    我们用的是自己的 profile，浏览器必然是**新进程**，启动期标志不会被丢，
    再调 AppleScript 只会白弹一个「想控制 Google Chrome」的授权窗。
    真遇到窗口没铺满，再考虑移植存档工具的 `_maximize_mac()`（按标题/应用名撑 bounds）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

APP_DIR = "ObraDinnCN-Installer"          # %LOCALAPPDATA% 下的目录名（profile 放这）

# 能用 `--app=<url>` 开无地址栏窗口的浏览器（Chromium 系都支持）
CHROMIUM_EXES = ("chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe",
                 "chromium.exe", "google-chrome", "chromium",
                 "chromium-browser", "microsoft-edge")

# macOS：.app 包名 -> 包内可执行文件名
MAC_APPS = (("Google Chrome", "Google Chrome"),
            ("Microsoft Edge", "Microsoft Edge"),
            ("Brave Browser", "Brave Browser"),
            ("Chromium", "Chromium"),
            ("Vivaldi", "Vivaldi"))


def _candidates() -> list[Path]:
    """已知的 Chromium 系安装位置：优先 Edge（Windows 一定有），再 Chrome 等"""
    out: list[Path] = []
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        for rel in (r"Microsoft\Edge\Application\msedge.exe",
                    r"Google\Chrome\Application\chrome.exe",
                    r"BraveSoftware\Brave-Browser\Application\brave.exe",
                    r"Vivaldi\Application\vivaldi.exe"):
            for root in (pf86, pf, local):
                if root:
                    out.append(Path(root) / rel)
    elif sys.platform == "darwin":
        # 先 /Applications，再用户自己的 ~/Applications（有些人装在这儿）
        for root in (Path("/Applications"), Path.home() / "Applications"):
            for bundle, inner in MAC_APPS:
                out.append(root / (bundle + ".app") / "Contents" / "MacOS" / inner)
    else:
        import shutil
        for name in ("google-chrome", "chromium", "chromium-browser",
                     "microsoft-edge", "brave-browser"):
            w = shutil.which(name)
            if w:
                out.append(Path(w))
    return out


def screen_bounds() -> tuple[int, int, int, int] | None:
    """主屏可用区域 (x, y, w, h)；拿不到就 None。

    macOS：CoreGraphics 的 CGDisplayBounds —— 不需要任何权限。
    Windows：SPI_GETWORKAREA（已扣掉任务栏）。
    """
    if sys.platform == "darwin":
        try:
            import ctypes
            import ctypes.util

            class _Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

            class _Size(ctypes.Structure):
                _fields_ = [("w", ctypes.c_double), ("h", ctypes.c_double)]

            class _Rect(ctypes.Structure):
                _fields_ = [("origin", _Point), ("size", _Size)]

            cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
            cg.CGMainDisplayID.restype = ctypes.c_uint32
            cg.CGDisplayBounds.restype = _Rect
            cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
            r = cg.CGDisplayBounds(cg.CGMainDisplayID())
            return (int(r.origin.x), int(r.origin.y), int(r.size.w), int(r.size.h))
        except Exception:                               # noqa: BLE001
            return None
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if not ctypes.windll.user32.SystemParametersInfoW(
                    0x0030, 0, ctypes.byref(rect), 0):       # SPI_GETWORKAREA
                return None
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        except Exception:                               # noqa: BLE001
            return None
    return None


def browser_exe() -> Path | None:
    # ① 用户自己的默认浏览器要是 Chromium 系，就用它（尊重选择）
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            ) as k:
                progid = winreg.QueryValueEx(k, "ProgId")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                rf"{progid}\shell\open\command") as k:
                raw = winreg.QueryValueEx(k, "")[0].strip()
            exe = raw[1:raw.find('"', 1)] if raw.startswith('"') else raw.split(" ")[0]
            p = Path(exe)
            if p.is_file() and p.name.lower() in CHROMIUM_EXES:
                return p
        except OSError:
            pass
    # ② 已知安装位置
    for c in _candidates():
        if c.is_file():
            return c
    return None


def profile_dir() -> Path:
    r"""给 app 窗口用的独立浏览器 profile（不动用户自己的）

    Windows：%LOCALAPPDATA%\ObraDinnCN-Installer\browser-profile
    macOS：  ~/Library/Application Support/ObraDinnCN-Installer/browser-profile
    """
    if sys.platform == "darwin":
        base: Path | None = Path.home() / "Library" / "Application Support"
    else:
        env = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
        base = Path(env) if env else None
    try:
        p = (base or Path(tempfile.gettempdir())) / APP_DIR / "browser-profile"
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path(tempfile.gettempdir()) / APP_DIR / "browser-profile"
        p.mkdir(parents=True, exist_ok=True)
    return p


def _spawn_kwargs() -> dict:
    kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008          # DETACHED_PROCESS：别留个黑窗
    else:
        kw["start_new_session"] = True
    return kw


def open_window(url: str, app_mode: bool = True, size: tuple[int, int] = (1180, 900)) -> str:
    """打开界面：优先 app 窗口，失败就退到普通标签页；返回用了哪种（给日志用）"""
    if app_mode:
        exe = browser_exe()
        if exe is not None:
            geo = ["--window-size=%d,%d" % size]
            area = screen_bounds()          # 铺满主屏：拿到屏幕尺寸就直接摆到 (x,y)
            if area:
                x, y, w, h = area
                geo = ["--window-size=%d,%d" % (w, h), "--window-position=%d,%d" % (x, y)]
            args = [str(exe), "--app=" + url,
                    "--user-data-dir=" + str(profile_dir()),
                    "--no-first-run", "--no-default-browser-check",
                    "--start-maximized"] + geo
            try:
                subprocess.Popen(args, **_spawn_kwargs())
                return "app 窗口（%s）" % exe.name
            except OSError:
                pass
    try:
        return "普通标签页" if webbrowser.open(url) else "普通标签页（未确认）"
    except Exception:                             # noqa: BLE001
        return "没打开（请手动访问 %s）" % url
