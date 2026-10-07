#!/usr/bin/env python3
"""比对 WrapProbe 的两份结果，判定「就地改的 CanBreakAfter」是否与参照 build 等价。

用法: python diff_wrap.py <A结果> <B结果> <A标签> <B标签> <详细输出>

结果行格式:  asian \t afterIndex \t 返回值 \t 原文
返回值: 0 / 1 / EX:<异常名>（原版对越界下标会抛）

打印全是 ASCII，详细差异写 UTF-8 文件（避开控制台乱码）。
"""
from __future__ import annotations

import sys
from pathlib import Path


def unescape(s: str) -> str:
    """还原探针写出的转义（\\ -> \\，以及 \\t/\\r/\\n）。

    ★ 必须还原：否则含反斜杠的原文会比真实值长，len() 一变就把「下标正好 = len」
      这种**越界**当成行内用例，统计就乱了。
    """
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append({"\\": "\\", "t": "\t", "r": "\r", "n": "\n"}.get(s[i + 1], s[i + 1]))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def is_ascii_word(ch: str) -> bool:
    """与 DLL 里 IsAsciiWordChar 同义（只对 ASCII 判定）。"""
    return len(ch) == 1 and ord(ch) <= 0x7F and (ch.isalnum() or ch in "_'")


def explain_shrink(text: str, i: int):
    """i 是 vanilla 允许断、patched 拒绝断的位置。

    返回命中的那条新规则名；返回 None = 无法解释（那就是问题）。
    """
    if not (0 <= i < len(text)):
        return None
    c = text[i]
    c2 = text[i - 1] if i > 0 else ""
    if i > 0 and is_ascii_word(c2) and is_ascii_word(c):
        return "两个 ASCII 词字符之间"
    if i > 0 and c in "-." and i + 1 < len(text) \
            and is_ascii_word(text[i + 1]) and is_ascii_word(c2):
        return "'-' / '.' 夹在 ASCII 词中间"
    if i > 0 and c2 in "-." and is_ascii_word(c) and i - 1 >= 1 \
            and is_ascii_word(text[i - 2]):
        return "前一位是 '-' / '.' 且两边都是 ASCII 词字符"
    return None


def load(path: Path) -> list[tuple[int, int, str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        rows.append((int(parts[0]), int(parts[1]), parts[2], unescape(parts[3])))
    return rows


def main() -> int:
    a_path, b_path, a_lab, b_lab, detail_path = sys.argv[1:6]
    A = load(Path(a_path))
    B = load(Path(b_path))

    print("A(%s) cases=%d" % (a_lab, len(A)))
    print("B(%s) cases=%d" % (b_lab, len(B)))
    if len(A) != len(B):
        print("!! 用例数不同，语料不一致，比对无意义")
        return 2

    # 语料键必须一一对应（asian, afterIndex, 原文）—— 注意原文在元组下标 3，不是 2
    bad_key = 0
    for ra, rb in zip(A, B):
        if (ra[0], ra[1], ra[3]) != (rb[0], rb[1], rb[3]):
            bad_key += 1
    print("key_mismatch=%d" % bad_key)
    if bad_key:
        return 2

    diff: list[tuple[int, int, str, str, str]] = []
    for ra, rb in zip(A, B):
        if ra[2] != rb[2]:
            diff.append((ra[0], ra[1], ra[3], ra[2], rb[2]))

    # 分类统计
    n_oob = 0            # 越界下标（i < 0 或 i >= len —— ★ len 也越界，与新版 bounds check 对齐）
    n_shrink = 0         # 行内：A=0 B=1（A 少断了一处 —— 本次改动的预期效果）
    n_grow = 0           # 行内：A=1 B=0（A 多断了 —— 不该出现）
    n_textex = 0         # A 抛异常 / B 不抛（或反之）
    n_other = 0
    for asian, i, text, va, vb in diff:
        oob = i < 0 or i >= len(text)
        ax = va.startswith("EX")
        bx = vb.startswith("EX")
        if oob:
            n_oob += 1
        elif ax or bx:
            n_textex += 1
        elif va == "0" and vb == "1":
            n_shrink += 1
        elif va == "1" and vb == "0":
            n_grow += 1
        else:
            n_other += 1

    print("diff_total=%d" % len(diff))
    print("  out_of_range=%d  (原版抛异常 / 新版返回 false)" % n_oob)
    print("  in_range_shrink=%d  (A=false B=true)" % n_shrink)
    print("  in_range_grow=%d    (A=true B=false)  <- 必须为 0" % n_grow)
    print("  in_range_ex=%d" % n_textex)
    print("  other=%d" % n_other)

    # shrink 归因：每条都应当命中三条新规则之一，否则就是「误拦」
    reasons: dict[str, int] = {}
    unexplained: list[tuple[int, int, str]] = []
    for asian, i, text, va, vb in diff:
        if 0 <= i < len(text) and not va.startswith("EX") and not vb.startswith("EX") \
                and va == "0" and vb == "1":
            why = explain_shrink(text, i)
            if why is None:
                unexplained.append((asian, i, text))
            else:
                reasons[why] = reasons.get(why, 0) + 1
    print("  归因:")
    for k in sorted(reasons):
        print("    %s = %d" % (k, reasons[k]))
    print("    unexplained = %d   <- 必须为 0" % len(unexplained))

    # 按 asian 分组看
    for flag in (1, 0):
        sub = [d for d in diff if d[0] == flag]
        print("  asian=%d: diff=%d" % (flag, len(sub)))

    lines = ["# %s  vs  %s" % (a_lab, b_lab), ""]
    lines.append("diff_total=%d out_of_range=%d shrink=%d grow=%d ex=%d other=%d"
                 % (len(diff), n_oob, n_shrink, n_grow, n_textex, n_other))
    lines.append("")
    # 只列行内差异（越界的太啰嗦），最多 200 条
    shown = 0
    for asian, i, text, va, vb in diff:
        if i < 0 or i >= len(text) or va.startswith("EX") or vb.startswith("EX"):
            continue
        lines.append("asian=%d i=%d  A=%s B=%s   断开点在 %r   原文=%r"
                     % (asian, i, va, vb,
                        text[max(0, i - 1):i + 2], text))
        shown += 1
        if shown >= 200:
            break
    lines.append("")
    for asian, i, text in unexplained[:50]:
        lines.append("UNEXPLAINED asian=%d i=%d 原文=%r" % (asian, i, text))
    lines.append("（越界用例共 %d 条，略）" % n_oob)
    Path(detail_path).write_text("\n".join(lines), encoding="utf-8")
    print("detail -> %s" % detail_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
