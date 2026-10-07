# -*- coding: utf-8 -*-
"""安装向导的统一主题：**只用游戏色系**。

色值只允许这 5 个（全部来自游戏，见 patcher 那套）：

    --ink     #2b2b20   深墨（页面底色 / 反色后的文字）
    --dark    #333319   深橄榄（页头 / 面板）
    --paper   #e8e2cf   纸色（正文 / 纸片提示）
    --line    #c9c2a8   纸色描边（低透明度使用）
    --light   #E5FFFF   青白（高亮 / 反色底 / 进度）

**没有红色**：强调一律用**反色**（亮底深字 = `--light` 底 + `--ink` 字），
不引入任何第三个色相。层次与状态靠 `rgba(游戏色, alpha)` 与 `filter:brightness()` 派生
（--dim / --faint / --edge / --edge-soft 就是纸色的两档透明度），这样页面始终是同一个色系。

页面用法：把 `<style>/*THEME*/</style>` 留在 HTML 里，文件末尾用 THEME_CSS 替换进去。
"""
from __future__ import annotations

THEME_CSS = r"""
  /* 字体用的是存档工具同款那两款（英文 IMFe / 中文思源宋体）
     ★ 开发测试阶段用的是**未子集化**的全字体（放在 gui/fonts/ 与 font_src/），
       发版时换成子集化的同名文件即可，字族名不用改。 */
  @font-face{font-family:"IMFe";src:url("/fonts/IMFeENrm28P.ttf") format("truetype");
             font-weight:400;font-style:normal;font-display:swap}
  @font-face{font-family:"SourceHanSerif";
             src:url("/fonts/SourceHanSerifSC-SemiBold-subset.otf") format("opentype");
             font-weight:400;font-style:normal;font-display:swap}
  @font-face{font-family:"SourceHanSerifHeavy";
             src:url("/fonts/SourceHanSerifSC-Heavy.otf") format("opentype");
             /* ★ 声明成 700：反色处请求 700 时中文**不再叠加合成加粗** */
             font-weight:700;font-style:normal;font-display:swap}

  :root{
    /* —— 游戏色系（只这 5 个，无红）—— */
    --ink:#2b2b20;
    --dark:#333319;
    --paper:#e8e2cf;
    --line:#c9c2a8;
    --light:#E5FFFF;
    /* —— 派生（不加新色）—— */
    --dim:rgba(232,226,207,.62);          /* 纸色压暗：次要文字 */
    --faint:rgba(232,226,207,.34);        /* 再压暗：边框、弱提示 */
    --edge:rgba(201,194,168,.38);         /* 描边 */
    --edge-soft:rgba(201,194,168,.20);    /* 细描边 */
    /* —— 尺寸：字体整体调大，且随窗口自适应 —— */
    --fs:clamp(16.5px, 0.55vw + 14.5px, 20px);   /* 基准字号（原来的 15px 调到 16.5~20）*/
    --pad:clamp(0.9rem, 1.5vw, 1.8rem);           /* 页面左右内边距 */
    --gap:clamp(0.8rem, 1.2vw, 1.4rem);           /* 块间距 */
    --maxw:min(1400px, 100%);                     /* 内容宽度跟着窗口走 */
    --font:"IMFe","SourceHanSerif","Songti SC","SimSun","Noto Serif CJK SC",Georgia,serif;
    /* 反色（白底黑字）处的字体：英文走 IM FELL + 浏览器**合成加粗**，
       中文回落到思源宋体 Heavy（它声明为 700，所以不会再被叠加一遍）→ 混排粗细一致 */
    --heavy:"IMFe","SourceHanSerifHeavy","SourceHanSerif",
            "Songti SC","SimSun",Georgia,serif;
    --heavy-weight:700;
  }

  *{box-sizing:border-box}
  /* 一律不要圆角（游戏 UI 全是方角） */
  *,*::before,*::after{border-radius:0 !important}
  html{font-size:var(--fs);scrollbar-width:none;-ms-overflow-style:none}
  html::-webkit-scrollbar,body::-webkit-scrollbar,#log::-webkit-scrollbar,
  table::-webkit-scrollbar{width:0;height:0}

  body{margin:0;padding:0 0 3rem;background:var(--ink);color:var(--paper);
       overflow-x:hidden;font:1rem/1.65 var(--font);
       /* 界面文字一律不可选中（只留输入框可选中，见下） */
       -webkit-user-select:none;user-select:none}
  /* 唯一例外：路径输入框得能选、能拖、能改 */
  input,textarea{-webkit-user-select:text;user-select:text}

  header{background:var(--dark);border-bottom:1px solid var(--edge);padding:1rem var(--pad);
         display:flex;align-items:baseline;gap:var(--gap) 1rem;flex-wrap:wrap}
  /* 标题：白字 + 加粗（同样走 IM FELL 合成加粗 + 思源 Heavy 混排） */
  header h1{margin:0;font-size:1.55rem;letter-spacing:.04em;color:var(--light);
            font-family:var(--heavy);font-weight:var(--heavy-weight)}

  main{max-width:var(--maxw);margin:0 auto;padding:1.2rem var(--pad) 2rem}
  section{background:var(--dark);border:1px solid var(--edge-soft);padding:1.1rem var(--pad);
          margin-bottom:var(--gap)}
  section>h2{margin:0 0 .9rem;font-size:1.15rem;color:var(--light);
             font-family:var(--heavy);font-weight:var(--heavy-weight);
             letter-spacing:.05em;border-bottom:1px solid var(--edge-soft);padding-bottom:.5rem}

  .row{display:flex;gap:.6rem var(--gap);align-items:baseline;padding:.28rem 0;flex-wrap:wrap}
  .row .k{min-width:8.5rem;color:var(--dim);font-size:1rem}
  .row .v{font-family:var(--font);font-size:1rem;word-break:break-all;min-width:0;flex:1 1 auto}
  .hint{color:var(--dim);font-size:.95rem;margin:.35rem 0 0}

  /* 提示框也是反色：白底（青白）+ 墨字，左侧一道墨色竖条做标识；文字用 Heavy */
  .warnbox{background:var(--light);border:0;border-left:4px solid var(--ink);
           color:var(--ink);padding:.6rem .85rem;margin:.6rem 0 0;font-size:.98rem;
           font-family:var(--heavy);font-weight:var(--heavy-weight);word-break:break-word}
  .warnbox b{color:var(--ink)}

  button{font:inherit;font-size:1em;background:var(--dark);color:var(--paper);
         border:1px solid var(--edge);padding:.5rem 1.05rem;cursor:pointer;flex:0 0 auto}
  button:hover:not(:disabled){filter:brightness(1.3)}
  /* 主按钮 = 反色（青白底墨字），文字用 --heavy；hover 略暗 */
  button.primary{background:var(--light);border-color:var(--light);color:var(--ink);
                 font-family:var(--heavy);font-weight:var(--heavy-weight)}
  button.primary:hover:not(:disabled){filter:brightness(.93)}
  button:disabled{opacity:.4;cursor:not-allowed;filter:none}

  input[type=text]{font:inherit;font-size:1em;background:var(--ink);color:var(--paper);
                   border:1px solid var(--edge);padding:.45rem .6rem;
                   min-width:0;flex:1 1 20rem}
  input[type=text]:focus{outline:1px solid var(--light);outline-offset:0}

  /* 步骤条 */
  .steps{display:flex;flex-wrap:wrap;gap:.35rem;margin:0 0 var(--gap)}
  .steps div{padding:.3rem .7rem;font-size:.95rem;color:var(--faint);
             border:1px solid var(--edge-soft);background:var(--ink)}
  .steps div.on{color:var(--ink);border-color:var(--light);background:var(--light);
                font-family:var(--heavy);font-weight:var(--heavy-weight)}
  .steps div.done{color:var(--paper);border-color:var(--edge)}

  /* 选项 */
  .choice{display:block;border:1px solid var(--edge-soft);border-left:3px solid var(--edge-soft);
          background:var(--ink);padding:.7rem .9rem;margin:.45rem 0;cursor:pointer}
  .choice:hover{border-color:var(--light)}
  /* 选中 = 整块反色（青白底 + 墨字）；反色处的文字都用 --heavy */
  .choice.sel{border-color:var(--light);border-left-color:var(--light);background:var(--light);
              box-shadow:none}
  .choice b{color:var(--light);font-size:1.06em}
  .choice.sel b{color:var(--ink);font-family:var(--heavy);font-weight:var(--heavy-weight)}
  .choice span{display:block;color:var(--dim);font-size:.96rem;margin-top:.25rem}
  .choice.sel span{color:var(--ink);opacity:.78;font-family:var(--heavy);
                   font-weight:var(--heavy-weight)}
  .choice.sel .preview{font-family:var(--heavy);font-weight:var(--heavy-weight)}
  .grp{margin:1.1rem 0 .25rem;font-size:1.05rem;color:var(--light);
       border-bottom:1px solid var(--edge-soft);padding-bottom:.35rem}
  .preview{background:var(--ink);border:1px solid var(--edge-soft);padding:.55rem .75rem;
           margin:.35rem 0 0;font-size:1.05rem;color:var(--paper);word-break:break-word}

  /* 表格 */
  table{width:100%;border-collapse:collapse;font-size:.98rem;table-layout:fixed}
  th,td{text-align:left;padding:.4rem .55rem;border-bottom:1px solid var(--edge-soft);
        vertical-align:top;word-break:break-all;overflow-wrap:anywhere}
  th{color:var(--dim);font-weight:400}
  /* 状态区分只靠亮度（同一色系）：青白 = 我们的，纸色 = 原版，压暗 = 其它/未知/缺失 */
  .vd-ours{color:var(--light)}
  .vd-vanilla{color:var(--paper)}
  .vd-other,.vd-unknown,.vd-missing{color:var(--faint)}

  /* 日志 / 进度 */
  #log{background:var(--ink);border:1px solid var(--edge-soft);padding:.7rem .85rem;
       height:clamp(13rem, 34vh, 28rem);
       overflow:auto;white-space:pre-wrap;font-family:var(--font);font-size:.95rem;
       color:var(--paper);margin-top:.7rem}
  .bar{height:1.2rem;background:var(--ink);border:1px solid var(--light);margin:.5rem 0 .25rem}
  #fill{height:100%;width:0;background:var(--light);transition:width .35s ease}
  .chips{display:flex;flex-wrap:wrap;gap:.35rem;margin:.6rem 0 0}
  .chips div{padding:.28rem .7rem;font-size:.95rem;color:var(--faint);
             border:1px solid var(--edge-soft);background:var(--ink)}
  .chips div.on{color:var(--ink);border-color:var(--light);background:var(--light);
                font-family:var(--heavy);font-weight:var(--heavy-weight)}
  .chips div.done{color:var(--paper);border-color:var(--edge)}

  .nav{display:flex;gap:.7rem;justify-content:space-between;align-items:center;
       flex-wrap:wrap;margin-top:1.1rem}
  .hide{display:none !important}
  .ok,.done{color:var(--light)}
  .bad{color:var(--ink);background:var(--light);padding:0 .3rem;
       font-family:var(--heavy);font-weight:var(--heavy-weight)}
  .res{font-size:1.05rem;margin-top:.7rem}

  /* 窄窗口：一切都能换行，不出现横向滚动 */
  @media (max-width:760px){
    .row .k{min-width:6rem}
    header h1{font-size:1.3rem}
    .nav{justify-content:flex-end}
    .nav button{flex:1 1 auto}
    .choice{padding:.6rem .7rem}
  }
  @media (max-width:520px){
    .steps div{font-size:.85rem}
    .row{flex-direction:column;gap:.15rem}
    .row .k{min-width:0}
  }
"""
