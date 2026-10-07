#!/usr/bin/env python3
"""纹理碎片选取器的本地服务（只为让网页能读纹理、存坐标、导出碎片）。

    python CN_Refined/langpack/serve_frag.py [--port 8796] [--no-open]

    GET  /                    选取器页面（frag_editor.html）
    GET  /api/textures        四张纹理的清单（名字/宽/高）
    GET  /api/texture/<name>  纹理原图（PNG 字节）
    GET  /api/rects           已保存的碎片坐标（JSON）
    POST /api/rects           保存碎片坐标（先 .prev，再临时文件 + os.replace 原子替换）
    POST /api/fragment?name=X 保存一块裁好的碎片到 out/fragments/

只绑 127.0.0.1。双击 frag_editor.html 也能用，但那种方式要手动选文件、碎片只能下载。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # CN_Refined/
TEXDIR = ROOT / "Textures"
HTML = HERE / "frag_editor.html"
RECTS = HERE / "extracted" / "fragments.json"
FRAGOUT = HERE.parent / "out" / "fragments"
MAX_BODY = 32 * 1024 * 1024
SAFE = re.compile(r"^[A-Za-z0-9_. -]+$")


def safe_file_name(name: str, ext: str = ".png") -> bool:
    """只拦路径穿越与控制字符；允许中文（碎片名会是 FolioSketch_f1_贵族标题.png）。"""
    if not name or not name.lower().endswith(ext):
        return False
    if name.startswith(".") or "/" in name or "\\" in name or ".." in name:
        return False
    return not any(ord(c) < 32 for c in name)

TARGET_COUNT = {"ManifestCrew": 3, "FolioSketch": 1}


def textures():
    out = []
    if not TEXDIR.is_dir():
        return out
    try:
        from PIL import Image
    except ImportError:
        Image = None
    for p in sorted(TEXDIR.glob("*.png")):
        wk = p.stem.strip()
        w = h = 0
        if Image is not None:
            try:
                with Image.open(p) as im:
                    w, h = im.size
            except Exception:
                pass
        out.append({"file": p.name, "key": wk, "w": w, "h": h,
                    "target": TARGET_COUNT.get(wk, 0),
                    "size": p.stat().st_size})
    return out


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "FragPicker/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            sys.stderr.write("  %s\n" % (fmt % args))

        def _send(self, code, body: bytes, ctype="application/octet-stream", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):                                     # noqa: N802
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                if not HTML.is_file():
                    return self._send(500, b"frag_editor.html missing",
                                      "text/plain; charset=utf-8")
                return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/textures":
                return self._json({"dir": str(TEXDIR), "textures": textures()})
            if u.path == "/api/rects":
                if not RECTS.is_file():
                    return self._json({})
                return self._json(json.loads(RECTS.read_text(encoding="utf-8")))
            if u.path.startswith("/api/texture/"):
                name = unquote(u.path[len("/api/texture/"):])
                if not safe_file_name(name):
                    return self._send(400, b"bad name", "text/plain; charset=utf-8")
                p = TEXDIR / name
                if not p.is_file():
                    return self._send(404, ("no such texture: " + name).encode("utf-8"),
                                      "text/plain; charset=utf-8")
                return self._send(200, p.read_bytes(), "image/png")
            return self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self):                                    # noqa: N802
            u = urlparse(self.path)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > MAX_BODY:
                return self._send(400, b"bad content-length", "text/plain; charset=utf-8")
            data = self.rfile.read(n)

            if u.path == "/api/rects":
                try:
                    json.loads(data.decode("utf-8"))           # 只收合法 JSON
                except Exception as e:
                    return self._send(400, ("bad json: %s" % e).encode("utf-8"),
                                      "text/plain; charset=utf-8")
                RECTS.parent.mkdir(parents=True, exist_ok=True)
                if RECTS.is_file():
                    shutil.copy2(RECTS, RECTS.with_name(RECTS.name + ".prev"))
                tmp = RECTS.with_name(RECTS.name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, RECTS)
                return self._json({"ok": True, "path": str(RECTS), "bytes": len(data)})

            if u.path == "/api/fragment":
                q = parse_qs(u.query)
                name = (q.get("name") or [""])[0]
                if not safe_file_name(name):
                    return self._send(400, b"bad fragment name",
                                      "text/plain; charset=utf-8")
                FRAGOUT.mkdir(parents=True, exist_ok=True)
                dst = FRAGOUT / name
                dst.write_bytes(data)
                return self._json({"ok": True, "path": str(dst), "bytes": len(data)})

            return self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8796)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if not TEXDIR.is_dir():
        print("[X] 找不到纹理目录 %s" % TEXDIR)
        return 1
    print("纹理目录 : %s" % TEXDIR)
    for t in textures():
        hint = "   ← 需要 %d 处碎片" % t["target"] if t["target"] else ""
        print("   %-20s %5d x %-5d%s" % (t["file"], t["w"], t["h"], hint))
    url = "http://127.0.0.1:%d/" % args.port
    print("碎片选取器: %s   （Ctrl+C 退出）" % url)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler())
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    print("退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
