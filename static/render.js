/* ============ 统一渲染管线：Markdown(GFM) + LaTeX 公式 + 表格 + 图片 ============
 * 所有输入预览与 LLM 输出共用此模块，保证「输入所见 = 输出所见」。
 * 依赖（本地内置，离线可用）：
 *   /vendor/marked.min.js         GFM 解析
 *   /vendor/mathjax/tex-svg.js    TeX -> SVG（无字体依赖）
 */
"use strict";

var Render = (function () {

  /* ---------- 公式占位符：用 \u0002 包裹，不会被 markdown 语法干扰 ---------- */
  var PH_RE = /\u0002MJ(\d+)\u0002/g;
  var PH_MAKE = function (i) { return "\u0002MJ" + i + "\u0002"; };

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* 判断 $...$ 是否像数学，避免把「金额 $50」「$5-10」误当公式 */
  function looksLikeMath(tex) {
    var t = String(tex).trim();
    if (!t || t.length > 300) return false;
    if (/^[\d\s.,%]+$/.test(t)) return false;              // 纯数字金额
    if (/^[\d\s.,]*[元美欧]/.test(t)) return false;         // 50 元
    var hasTex = /[\\^_{}=+\-*/<>]/.test(t);
    if (/[\u4e00-\u9fa5]/.test(t) && !hasTex) return false; // 中文且无 LaTeX 特征
    return /[\\^_{}=+\-*/<>]|[A-Za-z]/.test(t);
  }

  /* 从原始 markdown 中抽出公式，替换为占位符 */
  function splitMath(src) {
    var store = [];
    function put(tex, display) {
      store.push({ tex: tex, display: display });
      return PH_MAKE(store.length - 1);
    }
    var s = String(src == null ? "" : src);

    // 1) 块级 $$...$$（可跨行）
    s = s.replace(/\$\$([\s\S]+?)\$\$/g, function (m, tex) { return put(tex, true); });
    // 2) 块级 \[...\]
    s = s.replace(/\\\[([\s\S]+?)\\\]/g, function (m, tex) { return put(tex, true); });
    // 3) 未包裹定界符的 LaTeX 环境（模型常直接输出 \begin{equation}...）
    s = s.replace(
      /\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|split|aligned|cases|matrix|pmatrix|bmatrix|vmatrix|array)\}([\s\S]+?)\\end\{\1\}/g,
      function (m, env, body) { return put("\\begin{" + env + "}" + body + "\\end{" + env + "}", true); }
    );
    // 4) 行内 \(...\)
    s = s.replace(/\\\(([\s\S]+?)\\\)/g, function (m, tex) { return put(tex, false); });
    // 5) 行内 $...$（不跨行，长度受限，需通过 looksLikeMath）
    s = s.replace(/(^|[^\\$])\$([^\n$]{1,300}?)\$(?!\d)/g, function (m, pre, tex) {
      if (!looksLikeMath(tex)) return m;
      return pre + put(tex, false);
    });
    return { text: s, store: store };
  }

  /* 把占位符还原成可被 MathJax 识别的元素 */
  function fillMath(html, store) {
    html = html.replace(PH_RE, function (m, i) {
      var it = store[+i];
      if (!it) return "";
      var tex = escHtml(it.tex);
      if (it.display) {
        return '<div class="math-block"><span class="math-tex">$$' + tex + "$$</span></div>";
      }
      return '<span class="math-inline math-tex">$' + tex + "$</span>";
    });
    // 块级公式被 <p> 包裹时拆开，避免非法嵌套
    html = html.replace(/<p>\s*(<div class="math-block">[\s\S]*?<\/div>)\s*<\/p>/g, "$1");
    html = html.replace(/<br\s*\/?>\s*(<div class="math-block">)/g, "$1");
    html = html.replace(/(<\/div>)\s*<br\s*\/?>/g, "$1");
    return html;
  }

  /* 未被抽走的 $ 交给 MathJax 时会被误配对成公式。
     用占位符隔成独立 span：MathJax 只在单个文本节点内匹配定界符，跨元素不会误判。 */
  var DLR = "\u0002DLR\u0002";
  function markDollars(mdText) {
    return mdText.replace(/\$/g, DLR);
  }
  function restoreDollars(html) {
    return html.split(DLR).join('<span class="lit-dollar">$</span>');
  }

  var markedReady = false;
  function ensureMarked() {
    if (markedReady) return true;
    if (typeof marked === "undefined") return false;
    try {
      marked.use({ gfm: true, breaks: true });
      markedReady = true;
    } catch (e) { return false; }
    return true;
  }

  /* ---------- 主入口：markdown -> html（不含数学排版） ---------- */
  function md(text) {
    if (!text) return "";
    var sp = splitMath(text);
    var src = markDollars(sp.text);

    if (ensureMarked()) {
      var html = marked.parse(src);
      return restoreDollars(fillMath(html, sp.store));
    }

    /* 兜底：marked 未加载时走极简渲染，至少保留换行与粗体 */
    var h = escHtml(src);
    h = h.replace(/```([\s\S]*?)```/g, function (m, code) { return "<pre><code>" + code + "</code></pre>"; });
    h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/^####\s+(.*)$/gm, "<h4>$1</h4>")
      .replace(/^###\s+(.*)$/gm, "<h3>$1</h3>")
      .replace(/^##\s+(.*)$/gm, "<h2>$1</h2>")
      .replace(/^#\s+(.*)$/gm, "<h1>$1</h1>");
    h = h.split(/\n{2,}/).map(function (seg) {
      seg = seg.trim();
      if (!seg) return "";
      if (/^<(h\d|pre)/.test(seg)) return seg;
      return "<p>" + seg.replace(/\n/g, "<br>") + "</p>";
    }).join("\n");
    return restoreDollars(fillMath(h, sp.store));
  }

  /* ---------- MathJax 排版（串行队列，避免并发 typeset 冲突） ---------- */
  var mjQueue = Promise.resolve();

  function mathTargets(el) {
    var list = [];
    if (!el.querySelectorAll) return list;
    el.querySelectorAll(".math-block, .math-tex").forEach(function (n) {
      if (n.classList.contains("math-block")) {
        if (n.querySelector(".math-tex")) list.push(n);
      } else if (!n.closest(".math-block")) {
        list.push(n);
      }
    });
    return list;
  }

  function typeset(el) {
    if (!el) return Promise.resolve();
    var MJ = window.MathJax;
    var nodes = mathTargets(el);
    if (!nodes.length) nodes = [el];

    if (!MJ || typeof MJ.typesetPromise !== "function") {
      fallbackMath(el);
      return Promise.resolve();
    }

    mjQueue = mjQueue.then(function () {
      try { if (MJ.typesetClear) MJ.typesetClear(nodes); } catch (e) {}
      // 先整块排版（快）；失败则逐个重试，只降级真正出错的那一个公式，
      // 避免一个 \boldsymbol 之类的未知宏把整篇公式全打成源码。
      return MJ.typesetPromise(nodes).catch(function () {
        return nodes.reduce(function (p, node) {
          return p.then(function () {
            return MJ.typesetPromise([node]).catch(function () { fallbackMath(node); });
          });
        }, Promise.resolve());
      });
    }).catch(function () {});
    return mjQueue;
  }

  /* MathJax 不可用/渲染失败：把 TeX 原样显示为代码，不静默丢内容 */
  function fallbackMath(el) {
    el.querySelectorAll(".math-tex").forEach(function (n) {
      if (n.querySelector("svg") || n.classList.contains("math-failed")) return;
      n.classList.add("math-failed");
      var raw = n.textContent.replace(/^\$\$?|\$\$?$/g, "");
      n.innerHTML = '<code class="math-raw">' + escHtml(raw) + "</code>";
    });
  }

  /* ---------- DOM 后处理：表格滚动容器 / 图片放大 / 外链 ---------- */
  var lightbox = null;
  function getLightbox() {
    if (lightbox) return lightbox;
    lightbox = document.createElement("div");
    lightbox.className = "img-lightbox";
    lightbox.innerHTML = '<img alt="">';
    lightbox.addEventListener("click", function () { lightbox.classList.remove("on"); });
    document.body.appendChild(lightbox);
    return lightbox;
  }

  function enhance(el) {
    if (!el) return;
    el.classList.add("md");

    // 表格：包一层横向滚动容器，避免长表格撑破版面
    el.querySelectorAll("table").forEach(function (t) {
      if (t.parentNode && t.parentNode.classList.contains("table-wrap")) return;
      var w = document.createElement("div");
      w.className = "table-wrap";
      t.parentNode.insertBefore(w, t);
      w.appendChild(t);
    });

    // 图片：懒加载 + 点击放大
    el.querySelectorAll("img").forEach(function (img) {
      img.classList.add("md-img");
      img.loading = "lazy";
      img.addEventListener("click", function () {
        var lb = getLightbox();
        lb.querySelector("img").src = img.src;
        lb.classList.add("on");
      });
      img.addEventListener("error", function () {
        if (img.dataset.failed) return;
        img.dataset.failed = "1";
        var ph = document.createElement("span");
        ph.className = "img-broken";
        ph.textContent = "🖼 图片未能加载：" + (img.getAttribute("alt") || img.getAttribute("src"));
        img.parentNode.insertBefore(ph, img);
      });
    });

    // 外链新窗口
    el.querySelectorAll('a[href^="http"]').forEach(function (a) {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    });

    return typeset(el);
  }

  /* 一步到位：把 markdown 渲染进容器 */
  function render(el, text) {
    if (!el) return Promise.resolve();
    el.innerHTML = md(text);
    return enhance(el);
  }

  return {
    md: md,
    enhance: enhance,
    render: render,
    typeset: typeset,
    splitMath: splitMath,
    escapeHtml: escHtml
  };
})();

/* MathJax 全局配置：必须在 tex-svg.js 之前生效（index.html 中先于此文件内联设置） */
