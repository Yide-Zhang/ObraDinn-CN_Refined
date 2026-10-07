# -*- coding: utf-8 -*-
"""安装向导的页面（内嵌 HTML/CSS/JS，无外部依赖）。

观感沿用 patcher/ 那套：游戏里的深/浅色（#333319 / #E5FFFF）、一律方角、
两款游戏字体（英文 IMFe、中文思源宋体 SemiBold）。

流程（用户定的）：
    目录 → 和谐 → 双语 → 姓名样式（英/中）→ 旧/新（仅中文）→ 缩写（英文强制缩写）
    → 难度（参考 hardcore）→ 复核 → 安装 / 移除补丁
"""
from __future__ import annotations

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>《奥伯拉丁的回归》中文精修补丁安装向导</title>
<link rel="icon" href="/icon.png">
<style>/*THEME*/</style>
</head>
<body>
<header>
  <h1>《奥伯拉丁的回归》中文精修补丁安装向导</h1>
</header>
<main>
  <div class="steps" id="stepsBar"></div>

  <!-- 0. 欢迎 -->
  <section id="s0">
    <h2>欢迎</h2>
    <p class="hint">欢迎来到《奥伯拉丁的回归》中文补丁的安装向导。请选择要做的事：</p>
    <label class="choice" data-g="action" data-v="install"><b>安装</b>
      <span>把中文补丁装进游戏；随时可以用「解除安装」还原回去。</span></label>
    <label class="choice" data-g="action" data-v="uninstall"><b>解除安装</b>
      <span>把游戏恢复到安装前的样子（用安装时留下的备份写回）。</span></label>
    <div class="nav">
      <span></span>
      <span>
        <button id="btnQuit0">退出</button>
        <button class="primary" id="btnNext0" disabled>下一步</button>
      </span>
    </div>
  </section>

  <!-- 1. 目录 -->
  <section id="s1" class="hide">
    <h2>1 · 游戏目录</h2>
    <div class="row"><span class="k">自动检测</span><span class="v" id="autoInfo">…</span></div>
    <div class="row">
      <span class="k">安装目录</span>
      <input type="text" id="game" placeholder="Return of the Obra Dinn 的安装目录，或 ObraDinn_Data 本身">
      <button id="btnPick">浏览…</button>
      <button id="btnCheck">检查</button>
    </div>
    <p class="hint" id="gameHint"></p>
  </section>

  <!-- 2. 和谐 -->
  <section id="s2" class="hide">
    <h2>2 · 是否和谐</h2>
    <label class="choice" data-g="harm" data-v="no"><b>未和谐（推荐）</b>
      <span>保留原有地名文本。</span></label>
    <label class="choice" data-g="harm" data-v="yes"><b>和谐版</b>
      <span>用于录制视频 / 直播：把不易过审的地名相关文字处理掉。</span></label>
    <div class="warnbox hide" id="harmWarn">选「否（未和谐）」时请注意：本游戏中的部分地名相关
      文字内容部分平台不易过审，若你要录制视频或直播，建议改用和谐版。</div>
  </section>

  <!-- 3. 双语 -->
  <section id="s3" class="hide">
    <h2>3 · 是否双语</h2>
    <label class="choice" data-g="dialog" data-v="bi"><b>双语显示（推荐）</b>
      <span>中文与英文并列显示（对话里英文+中文）。</span></label>
    <label class="choice" data-g="dialog" data-v="mono"><b>单语（纯中文）</b>
      <span>只显示中文；官方有竖线分行的地方保留原句。</span></label>
  </section>

  <!-- 4. 姓名样式（选中文时给出两个子选择支：译文版本 + 缩写） -->
  <section id="s4" class="hide">
    <h2>4 · 姓名样式</h2>
    <label class="choice" data-g="nameStyle" data-v="zh"><b>中文姓名</b>
      <span>人名用中文写法（如「翼德大大」）。</span></label>
    <label class="choice" data-g="nameStyle" data-v="en"><b>英文姓名</b>
      <span>人名保留英文（如「Yide Zhang」）。</span></label>

    <div id="subZh">
      <div class="grp">译文版本</div>
      <label class="choice" data-g="tran" data-v="old"><b>旧翻译</b>
        <span>和社区里流传的版本一致，和人交流方便。</span></label>
      <label class="choice" data-g="tran" data-v="new"><b>新翻译（精修）</b>
        <span>更准确，但与人交流时对不上。</span></label>

      <div class="grp">姓名缩写</div>
      <label class="choice" data-g="short" data-v="full"><b>不缩写</b>
        <div class="preview" id="pvFull"></div></label>
      <label class="choice" data-g="short" data-v="abbr"><b>缩写</b>
        <div class="preview" id="pvShort"></div></label>
    </div>

    <p class="hint" id="s4Hint"></p>
  </section>

  <!-- 5. 复核（难度是静默读取的，不占一步、也不显示） -->
  <section id="s5" class="hide">
    <h2>5 · 复核</h2>
    <table><tbody id="review"></tbody></table>
    <div class="nav">
      <button id="btnBack">← 上一步</button>
      <button class="primary" id="btnInstall">安装</button>
    </div>
  </section>

  <!-- 解除安装：自己的第二步（走另一条流程，见 panels()） -->
  <section id="sU" class="hide">
    <h2>2 · 确认解除</h2>
    <div id="unHasRecord">
      <p class="hint">将要把游戏恢复到安装前的样子 —— 下面这些文件会用安装时留下的备份覆盖回去。</p>
      <table><thead><tr><th style="width:58%">文件</th><th>备份</th></tr></thead>
      <tbody id="unBody"></tbody></table>
      <div class="warnbox">备份里也包含 DLL。解除之后如果还想用补丁，重新装一次即可；
        <b>在我们安装之前别人打过的补丁会原样保留</b>。</div>
    </div>
    <div id="unNoRecord" class="hide">
      <div class="warnbox">这台机器上没有安装记录（可能没装过，或者备份文件夹
        <code>ObraDinnCN-installer</code> 已被删除）—— 没有可以还原的东西。</div>
    </div>
    <div class="nav">
      <button id="btnUnBack">← 上一步</button>
      <button class="primary" id="btnUnDo" disabled>解除安装</button>
    </div>
  </section>

  <!-- 进度：安装/移除会跳到独立页面 /progress，这里不再内嵌 -->
</main>

<script>
const S = {game:"", how:"", action:"", harm:"no", dialog:"bi",
           nameStyle:"", tran:"", short:"", shortZh:"",
           level:3, backups:[], opts:null, steps:[]};

const $ = id => document.getElementById(id);
const show = (id, on) => $(id).classList.toggle("hide", !on);

/* ---------- 选项加载 ---------- */
async function loadOptions(){
  S.opts = await (await fetch("/api/options")).json();
  $("autoInfo").textContent = S.opts.game_auto.found
      ? S.opts.game_auto.path + "（" + S.opts.game_auto.how + "）"
      : "没找到：" + S.opts.game_auto.how;
  if (S.opts.game_auto.found) $("game").value = S.opts.game_auto.path;
  $("pvFull").textContent = S.opts.preview.full;
  $("pvShort").textContent = S.opts.preview.short;
  S.level = 3; S.shortZh = "";
  bindChoices();
  renderSteps();
  syncUI();
}

/* ---------- 单选组 ---------- */
function bindChoices(){
  document.querySelectorAll("[data-g]").forEach(el => {
    el.onclick = () => pick(el.dataset.g, el.dataset.v);
  });
}
function pick(g, v){
  if (g === "nameStyle"){
    if (v === "en"){ S.shortZh = S.short || S.shortZh; S.short = "abbr"; }
    else { S.short = S.shortZh || ""; }          // 切回中文：只恢复选过的，否则保持未选
  }
  S[g] = (g === "level") ? parseInt(v, 10) : v;
  if (g === "action") renderSteps();           // 安装/解除是两套步骤，重画步骤条
  syncUI();
  goto(S.stepIndex || 0);
}
/* 选中的判定：状态里的值 == 这个选项的 data-v（以前误写成 S[el.dataset.v]，永远 undefined → 高亮从未生效） */
function selOf(el){ return S[el.dataset.g] !== "" && String(S[el.dataset.g]) === String(el.dataset.v); }

/* 姓名样式必须选全才能去复核（用户要求：默认不预设任何选择） */
function s4Ready(){
  if (!S.nameStyle) return false;
  if (S.nameStyle === "en") return true;        // 英文只有缩写一种，静默定好
  return !!S.tran && !!S.short;
}

/* 只改**内容**与页内子块，不碰步骤面板本身的显隐（那个一律归 goto() 管） */
function syncUI(){
  document.querySelectorAll("[data-g]").forEach(el => el.classList.toggle("sel", selOf(el)));
  show("harmWarn", S.harm === "no");
  show("subZh", S.nameStyle === "zh");        // 中文才问译文版本与缩写
  const b0 = $("btnNext0"); if (b0) b0.disabled = !S.action;
  const h = $("s4Hint");
  if (h){
    if (!S.nameStyle) h.textContent = "请先选择姓名样式。";
    else if (S.nameStyle === "zh" && (!S.tran || !S.short)) h.textContent = "请再把译文版本与姓名缩写选完。";
    else h.textContent = "";
  }
  const b4 = document.querySelector("#s4 button.primary");
  if (b4) b4.disabled = !s4Ready();
}

/* ---------- 步骤条 ---------- */
/* 两条流程：安装 5 步，解除 2 步（目的就是别让人在安装向导里迷路） */
function stepList(){
  return (S.action === "uninstall") ? ["目录", "确认解除"]
                                    : ["目录", "和谐", "双语", "姓名样式", "复核"];
}
function renderSteps(){
  const bar = $("stepsBar"); bar.innerHTML = "";
  stepList().forEach((t, i) => {
    const d = document.createElement("div"); d.textContent = (i+1) + " " + t;
    bar.appendChild(d);
  });
}

/* ---------- 版本映射 ---------- */
function versionOf(){
  if (S.nameStyle === "en") return "v3";
  if (S.tran === "old") return S.short === "full" ? "v1" : "v2";
  return S.short === "full" ? "v4" : "v5";
}

/* ---------- 目录与状态 ---------- */
async function checkGame(){
  const g = $("game").value.trim();
  if (!g){ $("gameHint").textContent = "请填写或选择目录。"; return false; }
  const r = await (await fetch("/api/state?game=" + encodeURIComponent(g))).json();
  if (!r.ok){
    $("gameHint").innerHTML = '<span class="bad">' + r.error + "</span>";
    S.game = ""; return false;
  }
  S.game = r.game; S.how = r.how;
  S.level = r.level; S.levelLabel = r.level_label || "";   // 难度：静默记着，界面不展示
  S.backups = r.backup_files || [];
  // 状态诊断不摆给用户看：引擎自己分得清 原版/我们的/未知，并各自处理
  // （未知文件会在安装前弹确认框，那条路径与这张表无关）
  $("gameHint").innerHTML = '已识别：<b>' + r.game + "</b>（" + r.how + "）";
  return true;
}


/* ---------- 复核 ---------- */
function reviewRows(){
  const rows = [
    ["游戏目录", S.game],
    ["和谐", S.harm === "yes" ? "和谐版" : "未和谐"],
    ["对话", S.dialog === "bi" ? "双语" : "单语（纯中文）"],
    ["姓名样式", S.nameStyle === "en" ? "英文姓名" : "中文姓名"],
  ];
  if (S.nameStyle === "zh"){
    rows.push(["译文版本", S.tran === "old" ? "旧翻译" : "新翻译（精修）"]);
    rows.push(["姓名缩写", S.short === "full" ? "不缩写" : "缩写"]);
  } else {
    rows.push(["姓名缩写", "缩写"]);          // 英文只有这一种，不额外提示
  }
  rows.push(["版本号", versionOf()]);
  return rows;
}

/* ---------- 页面切换 ---------- */
function stepIndex(){ return S.stepIndex || 0; }
function panels(){
  return (S.action === "uninstall") ? ["s0","s1","sU"] : ["s0","s1","s2","s3","s4","s5"];
}
async function goto(i){
  const p = panels();
  i = Math.max(0, Math.min(p.length - 1, i));
  S.stepIndex = i;
  // 先关掉**所有**面板（含另一条流程的 sU），否则切换流程时会残留一页
  ["s0","s1","s2","s3","s4","s5","sU"].forEach(id => show(id, false));
  p.forEach((id, k) => show(id, k === i));
  if (p[i] === "sU") renderUninstall();
  if (p[i] === "s5"){
    $("review").innerHTML = reviewRows().map(r =>
      "<tr><th style='width:9rem'>" + r[0] + "</th><td>" + r[1] + "</td></tr>").join("");
  }
  const ds = $("stepsBar").children;
  const bi = i - 1;                                  // s0 是欢迎页，不占步骤条
  $("stepsBar").style.visibility = (i === 0) ? "hidden" : "visible";
  for (let k = 0; k < ds.length; k++){
    ds[k].classList.toggle("on", k === bi);
    ds[k].classList.toggle("done", k < bi);
  }
}
function nav(i, label){
  const d = document.createElement("div"); d.className = "nav";
  const b = document.createElement("button"); b.textContent = "← 上一步";
  b.onclick = () => goto(i - 1);
  const f = document.createElement("button"); f.className = "primary";
  f.textContent = label || "下一步 →";
  f.onclick = async () => {
    if (i === 1 && !(await checkGame())) return;
    if (i === 4 && !s4Ready()) return;
    goto(i + 1);
  };
  d.appendChild(b); d.appendChild(f);
  return d;
}

/* ---------- 安装 / 还原 ---------- */
async function post(path, body){
  return await (await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
                                   body: JSON.stringify(body)})).json();
}
async function start(kind){
  const body = {game: S.game, version: versionOf(), harmonized: S.harm === "yes",
                dialog: S.dialog, force: true};      // 难度由引擎自己读游戏，不传
  let r = await post("/api/" + kind, body);
  if (r.need_confirm){
    const list = r.need_confirm.map(x => "· " + x.rel + " —— " + x.detail).join("\n");
    if (!confirm("下面这些文件既不是原版、也不是我们认识的产物：\n\n" + list
        + "\n\n安装会在它们现有的内容上继续做（不会覆盖别人的改动）。要继续吗？")) return;
    r = await post("/api/" + kind, Object.assign(body, {confirmed: true}));
  }
  if (!r.ok){ alert(r.error || "启动失败"); return; }
  location.href = "/progress";          // 安装/移除走独立页面（有进度条与完整日志）
}

/* ---------- 退出 / 解除安装 ---------- */
async function quitWizard(){
  try { await post("/api/quit", {}); } catch (e) {}
  document.body.innerHTML = '<main style="max-width:980px;margin:0 auto;padding:3rem 1.2rem;'
      + 'color:var(--paper);font:var(--fs)/1.65 var(--font)">向导已退出，可以关掉这个窗口了。</main>';
  window.close();
}
/* ---------- 解除安装：确认页 ---------- */
function fmtSize(n){
  if (!n) return "0 B";
  if (n >= 1048576) return (n / 1048576).toFixed(2) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
function renderUninstall(){
  const has = (S.backups || []).length > 0;
  show("unHasRecord", has);
  show("unNoRecord", !has);
  // 没东西可还原时，右下角不该还摆个「解除安装」——改成「退出」
  const b = $("btnUnDo");
  b.disabled = false;
  b.textContent = has ? "解除安装" : "退出";
  b.onclick = has ? doRestore : quitWizard;
  if (has){
    $("unBody").innerHTML = S.backups.map(x =>
      "<tr><td>" + x.rel + "</td><td>" +
      (x.exists ? fmtSize(x.size) : "（备份缺失）") + "</td></tr>").join("");
  }
}
async function doRestore(){
  if (!confirm("解除安装 = 把游戏恢复到**安装前**的样子（用备份覆盖回去）。\n\n"
      + "这会把备份的那几个文件写回，包括 DLL —— 之后如果还想用补丁，重新装一次即可。\n\n继续吗？"))
    return;
  start("restore");
}

/* ---------- 启动 ---------- */
(async function(){
  [1,2,3,4].forEach(i => $("s" + i).appendChild(nav(i, i === 4 ? "去复核 →" : null)));
  $("btnBack").onclick = () => goto(4);
  $("btnQuit0").onclick = quitWizard;
  $("btnNext0").onclick = () => goto(1);          // 两条流程都先去选目录
  $("btnUnBack").onclick = () => goto(1);
  $("btnPick").onclick = async () => {
    const r = await post("/api/pick", {initial: S.game || $("game").value.trim()});
    if (r.ok){ $("game").value = r.path; await checkGame(); }
    else if (r.error){ alert(r.error); }
  };
  $("btnCheck").onclick = checkGame;
  $("btnInstall").onclick = () => start("install");
  await loadOptions();
  syncUI();
  goto(0);
  if (S.opts.game_auto.found) await checkGame();
})();
</script>
</body>
</html>
"""

# 主题（只用游戏色系）在 gui/theme.py 统一维护，这里替换进页面
from theme import THEME_CSS as _THEME                     # noqa: E402

INDEX_HTML = INDEX_HTML.replace("/*THEME*/", _THEME)
