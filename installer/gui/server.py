# -*- coding: utf-8 -*-
"""安装向导的本地服务：静态前端 + 很小的 JSON API，**所有实际操作都调 engine.py**。

    python -m CN_Refined.installer.gui.server      # 或直接跑 install_gui.py

为什么是本地服务 + 浏览器（而不是 tkinter/Qt）：
  · 沿用 patcher/ 那套技术栈，观感（游戏深/浅色、方角按钮）能直接对上；
  · 打补丁要几分钟，浏览器这边可以一直显示步骤与日志，比卡住的原生窗口好。

要注意的点：
  · 浏览器拿不到本地真实路径 → 目录选择框必须由**服务端**（tkinter）弹；
  · 安装/还原是长任务 → 丢到线程里跑，前端轮询 /api/progress 拿日志；
  · 同一时刻只允许一个写操作（_LOCK），防止有人连点两次「安装」。
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                                    # CN_Refined/installer/
ROOT = PKG.parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(HERE))

import engine as E                                    # noqa: E402
from wizard import INDEX_HTML                         # noqa: E402
from progress import PROGRESS_HTML                    # noqa: E402
from window import open_window                        # noqa: E402  app 窗口（--app）

DEFAULT_PORT = 8790
APP_TITLE = "《奥伯拉丁的回归》中文精修补丁 · 安装向导"

# 界面字体：优先包内（子集化 B），没有就回落到开发期的**全字体**。
# 前端 CSS 里写死的两个名字是稳定接口，这里做别名解析。
FONT_DIRS = [HERE / "fonts",                           # 开发期：未子集化的全字体（也放将来的子集 B）
             ROOT / "font_src",                        # 项目里的思源宋体源（全字体）
             PKG / "assets" / "fonts",
             ROOT / "patcher" / "assets" / "fonts"]
FONT_ALIAS = {
    "SourceHanSerifSC-SemiBold-subset.otf": ["SourceHanSerifSC-SemiBold-subset.otf",
                                              "SourceHanSerifSC-SemiBold.otf",
                                              "SOURCEHANSERIFSC-SEMIBOLD.OTF"],
    "SourceHanSerifSC-Heavy.otf": ["SourceHanSerifSC-Heavy.otf",
                                   "SOURCEHANSERIFSC-HEAVY.OTF"],
    "IMFeENrm28P.ttf": ["IMFeENrm28P.ttf"],
}

_LOCK = threading.Lock()
_ST = {"busy": False, "what": "", "kind": "", "ok": None, "log": [], "lines": 0,
       "step": 0, "total": 4}
_SRV: dict = {}                       # 给 /api/quit 用来关掉自己
_CUR: dict = {"lines": None}         # 当前任务要收集日志的那个 list（由 _hook_say 写入）

# 引擎的日志里 `[1/4] ...`、`[还原 2/5] ...` 就是进度来源
RE_STEP = re.compile(r"^\[(?:还原\s*)?(\d+)\s*/\s*(\d+)\]")


# ---------------------------------------------------------------------------
# 进度：engine 自己会 say()，我们把它接到日志队列上
# ---------------------------------------------------------------------------
def _hook_say(new_lines: list[str]) -> None:
    """把 engine 的 say() 接到日志队列上 —— ★ **只挂一次**

    早先是每跑一个任务就再包一层 `E.say`，于是同一个会话里跑第 N 个任务时，
    每一行会被记 N 次（进度页日志成倍重复，实测跑 3 次就看到 3 份）。
    现在挂钩一次、用 `_CUR["lines"]` 指向「当前任务」的 list。
    """
    _CUR["lines"] = new_lines
    if getattr(E.say, "_obradinn_hooked", False):
        return
    orig = E.say

    def say(m: str = "") -> None:                     # type: ignore[no-redef]
        orig(m)
        cur = _CUR["lines"]
        if cur is not None:
            cur.append(m)
        _ST["log"].append(m)
        _ST["lines"] = len(_ST["log"])
        mt = RE_STEP.match(m.strip())                 # [1/4] / [还原 2/5] → 进度
        if mt:
            _ST["step"] = int(mt.group(1))
            _ST["total"] = max(1, int(mt.group(2)))

    say._obradinn_hooked = True                        # type: ignore[attr-defined]
    E.say = say                                        # type: ignore[assignment]


def _run_async(kind: str, fn, total: int = 4) -> None:
    def body() -> None:
        lines: list[str] = []
        _hook_say(lines)
        try:
            ok, log = fn()
            _ST["ok"] = bool(ok)
            said = set(lines)                    # fn() 跑完再取快照，否则会重复说一遍
            for ln in log:
                if ln not in said:
                    E.say(ln)
        except Exception as ex:                          # noqa: BLE001
            E.say("✗ 内部错误: %s: %s" % (type(ex).__name__, ex))
            _ST["ok"] = False
        finally:
            _ST["busy"] = False
            _ST["what"] = ""
            _CUR["lines"] = None

    _ST.update(busy=True, what=kind, kind=kind, ok=None, log=[], lines=0, step=0,
               total=max(1, total))
    threading.Thread(target=body, daemon=True).start()


def pick_folder(initial: str | None = None) -> dict:
    """弹系统目录选择框（弹在服务所在机器上，浏览器给不了真实路径）

    ★ 平台差异（别改成一致）：
      Windows：用 tkinter（filedialog）。
      macOS：**必须**换成 osascript。Tk 在 macOS 上要求跑在**主线程**，而这里
             是 HTTP 工作线程 —— 在 mac 上这么调轻则不响应、重则直接崩；
             仓库里的存档工具（_publish/ObraDinn-SaveTool）就是为此改用 osascript 的。
    """
    if sys.platform == "darwin":
        prompt = "选择 Return of the Obra Dinn 的安装目录"
        try:
            r = subprocess.run(["osascript", "-e",
                                'POSIX path of (choose folder with prompt "%s")' % prompt],
                               capture_output=True, text=True)
        except OSError as e:
            return {"ok": False, "error": "打不开选择框（%s），请手动填写路径" % e}
        if r.returncode != 0:
            err = (r.stderr or "").strip()
            if "ancel" in err or "-128" in err:          # 用户自己取消（不是错）
                return {"ok": False, "cancelled": True}
            return {"ok": False, "error": "选择框出错（%s）" % (err[:160] or "未知")}
        chosen = (r.stdout or "").strip()
        if not chosen:
            return {"ok": False, "cancelled": True}
        g = E.game_root(Path(chosen))
        if g is None:
            return {"ok": False, "error": "这个目录里找不到游戏数据（要选到游戏根目录或 .app）"}
        return {"ok": True, "path": str(g)}

    try:
        import tkinter                                   # noqa: PLC0415
        from tkinter import filedialog                   # noqa: PLC0415
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "error": "系统目录选择框不可用（%s），请手动填写路径" % e}
    try:
        root = tkinter.Tk()
        root.withdraw()
        try:
            chosen = filedialog.askdirectory(title="选择 Return of the Obra Dinn 的安装目录",
                                             initialdir=initial or "", mustexist=True)
        finally:
            root.destroy()
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "error": "打开目录选择框失败（%s）" % e}
    if not chosen:
        return {"ok": False, "cancelled": True}
    g = E.game_root(chosen)
    if g is None:
        return {"ok": False, "error": "这个目录里找不到游戏数据（要选到游戏根目录或 .app）"}
    return {"ok": True, "path": str(g)}


# ---------------------------------------------------------------------------
# 选项（给前端渲染用；真实可用性以包内资源为准）
# ---------------------------------------------------------------------------
def resolve_font(name: str) -> Path | None:
    """把前端要的名字（或别名）解析成实际文件"""
    if Path(name).name != name:                 # 防目录穿越
        return None
    for cand in FONT_ALIAS.get(name, [name]):
        for d in FONT_DIRS:
            p = (d / cand)
            if p.is_file():
                return p
    return None


def icon_path() -> Path | None:
    """窗口 / 任务栏图标：app 模式的窗口图标取自页面的 favicon

    包内优先（build_release 会把 assets/ 整目录带上），开发时回落到仓库根那张原图。
    """
    for c in (E.ASSETS / "icon.png", HERE / "icon.png", ROOT / "icon-CNRefined.png"):
        if c.is_file():
            return c
    return None


def options() -> dict:
    tab = E.difficulty_table()
    levels = [{"level": int(l["level"]), "zh": l.get("zh", ""), "label": l.get("label", ""),
               "desc": l.get("desc", ""), "patch": bool(l.get("patch", True))}
              for l in tab.get("levels", [])]
    if not levels:
        levels = [{"level": 3, "zh": "三", "label": "原版（不改）", "desc": "按原版节奏：每次验证 3 人",
                   "patch": False}]
    vers = []
    for v in E.LEVELS:
        tsv_ok = E.langpack_tsv(v, "unharm", "bi") is not None
        vers.append({"id": v, "axis": E.NAME_AXIS[v], "tsv": tsv_ok})
    return {
        "title": APP_TITLE,
        "versions": vers,
        "levels": levels,
        "level_default": 3,                              # 默认不改难度（翻译包的本分）
        "fonts": {
            # GUI 用字体：开发阶段直接用全字体（子集化 B 以后再做）
            "serif": (resolve_font("SourceHanSerifSC-SemiBold-subset.otf") or Path()).name,
            "hand": (resolve_font("IMFeENrm28P.ttf") or Path()).name,
            "dirs": [str(d) for d in FONT_DIRS],
        },
        "preview": {
            "full": "汉堡包：被吃掉，翼德大大",            # 不缩写
            "short": "汉堡包：被吃掉，Y. 张",              # 缩写
        },
        "langtool": str(E.langtool() or ""),
        "game_auto": _auto_game(),
    }


def _auto_game() -> dict:
    g, how = E.detect_game(None)
    return {"found": bool(g), "path": str(g) if g else "", "how": how}


def state(game_str: str | None) -> dict:
    game, how = E.detect_game(game_str)
    if game is None:
        return {"ok": False, "error": how}
    rows = E.inspect_state(game)
    rec = E.Record.load(game)
    lv, lvhow = E.detect_level(game)
    lvinfo = E.difficulty_info(lv) or {}
    stash = game / E.STASH_DIR / "original"
    backups = []
    for k, v in sorted((rec.files or {}).items()):
        if k.startswith("_"):
            continue
        p = stash / Path(k)
        backups.append({"rel": k, "exists": p.is_file(),
                        "size": p.stat().st_size if p.is_file() else 0,
                        "orig_sha": str((v or {}).get("orig_sha", ""))[:16]})
    return {
        "ok": True, "game": str(game), "how": how,
        "rows": [{"rel": s.rel, "exists": s.exists, "sha": s.sha[:16],
                  "verdict": s.verdict, "detail": s.detail, "action": s.action} for s in rows],
        "has_record": bool(rec.files and not all(k.startswith("_") for k in rec.files)),
        "last": rec.options or {},
        "stash_count": len([k for k in rec.files if not k.startswith("_")]),
        "risky": [s.rel for s in rows if s.verdict in ("unknown", "other")],
        # 难度：**只读**（本补丁不改难度，只按它写文案）
        "level": lv, "level_label": lvinfo.get("label", ""),
        "level_zh": lvinfo.get("zh", ""), "level_how": lvhow,
        # 解除安装用：备份清单
        "backup_files": backups,
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "ObraDinnCNInstaller"
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt, *args) -> None:            # 静音
        pass

    def do_GET(self) -> None:                             # noqa: N802
        u = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif u.path in ("/progress", "/progress.html"):
            self._send(200, PROGRESS_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif u.path == "/api/options":
            self._json(options())
        elif u.path == "/api/state":
            self._json(state(q.get("game")))
        elif u.path == "/api/progress":
            self._json({"busy": _ST["busy"], "what": _ST["what"], "kind": _ST["kind"],
                        "ok": _ST["ok"], "log": _ST["log"], "n": _ST["lines"],
                        "step": _ST["step"], "total": _ST["total"]})
        elif u.path in ("/icon.png", "/favicon.ico"):
            self._icon()
        elif u.path.startswith("/fonts/"):
            self._font(u.path[len("/fonts/"):])
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:                            # noqa: N802
        u = urlsplit(self.path)
        req = self._read_json()
        if u.path == "/api/quit":
            self._json({"ok": True})
            threading.Thread(target=_SRV["srv"].shutdown, daemon=True).start()
            return
        if u.path == "/api/pick":
            self._json(pick_folder(req.get("initial")))
            return
        if u.path in ("/api/install", "/api/restore"):
            if not _LOCK.acquire(blocking=False):
                self._json({"ok": False, "error": "已经在忙了，等它跑完"})
                return
            try:
                if _ST["busy"]:
                    self._json({"ok": False, "error": "上一个任务还没结束"})
                    return
                game, how = E.detect_game(req.get("game"))
                if game is None:
                    self._json({"ok": False, "error": how})
                    return
                if u.path == "/api/install":
                    opt = E.Options(version=str(req.get("version") or "v5"),
                                    harmonized=bool(req.get("harmonized")),
                                    dialog=str(req.get("dialog") or "bi"),
                                    level=(int(req["level"]) if req.get("level") else None))
                    if not req.get("force"):
                        risky = [s for s in E.inspect_state(game)
                                 if s.verdict in ("unknown", "other")]
                        if risky and not req.get("confirmed"):
                            self._json({"ok": False, "need_confirm": [
                                {"rel": s.rel, "verdict": s.verdict, "detail": s.detail}
                                for s in risky]})
                            return
                    _run_async("安装", lambda: E.install(game, opt, force=True), total=4)
                else:
                    _run_async("解除安装", lambda: E.restore(game), total=5)
                self._json({"ok": True, "started": True})
            finally:
                _LOCK.release()
            return
        self._json({"ok": False, "error": "not found"}, 404)

    # ---------- 静态资源 ----------
    def _icon(self) -> None:
        """窗口/任务栏图标（app 模式的窗口图标就是页面 favicon）"""
        p = icon_path()
        if p is None:
            self._json({"ok": False, "error": "no icon"}, 404)
            return
        self._send(200, p.read_bytes(), "image/png")

    def _font(self, name: str) -> None:
        p = resolve_font(name)
        if p is None or p.suffix.lower() not in (".ttf", ".otf", ".woff", ".woff2"):
            self._json({"ok": False, "error": "no such font: %s" % name}, 404)
            return
        ctype = "font/otf" if p.suffix.lower() == ".otf" else "font/ttf"
        self._send(200, p.read_bytes(), ctype)


def _close_splash() -> None:
    """收掉 PyInstaller 的启动画面（单文件版启动要解压 ~40 MB，那期间就靠它顶着）

    开发运行或没用 `--splash` 时根本没有 pyi_splash 这个模块 → 静默跳过。
    """
    try:
        import pyi_splash                            # type: ignore[import-not-found]
        pyi_splash.close()
    except Exception:                                # noqa: BLE001
        pass


class WizServer(ThreadingHTTPServer):
    daemon_threads = True
    # ★ Windows 上 SO_REUSEADDR 允许**两个**进程绑同一个端口（后者把连接抢走），
    #   关掉它，才能靠「绑不上」判断向导是不是已经在跑
    allow_reuse_address = False


def _is_ours(port: int) -> bool:
    """这个端口上跑的是不是我们自己（双击两次 exe / 先前忘了关时会碰到）"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/options" % port,
                                    timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("title") == APP_TITLE
    except Exception:                                 # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--tab", action="store_true",
                    help="用普通浏览器标签页，而不是 app 窗口（调试用）")
    ap.add_argument("--demo", action="store_true",
                    help=argparse.SUPPRESS)      # 开发自测用：流程照跑但不写盘（界面里没有入口）
    a = ap.parse_args(argv)
    if a.demo:
        E.DEMO = True
    srv, port = None, a.port
    for p in range(a.port, a.port + 10):
        try:
            srv = WizServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:                              # 端口被占
            if _is_ours(p):                          # 是我们自己 → 把界面叫回来就行
                print("向导已经在运行：http://127.0.0.1:%d/" % p, flush=True)
                if not a.no_browser:
                    print("  已打开: %s" % open_window(
                        "http://127.0.0.1:%d/" % p, app_mode=not a.tab), flush=True)
                _close_splash()
                return 0
            continue
    if srv is None:
        print("✗ 端口 %d~%d 都被占用了，换一个：--port 别的" % (a.port, a.port + 9), flush=True)
        _close_splash()
        return 2
    _SRV["srv"] = srv
    url = "http://127.0.0.1:%d/" % port
    print("%s\n  %s%s" % (APP_TITLE, url,
                          "\n  ★ 演示模式（不会修改任何文件）" if E.DEMO else ""), flush=True)

    def _finish_boot() -> None:
        if not a.no_browser:
            print("  已打开: %s" % open_window(url, app_mode=not a.tab), flush=True)
        # 窗口要一会儿才画出来；稍等一下再收启动画面，别留一条缝
        threading.Timer(1.2, _close_splash).start()

    if not a.no_browser:
        threading.Timer(0.6, _finish_boot).start()
    else:
        threading.Timer(0.6, _close_splash).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
