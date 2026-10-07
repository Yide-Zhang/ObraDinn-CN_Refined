# -*- coding: utf-8 -*-
"""验证：对「Windows 原版 shs6」做字节手术（把文本换成我们发布件里的文本），
能否**逐字节复现**我们已发布的 assets/sharedassets6.assets。

能复现 = 这个字节手术就是发布件的生成方式 = 可以在 mac 上用同一套代码、
以「机器自己那份」为基底就地注入（从而保住 mac 的 m_TargetPlatform，不把 Windows 的文件塞进 mac）。

手术内容（与 CN_Refined/assets/inject_credits.py 一致）：
  · 每个 #credits_* 条目：文本 = int32 长度 + UTF-8 + 4 字节对齐
  · 改完同步两处尺寸：SerializedFile 头的 file_size（大端）、
    metadata 里那个 MonoBehaviour 的 byteSize（小端，值是旧值 → 搜出来替换）
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]           # CN_Refined/
VANILLA = ROOT / "originalassets" / "sharedassets6.assets"
OURS = ROOT / "installer" / "assets" / "sharedassets6.assets"
OUT = ROOT / "out" / "_repro_shs6.assets"
REPORT = ROOT / "out" / "_repro_shs6.txt"

L: list[str] = []
say = L.append


def read_str(buf: bytes, off: int):
    """int32(LE) 长度 + 字节 + 4 对齐填充 -> (文本, 下一个偏移)"""
    if off + 4 > len(buf):
        return None
    n = struct.unpack_from("<i", buf, off)[0]
    if not (0 <= n <= 65535) or off + 4 + n > len(buf):
        return None
    raw = buf[off + 4:off + 4 + n]
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(not c.isprintable() and c not in "\r\n\t" for c in s):
        return None
    return s, off + 4 + n + ((-n) % 4)


def entries(buf: bytes):
    """-> [(id, id偏移, 文本, 文本偏移, 文本结束偏移)]"""
    out = []
    off = 0
    while True:
        p = buf.find(b"#credits_", off)
        if p < 0:
            break
        off = p + 1
        rid = read_str(buf, p - 4)
        if not rid or not rid[0].startswith("#credits_"):
            continue
        txt = read_str(buf, rid[1])
        if not txt:
            continue
        out.append((rid[0], p - 4, txt[0], rid[1], txt[1]))
    return out


def pack_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<i", len(b)) + b + b"\x00" * ((-len(b)) % 4)


def splice(buf: bytes, pairs: list[tuple[int, int, str]]) -> bytes:
    """pairs = [(start, end, new_text)]，按偏移升序替换"""
    out = bytearray()
    prev = 0
    for start, end, txt in sorted(pairs):
        out += buf[prev:start]
        out += pack_str(txt)
        prev = end
    out += buf[prev:]
    return bytes(out)


def main() -> int:
    van = VANILLA.read_bytes()
    ours = OURS.read_bytes()
    say("原版 %d B  sha=%s" % (len(van), __import__("hashlib").sha256(van).hexdigest()[:16]))
    say("发布件 %d B  sha=%s" % (len(ours), __import__("hashlib").sha256(ours).hexdigest()[:16]))

    want = {e[0]: e[2] for e in entries(ours)}
    ents = entries(van)
    say("发布件里的 #credits_* 有 %d 条；原版 %d 条" % (len(want), len(ents)))
    changed = [(e[3], e[4], want[e[0]]) for e in ents if want.get(e[0], e[2]) != e[2]]
    say("需要改文本的条目：%d 条" % len(changed))
    for s, e, t in changed[:4]:
        say("   文本 @%d..%d -> %r" % (s, e, t[:60]))

    new = splice(van, changed)
    say("替换后长度 %d（原版 %d，差 %+d）" % (len(new), len(van), len(new) - len(van)))

    # ① 头里的 file_size（大端，偏移 4）
    old_size_be = struct.unpack_from(">I", new, 4)[0]
    b = bytearray(new)
    struct.pack_into(">I", b, 4, len(new))
    say("头 file_size：%d -> %d（大端写入）" % (old_size_be, len(new)))

    # ② metadata 里那个对象的 byteSize（小端）——先从 UnityPy 拿旧值
    try:
        import UnityPy
        env = UnityPy.load(str(VANILLA))
        objs = [o for o in env.objects if o.type.name == "MonoBehaviour"]
        last = max(objs, key=lambda o: o.byte_size) if objs else None
        old_bs = last.byte_size if last else None
    except Exception as exc:                                    # noqa: BLE001
        say("UnityPy 读不了：%s" % exc)
        old_bs = None
    if old_bs:
        delta = len(new) - len(van)
        new_bs = old_bs + delta
        hits = [i for i in range(16, min(4096, len(b) - 4))
                if struct.unpack_from("<I", b, i)[0] == old_bs]
        say("metadata 里 byteSize=%d 的位置：%s；新值应为 %d"
            % (old_bs, hits, new_bs))
        if len(hits) == 1:
            struct.pack_into("<I", b, hits[0], new_bs)
        else:
            say("！位置不唯一或有 %d 处，先不动（看报告）" % len(hits))
    out = bytes(b)
    OUT.write_bytes(out)
    hs = __import__("hashlib").sha256(out).hexdigest()
    say("")
    say("重新生成 %s  %d B  sha=%s" % (OUT.name, len(out), hs[:16]))
    say("与發布件一致 = %s" % (hs == __import__("hashlib").sha256(ours).hexdigest()))
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
