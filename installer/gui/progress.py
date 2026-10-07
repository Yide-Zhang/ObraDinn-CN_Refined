# -*- coding: utf-8 -*-
"""安装 / 移除补丁的**独立进度页**（向导点「安装」后跳到 /progress）。

为什么单独一页（用户要求）：安装要跑几分钟，向导那套步骤导航在跑的时候就该让位，
单独页面专心显示进度条 + 实时日志，跑完给结果和「返回向导」。

进度来源：引擎日志里的 `[1/4] ...`（安装）与 `[还原 2/5] ...`（移除），
服务端解析成 step/total 放在 /api/progress 里。不用假造的动画 —— 动一下就是真做了一步。
"""
from __future__ import annotations

PROGRESS_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>正在处理… · 奥伯拉丁中文精修补丁</title>
<link rel="icon" href="/icon.png">
<style>/*THEME*/</style>
</head>
<body>
<header>
  <h1 id="ttl">正在处理…</h1>
</header>
<main>
  <section>
    <h2 id="h2">进度</h2>
    <div class="bar"><div id="fill"></div></div>
    <div class="chips" id="chips"></div>
    <div class="row"><span class="k">状态</span><span class="v" id="progtext">…</span></div>
    <div class="row"><span class="k">已用时间</span><span class="v" id="elapsed">0:00</span></div>
    <div id="log"></div>
    <div class="res" id="result"></div>
    <div class="nav">
      <button id="btnQuit" disabled>退出</button>
    </div>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const show = (id, on) => $(id).classList.toggle("hide", !on);
const STEP_NAMES = ["字体子集", "鸣谢文本", "语言包", "换行修补"];
let T0 = Date.now(), last = null, done = false;

function chips(kind, total, step, finished){
  const c = $("chips"); c.innerHTML = "";
  const names = (kind === "解除安装") ? ["还原备份文件"]
              : (total === 4 ? STEP_NAMES : STEP_NAMES.slice(0, total));
  names.forEach((n, i) => {
    const d = document.createElement("div");
    d.textContent = (i + 1) + " " + n;
    if (finished) d.className = "done";
    else if (i + 1 < step) d.className = "done";
    else if (i + 1 === step) d.className = "on";
    c.appendChild(d);
  });
}
function tick(){
  if (done) return;
  const s = Math.floor((Date.now() - T0) / 1000);
  $("elapsed").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}
setInterval(tick, 500);

async function poll(){
  const r = await (await fetch("/api/progress")).json();
  last = r;
  if (!r.kind && !r.busy && r.log.length === 0){       // 直接打开这个页面，没有任务
    $("ttl").textContent = "没有正在进行的任务";
    $("h2").textContent = "没有任务";
    $("progtext").textContent = "可能已经跑完了，或者你是直接打开这个页面的。";
    $("btnQuit").disabled = false;
    return;
  }
  $("ttl").textContent = "正在" + (r.kind || "处理") + "…";
  $("h2").textContent = "正在" + (r.kind || "处理");
  chips(r.kind, r.total, r.step, !r.busy && r.ok !== null);
  const pct = r.busy ? Math.round(100 * r.step / r.total)
                     : (r.ok === null ? 0 : 100);
  $("fill").style.width = pct + "%";
  $("log").textContent = r.log.join("\n");
  $("log").scrollTop = $("log").scrollHeight;
  $("progtext").textContent = r.busy
      ? (r.step === 0 ? "正在准备…"
         : (r.kind === "解除安装"
            ? ("正在还原第 " + r.step + " / " + r.total + " 个文件…")
            : ("第 " + r.step + " / " + r.total + " 步…")))
      : (r.ok === null ? "…" : (r.ok ? "全部完成 ✓" : "有未完成项 ✗"));
  if (r.busy){ setTimeout(poll, 400); return; }
  done = true;
  $("fill").style.width = "100%";
  const un = (r.kind === "解除安装");
  const head = r.ok ? (un ? "解除安装完成" : "安装完成")
                    : (un ? "解除安装未完成" : "安装未完成");
  $("ttl").textContent = head;
  $("h2").textContent = head;
  $("result").innerHTML = r.ok
      ? '<span class="ok">✓ ' + (r.kind || "任务") + '成功。</span>'
      : '<span class="bad">✗ 没有完全成功 —— 请看上面的日志。</span>';
  $("btnQuit").disabled = false;
  $("btnQuit").className = "primary";
}
$("btnQuit").onclick = async () => {
  try {
    await fetch("/api/quit", {method:"POST", headers:{"Content-Type":"application/json"},
                               body:"{}"});
  } catch (e) {}
  document.body.innerHTML = '<main style="max-width:980px;margin:0 auto;padding:3rem 1.2rem;'
      + 'color:var(--paper);font:var(--fs)/1.65 var(--font)">向导已退出，可以关掉这个窗口了。</main>';
  window.close();
};
poll();
</script>
</body>
</html>
"""

# 主题（只用游戏色系）在 gui/theme.py 统一维护，这里替换进页面
from theme import THEME_CSS as _THEME                     # noqa: E402

PROGRESS_HTML = PROGRESS_HTML.replace("/*THEME*/", _THEME)
