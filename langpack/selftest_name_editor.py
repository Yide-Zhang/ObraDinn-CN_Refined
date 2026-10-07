#!/usr/bin/env python3
"""name_editor 服务的自检：起服务 → 打三个端点 → 验「读-改-写」往返。

全程在临时目录里对**表的副本**做，不碰真表。

用法: python CN_Refined/langpack/selftest_name_editor.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve_name_editor as srv  # noqa: E402


def main() -> int:
    real = HERE / "extracted" / "crew_name_variants.tsv"
    if not real.is_file():
        print("[X] 找不到 %s" % real)
        return 1
    tmpdir = Path(tempfile.mkdtemp(prefix="nameeditor_"))
    tsv = tmpdir / "crew_name_variants.tsv"
    shutil.copy2(real, tsv)
    raw0 = tsv.read_bytes()
    text0 = raw0.decode("utf-8")                       # 保留原行尾
    norm0 = text0.replace("\r\n", "\n")                # 归一化，便于行级比较
    print("表: %d 字节, CRLF %d, LF 总 %d"
          % (len(raw0), raw0.count(b"\r\n"), raw0.count(b"\n")))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(tsv))
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    ok = True

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok
        print("  %s %s%s" % ("[ok]" if cond else "[X] ", name,
                             ("   " + extra) if extra else ""))
        if not cond:
            ok = False

    # 1) 页面本身
    page = urllib.request.urlopen(base + "/", timeout=10).read().decode("utf-8")
    check("GET / 返回编辑器页面", "人名对照表编辑器" in page)
    check("页面自包含（无外部依赖）",
          "<style>" in page and "<script>" in page and "http://" not in page.split("<script>")[0])

    # 2) 读表
    got = urllib.request.urlopen(base + "/api/load", timeout=10).read()
    check("GET /api/load 与磁盘逐字节一致", got == raw0)

    # 3) 原样写回（幂等）
    req = urllib.request.Request(base + "/api/save", data=raw0, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
    check("POST /api/save 返回 ok", r.get("ok") is True)
    check("原样写回后逐字节不变", tsv.read_bytes() == raw0)
    prev = tsv.with_name(tsv.name + ".prev")
    check(".prev 备份是老内容", prev.is_file() and prev.read_bytes() == raw0)

    # 4) 真改一格（v4/v5）再存
    lines = norm0.split("\n")
    hit = False
    for i, ln in enumerate(lines):
        if ln.startswith("[CrewNameCaptain]\t"):
            f = ln.split("\t")
            f[5], f[6] = "罗伯特·威特瑞", "威特瑞"
            lines[i] = "\t".join(f)
            hit = True
            break
    check("测试用的行找得到", hit)
    text1 = "\n".join(lines)
    req = urllib.request.Request(base + "/api/save", data=text1.encode("utf-8"),
                                 method="POST")
    urllib.request.urlopen(req, timeout=10).read()
    back = tsv.read_bytes().decode("utf-8").replace("\r\n", "\n")
    check("改动落盘", "罗伯特·威特瑞" in back and "威特瑞" in back)
    check("只有那一行变了",
          sum(1 for a, b in zip(norm0.split("\n"), back.split("\n")) if a != b) == 1)
    check("注释块原样保留",
          back.startswith("# CN_Refined") and back.count("\n#") == norm0.count("\n#"))

    httpd.shutdown()
    httpd.server_close()
    shutil.rmtree(tmpdir, ignore_errors=True)
    print("结果: " + ("全部通过 ✓" if ok else "有失败 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
