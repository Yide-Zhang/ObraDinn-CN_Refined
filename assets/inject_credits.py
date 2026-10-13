# -*- coding: utf-8 -*-
"""往 sharedassets6.assets 注入鸣谢文本。

结构（已查明）：
  该文件是一个 SerializedFile，里面有一个 MonoBehaviour 存着「鸣谢」——
  形如 `#credits_loc_chinese_s` 这样的 ID 后面紧跟它对应的文本，
  字符串格式 = `int32 长度` + UTF-8 字节 + 4 字节对齐填充；
  该 MonoBehaviour 是**最后一个对象**（数据到文件尾），所以改长度只需同步：
    · 头部 file_size
    · metadata 里该对象的 byteSize

用法:
  python CN_Refined\\assets\\inject_credits.py --list
  python CN_Refined\\assets\\inject_credits.py --dump 9700 10100
  python CN_Refined\\assets\\inject_credits.py --set credits_loc_chinese_s "新文本" [--base ...] [--out ...]
  python CN_Refined\\assets\\inject_credits.py --reproduce      # 用你的旧产物反向验证补丁逻辑
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets" / "sharedassets6.assets"
USER = ROOT / "CN_Refined" / "olddevassets" / "sharedassets6.assets"
OUTDEF = ROOT / "CN_Refined" / "out" / "assets" / "sharedassets6.assets"
CREDITS_PREFIX = b"#credits_"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def hexdump(buf: bytes, lo: int, hi: int, width: int = 16) -> list[str]:
    out = []
    for off in range(lo, hi, width):
        chunk = buf[off:min(off + width, hi)]
        hx = " ".join("%02x" % b for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "·" for b in chunk)
        out.append("  %08d  %-47s  %s" % (off, hx, asc))
    return out


def pad4(n: int) -> int:
    return (-n) % 4


def read_str(buf: bytes, off: int):
    """读一个 Unity 串： int32(LE) 长度 + 字节 + 4 对齐填充 -> (文本, 下一个偏移, 长度, 填充)"""
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
    nxt = off + 4 + n + pad4(n)
    return s, nxt, n, pad4(n)


def find_entries(buf: bytes):
    """-> [(id偏移, id文本, 文本偏移, 文本, 文本之后的下一个偏移, ...)]"""
    ents = []
    off = 0
    while True:
        p = buf.find(CREDITS_PREFIX, off)
        if p < 0:
            break
        off = p + 1
        start = p - 4                     # 长度前缀在 ID 之前
        if start < 0:
            continue
        rid = read_str(buf, start)
        if not rid:
            continue
        id_txt, id_next, id_n, id_pad = rid
        if not id_txt.startswith("#credits_"):
            continue
        rtx = read_str(buf, id_next)      # 文本紧跟 ID 之后
        if not rtx:
            continue
        txt, txt_next, txt_n, txt_pad = rtx
        ents.append((start, id_txt, id_next, txt, txt_next,
                     id_n, id_pad, txt_n, txt_pad))
    return ents


def locate_fields(buf: bytes, env=None):
    """找出 file_size 与最后对象 byteSize 两个 4 字节字段的偏移与字节序。

    · byteSize 的值从 UnityPy 取（它读得出来），只在 metadata 区里搜这一个值
    · file_size 的值就是文件长度，在前 64 字节里搜
    """
    import UnityPy
    env = UnityPy.load(str(ORIG)) if env is None else env
    tails = [o for o in env.objects if o.type.name == "MonoBehaviour"]
    if not tails:
        return None
    # 数据区里最后出现的那个对象 = MonoBehaviour
    last = max(env.objects, key=lambda o: o.byte_size)
    bs = last.byte_size
    hits = [i for i in range(16, min(len(buf), 4096))
            if struct.unpack_from("<I", buf, i)[0] == bs
            or struct.unpack_from(">I", buf, i)[0] == bs]
    sz_hits = []
    for i in range(0, 64):
        if i + 4 <= 64:
            if struct.unpack_from("<I", buf, i)[0] == len(buf):
                sz_hits.append((i, "<"))
            if struct.unpack_from(">I", buf, i)[0] == len(buf):
                sz_hits.append((i, ">"))
    return {"byteSize": bs, "bs_hits": hits, "size_hits": sz_hits, "last": last}


def scan_layout(buf: bytes):
    """把每条 ID/文本的 前缀偏移、串尾、填充量 都列出来，反推对齐规则。"""
    rows = []
    for e in find_entries(buf):
        start, id_txt, id_next, txt, txt_next, id_n, id_pad, txt_n, txt_pad = e
        rows.append({"id": id_txt, "pfx": start, "id_end": start + 4 + id_n,
                     "txt_pfx": id_next, "txt_end": id_next + 4 + txt_n,
                     "next": txt_next, "id_n": id_n, "txt_n": txt_n})
    for a, b in zip(rows, rows[1:]):
        a["gap1"] = a["txt_pfx"] - a["id_end"]      # ID 之后的填充
        a["gap2"] = b["pfx"] - a["txt_end"]         # 文本之后的填充(到下一个 ID 前缀)
    return rows


def find_text_block(buf: bytes, id_key: str):
    """定位某个鸣谢 ID 对应的**文本块**。

    -> (前缀偏移, 旧文本, 块总长) 或 None
    算法：从 ID 串尾往后，找第一个「4 对齐、int32 长度>0、且后面那 n 字节是合法可打印 UTF-8」的位置。
    """
    key = id_key if id_key.startswith("#") else "#" + id_key
    kb = key.encode()
    o = buf.find(kb)
    if o < 0:
        return None
    id_end = o + len(kb)
    for p in range(id_end, min(len(buf) - 8, id_end + 64)):
        if p % 4:
            continue
        n = struct.unpack_from("<i", buf, p)[0]
        if n <= 0 or p + 4 + n > len(buf):
            continue
        try:
            s = buf[p + 4:p + 4 + n].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if any(not c.isprintable() and c not in "\r\n\t" for c in s):
            continue
        old_len = 4 + n + pad4(n)
        return p, s, old_len
    return None


def patch_credits(buf: bytes, edits: dict[str, str]):
    """把若干条鸣谢文本换掉 -> (新字节, 明细)。

    ★ 该 MonoBehaviour 是最后一个对象，所以改长度只需同步两处：
        · 头部 file_size（偏移 4，**大端** uint32）
        · metadata 里本对象的 byteSize（偏移 184，**小端** uint32）
      —— 这两处的偏移/字节序都是用「复现你的旧产物」反推并验证过的。
    """
    out = bytearray(buf)
    delta_total = 0
    detail = []
    for key, new_text in edits.items():
        hit = find_text_block(out, key)
        if not hit:
            raise SystemExit("找不到鸣谢条目 %s" % key)
        pfx, old, old_len = hit
        nb = new_text.encode("utf-8")
        new_len = 4 + len(nb) + pad4(len(nb))
        block = struct.pack("<i", len(nb)) + nb + b"\x00" * pad4(len(nb))
        out[pfx:pfx + old_len] = block
        delta = new_len - old_len
        delta_total += delta
        detail.append((key, old, new_text, old_len, new_len, delta, pfx))

    if delta_total:
        fs = struct.unpack_from(">I", out, 4)[0]
        struct.pack_into(">I", out, 4, fs + delta_total)
        bs = struct.unpack_from("<I", out, 184)[0]
        struct.pack_into("<I", out, 184, bs + delta_total)
        detail.append(("file_size(偏移4,大端)", str(fs), str(fs + delta_total),
                       0, 0, delta_total, 4))
        detail.append(("byteSize(偏移184,小端)", str(bs), str(bs + delta_total),
                       0, 0, delta_total, 184))
    return bytes(out), detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ORIG))
    ap.add_argument("--out", default=str(OUTDEF))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dump", nargs=2, type=int, metavar=("LO", "HI"))
    ap.add_argument("--set", nargs=2, metavar=("ID", "TEXT"))
    ap.add_argument("--reproduce", action="store_true")
    ap.add_argument("--scan", action="store_true", help="列出各条的对齐填充量，反推规则")
    args = ap.parse_args()

    base = Path(args.base)
    buf = bytearray(base.read_bytes())
    say("基准 %s  %d 字节" % (base, len(buf)))
    info = locate_fields(bytes(buf))
    if info:
        say("  最后对象的 byteSize = %d  在 metadata 里出现于偏移 %s"
            % (info["byteSize"], info["bs_hits"][:5]))
        say("  文件长度 %d  在前 64 字节里出现于 %s"
            % (len(buf), [(i, e) for i, e in info["size_hits"]]))
    ents = find_entries(bytes(buf))
    say("  鸣谢条目 %d 条" % len(ents))
    say("")

    if args.dump:
        lo, hi = args.dump
        say("--- 头部 0..48 ---")
        lines.extend(hexdump(bytes(buf), 0, 48))
        say("--- 字段区 160..200 ---")
        lines.extend(hexdump(bytes(buf), 160, 200))
        say("--- %d..%d ---" % (lo, hi))
        lines.extend(hexdump(bytes(buf), lo, hi))
        say("")

    if args.list or not (args.dump or args.set or args.reproduce):
        say("%-30s %-6s %s" % ("ID", "长度", "当前文本"))
        for e in ents:
            _, sid, _, txt, *_ = e
            say("%-30s %-6d %s" % (sid, len(txt.encode()), txt.replace("\n", "\\n")))
        say("")

    if args.scan:
        rows = scan_layout(bytes(buf))
        say("%-30s %6s %6s %8s %8s %5s %5s  %s"
            % ("ID", "id_n", "txt_n", "id_end", "txt_pfx", "gap1", "gap2", "4对齐检查"))
        for r in rows:
            chk = ""
            if "gap1" in r:
                # 猜：串块整体按 8 对齐？或 ID 块 4 对齐后再多 4？
                chk = "id+n=%d→%d pad=%d ; +4=%d" % (
                    4 + r["id_n"], r["id_end"], r["gap1"],
                    (-(4 + r["id_n"])) % 4)
            say("%-30s %6d %6d %8d %8d %5s %5s  %s"
                % (r["id"], r["id_n"], r["txt_n"], r["id_end"], r["txt_pfx"],
                   r.get("gap1", "-"), r.get("gap2", "-"), chk))
        say("")

    if args.set:
        key, new_text = args.set
        data, detail = patch_credits(bytes(buf), {key: new_text})
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(data)
        say("已写入 %s  %d → %d 字节" % (args.out, len(buf), len(data)))
        for k, o, nt, ol, nl, d, p in detail:
            say("  %-28s @%-6d %r → %r   块 %d→%d (%+d)"
                % (k, p, o[:28] if isinstance(o, str) else o[:28],
                   nt[:28] if isinstance(nt, str) else nt,
                   ol, nl, d))
        say("")

    if args.reproduce:
        # 用你的旧产物反向验证：把原文改成你改的那句，看能不能**逐字节复现你的文件**
        say("【复现验证】把原文的 credits_loc_chinese_s 改成你写的内容")
        data, _ = patch_credits(bytes(ORIG.read_bytes()),
                                {"credits_loc_chinese_s": "Yide Zhang 翼德大大"})
        ref = USER.read_bytes()
        same = data == ref
        say("  我们生成 %d 字节   你的旧产物 %d 字节   →   **逐字节相同 = %s**"
            % (len(data), len(ref), same))
        if not same:
            n = min(len(data), len(ref))
            d = [i for i in range(n) if data[i] != ref[i]]
            say("  不同字节数 %d；首 8 处： %s" % (len(d), d[:8]))
            for i in d[:4]:
                say("     @%d  我们 %02x  你的 %02x" % (i, data[i], ref[i]))
        say("")

    text = "\n".join(lines)
    print("\n".join(l for l in lines if l.isascii()))
    (HERE / "out" / "credits.txt").write_text(text + "\n", encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
