#!/usr/bin/env python3
"""比对 langtool export 出来的 lang-*.tsv，给「dev 内容精修检讨」打底。

用法:
    python compare_lang.py <dev.tsv> <official-zh-s.tsv> <en.tsv> <详细输出.txt>

看的东西：
  * 键集合是否一致、多少条改过
  * 空值 / 与英文完全相同（疑似未译）
  * **换行**：`\\n` 数量、以及 `\\n` 后面紧跟空格/制表符（续行首字符是空白 —— 会顶出来，
    正好撞上咱们那条断行规则）
  * 占位符 `{...}` / `%s` 与官方是否一致（不一致会显示错甚至崩）
  * 没有换行但特别长的条目（会被 wrap 切开）

stdout 只留 ASCII；中文样本写 UTF-8 文件（控制台会搞乱）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PLACE = re.compile(r"\{[^}]*\}|%[sdif]")


def unescape(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"\\": "\\", "n": "\n", "t": "\t", "r": "\r"}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load(path: Path) -> tuple[dict[str, str], str]:
    header = ""
    d: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            header = line
            continue
        k, _, v = line.partition("\t")
        d[k] = unescape(v)
    return d, header


def nls(d: dict[str, str]) -> tuple[int, int, list[str], list[str]]:
    with_nl = sum(1 for v in d.values() if "\n" in v)
    total = sum(v.count("\n") for v in d.values())
    lead = [k for k, v in d.items() if re.search(r"\n[ \t]", v)]
    trail = [k for k, v in d.items() if re.search(r"[ \t]\n", v)]
    return with_nl, total, lead, trail


def main() -> int:
    dev_p, off_p, en_p, out_p = sys.argv[1:5]
    dev, dh = load(Path(dev_p))
    off, oh = load(Path(off_p))
    en, _ = load(Path(en_p))

    print("dev      : %d keys   %s" % (len(dev), dh))
    print("official : %d keys   %s" % (len(off), oh))
    print("en       : %d keys" % len(en))
    print("key_set_equal = %s  (only_dev=%d only_official=%d)"
          % (set(dev) == set(off), len(set(dev) - set(off)), len(set(off) - set(dev))))

    common = [k for k in dev if k in off]
    same = [k for k in common if dev[k] == off[k]]
    diff = [k for k in common if dev[k] != off[k]]
    print("common=%d  identical=%d  changed=%d" % (len(common), len(same), len(diff)))

    empty_dev = [k for k in dev if not dev[k].strip()]
    empty_off = [k for k in off if not off[k].strip()]
    print("empty_value: dev=%d official=%d" % (len(empty_dev), len(empty_off)))

    en_dev = [k for k in dev if k in en and dev[k] == en[k] and dev[k].strip()]
    en_off = [k for k in off if k in en and off[k] == en[k] and off[k].strip()]
    print("value_equal_to_en: dev=%d official=%d" % (len(en_dev), len(en_off)))

    print("total_chars: dev=%d official=%d ; changed_only: dev=%d official=%d"
          % (sum(len(v) for v in dev.values()), sum(len(v) for v in off.values()),
             sum(len(dev[k]) for k in diff), sum(len(off[k]) for k in diff)))

    a = nls(dev)
    b = nls(off)
    print("with_newline: dev=%d official=%d ; total_newlines: dev=%d official=%d"
          % (a[0], b[0], a[1], b[1]))
    print("newline_then_space: dev=%d official=%d   <- 续行首字符是空白"
          % (len(a[2]), len(b[2])))
    print("space_before_newline: dev=%d official=%d" % (len(a[3]), len(b[3])))

    bad_place = [k for k in common if PLACE.findall(dev[k]) != PLACE.findall(off[k])]
    print("placeholder_mismatch_vs_official = %d" % len(bad_place))

    tab_a = sum(v.count("\t") for v in dev.values())
    tab_b = sum(v.count("\t") for v in off.values())
    print("tab_total: dev=%d official=%d" % (tab_a, tab_b))

    def tab_sig(v: str) -> tuple:
        """把值里每段连续制表符的长度取出来 —— 「缩进形状」。"""
        return tuple(len(m.group(0)) for m in re.finditer(r"\t+", v))

    tab_diff = [k for k in common if tab_sig(dev[k]) != tab_sig(off[k])]
    print("tab_indent_shape_differs = %d" % len(tab_diff))

    pipe_dev = [k for k in dev if " | " in dev[k]]
    pipe_off = [k for k in off if " | " in off[k]]
    print("bilingual_pipe(' | '): dev=%d official=%d" % (len(pipe_dev), len(pipe_off)))

    both_empty = [k for k in common if not dev[k].strip() and not off[k].strip()]
    print("empty_in_both = %d %s" % (len(both_empty), both_empty[:5]))

    longest = sorted(((len(v), k) for k, v in dev.items()), reverse=True)[:12]

    rep: list[str] = []
    rep.append("dev      = %s" % dev_p)
    rep.append("official = %s" % off_p)
    rep.append("en       = %s" % en_p)
    rep.append("")
    rep.append("keys: dev=%d official=%d en=%d  key_set_equal=%s"
               % (len(dev), len(off), len(en), set(dev) == set(off)))
    rep.append("identical=%d changed=%d empty(dev)=%d value_equal_to_en(dev)=%d"
               % (len(same), len(diff), len(empty_dev), len(en_dev)))
    rep.append("")
    rep.append("## 续行首字符是空白（\n 后面跟空格）—— dev")
    for k in a[2][:60]:
        rep.append("  %-28s = %r" % (k, dev[k]))
    rep.append("")
    rep.append("## 同上 —— official（作为对照）")
    for k in b[2][:30]:
        rep.append("  %-28s = %r" % (k, off[k]))
    rep.append("")
    rep.append("## 缩进形状与官方不同（dev）—— 例如官方 1 个 \\t、dev 变 2 个")
    for k in tab_diff[:40]:
        rep.append("  %s\n    dev      = %r\n    official = %r" % (k, dev[k], off[k]))
    rep.append("")
    rep.append("## 带双语分隔 ' | ' 的条目")
    for k in pipe_dev[:30]:
        rep.append("  %-28s = %r" % (k, dev[k][:200]))
    rep.append("        （其中官方也有 ' | ' 的：%d 条）" % len(pipe_off))
    rep.append("")
    rep.append("## 占位符与官方不一致 —— dev")
    for k in bad_place[:60]:
        rep.append("  %s\n    dev      = %r\n    official = %r" % (k, dev[k], off[k]))
    rep.append("")
    rep.append("## 无换行且特别长（会被 wrap 切开）—— dev")
    for n, k in longest:
        rep.append("  %4d  %-28s = %r" % (n, k, dev[k][:200]))
    rep.append("")
    rep.append("## 与英文完全相同（疑似未译）—— dev")
    for k in en_dev[:60]:
        rep.append("  %-28s = %r" % (k, dev[k]))
    rep.append("")
    rep.append("## 空值 —— dev")
    for k in empty_dev[:60]:
        rep.append("  %s" % k)
    rep.append("")
    rep.append("## 改动过的条目样本（dev vs official，前 40）")
    for k in diff[:40]:
        rep.append("  %s\n    dev      = %r\n    official = %r" % (k, dev[k], off[k]))
    Path(out_p).write_text("\n".join(rep), encoding="utf-8")
    print("detail -> %s" % out_p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
