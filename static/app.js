/* ============ PaperMate 开源论文搭子 · 前端逻辑 ============ */
"use strict";

var CFG = loadCfg();
var META = null;
var SESSIONS = {};   // stage -> session_id
var LEXICAL = null;  // 最近一次词面检测结果

/* ---------- 工具 ---------- */
function $(id){ return document.getElementById(id); }
function escapeHtml(s){
  return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function api(path, body){
  var res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  var data = await res.json().catch(function(){ return {}; });
  if(!res.ok){
    var err = new Error(data.detail || ("请求失败（HTTP " + res.status + "）"));
    err.status = res.status;   // 405 要能识别成「后端是旧版本」，不能当成地址错
    // 401 = 登录过期。云部署后会经常遇到（Cookie 满 30 天、或管理员改了口令）。
    // 统一跳到登录页并带上回跳地址，比让用户对着「请求失败」猜要好。
    if(res.status === 401){
      var here = location.pathname + location.search;
      location.href = "/login.html?next=" + encodeURIComponent(here);
    }
    throw err;
  }
  return data;
}

function llmFields(){
  return {api_key: CFG.api_key || "", base_url: CFG.base_url || "", model: CFG.model || ""};
}

/* ---------- 设置 · 模型接入 ---------- */

function loadCfg(){
  try{ return JSON.parse(localStorage.getItem("acw_cfg") || "{}"); }
  catch(e){ return {}; }
}
function saveCfg(){
  localStorage.setItem("acw_cfg", JSON.stringify(CFG));
}

var CFG_PROVIDER = "";   // 当前选中的服务商预设

var PROMO = {
  url: "https://www.lumdatech.com/?utm_source=academic-writing-agent&utm_medium=referral&utm_campaign=promo",
  title: "萤算搭子 · 注册即送 5 元体验券",
  body: "一个 key 调 DeepSeek V4 / Flash，低至 6 折起，星际直连，OpenAI 兼容。",
  cta: "去看看 →"
};

function promoHtml(extra){
  return '<div class="promo-head"><span class="promo-tag">推广</span>'
    + '<b>' + escapeHtml(PROMO.title) + '</b></div>'
    + '<p>' + escapeHtml(PROMO.body) + (extra ? " " + escapeHtml(extra) : "") + '</p>'
    + '<a class="btn sm" href="' + PROMO.url + '" target="_blank" rel="noopener sponsored">'
    + escapeHtml(PROMO.cta) + '</a>'
    + '<div class="promo-foot">推广链接；价格与可用性以平台实时页面为准，本站不代收费用。</div>';
}

function providerOf(base){
  var b = (base || "").toLowerCase();
  if(b.indexOf("lumdatech") >= 0) return "lumda";
  if(b.indexOf("anthropic") >= 0 || b.indexOf("claude.ai") >= 0) return "anthropic";
  if(b.indexOf("deepseek") >= 0) return "deepseek";
  return "";
}

function renderProviders(){
  var box = $("cfgProviders");
  if(!box) return;
  var ps = (META && META.providers) || {};
  box.innerHTML = Object.keys(ps).map(function(k){
    return '<button type="button" class="chip' + (k === CFG_PROVIDER ? " on" : "")
      + '" onclick="chooseProvider(\'' + k + '\')">' + escapeHtml(ps[k].label) + '</button>';
  }).join("");
  renderProviderMeta();
}

function renderProviderMeta(){
  var ps = (META && META.providers) || {};
  var p = ps[CFG_PROVIDER] || {};
  var note = $("cfgProvNote");
  if(note) note.textContent = p.note || "";
  var box = $("cfgModels");
  if(!box) return;
  box.innerHTML = (p.models || []).map(function(m){
    return '<button type="button" class="chip sm" onclick="pickModel(\'' + m + '\')">' + escapeHtml(m) + '</button>';
  }).join("");
}

function chooseProvider(k){
  var ps = (META && META.providers) || {};
  var p = ps[k] || {};
  CFG_PROVIDER = k;
  if(p.base_url) $("cfg-base").value = p.base_url;
  if(p.models && p.models.length) $("cfg-model").value = p.models[0];
  $("cfgTestResult").innerHTML = "";
  renderProviders();
}

function pickModel(m){
  $("cfg-model").value = m;
}

function openSettings(){
  $("cfg-key").value = CFG.api_key || "";
  $("cfg-base").value = CFG.base_url || "";
  $("cfg-model").value = CFG.model || "";
  // 没配置过时默认落在 DeepSeek，并把它家的地址/模型填好，省得用户自己想
  CFG_PROVIDER = CFG.base_url ? providerOf(CFG.base_url) : "deepseek";
  $("cfgTestResult").innerHTML = "";
  $("cfgTestHint").textContent = "";
  $("settingsPromo").innerHTML = promoHtml("填好地址就能用，不用换客户端。");
  if(!CFG.base_url){
    var p0 = (META && META.providers && META.providers["deepseek"]) || {};
    if(p0.base_url && !$("cfg-base").value) $("cfg-base").value = p0.base_url;
    if(!$("cfg-model").value && p0.models && p0.models.length) $("cfg-model").value = p0.models[0];
  }
  renderProviders();
  $("settingsModal").style.display = "flex";
}
function closeSettings(){ $("settingsModal").style.display = "none"; }

function saveSettings(){
  CFG.api_key = $("cfg-key").value.trim();
  // 前端先做一层轻量清理：用户常把整条端点粘进来
  CFG.base_url = $("cfg-base").value.trim()
    .replace(/\/+$/, "")
    .replace(/\/(v1\/)?chat\/completions$/i, "")
    .replace(/\/(v1\/)?messages$/i, "")
    .replace(/\/(v1\/)?complete$/i, "");
  CFG.model = $("cfg-model").value.trim();
  saveCfg();
  closeSettings();
  updateKeyNotice();
}

async function testLLM(){
  var key = $("cfg-key").value.trim();
  if(!key){ $("cfgTestHint").textContent = "先填 API Key"; return; }
  var btn = $("btnCfgTest");
  btn.disabled = true; btn.textContent = "测试中…";
  $("cfgTestResult").innerHTML = "";
  try{
    var r = await api("/api/llm/test", {
      api_key: key,
      base_url: $("cfg-base").value.trim(),
      model: $("cfg-model").value.trim()
    });
    var rows = [];
    rows.push('<div class="kv"><span>结果</span><b class="' + (r.ok ? "ok-t" : "no-t") + '">'
      + (r.ok ? "连接正常" : "未通过") + '</b></div>');
    rows.push('<div class="kv"><span>实际地址</span><code>' + escapeHtml(r.base_used || "—") + '</code></div>');
    if(r.protocol){
      rows.push('<div class="kv"><span>协议</span><span>'
        + (r.protocol === "anthropic" ? "Anthropic 原生 Messages" : "OpenAI 兼容")
        + '</span></div>');
    }
    if(r.corrected){
      rows.push('<div class="kv"><span>已自动纠正</span><span>' + escapeHtml(r.note || "") + '</span></div>');
    }
    if(r.latency_ms != null){
      rows.push('<div class="kv"><span>延迟</span><span>' + r.latency_ms + ' ms</span></div>');
    }
    if(r.models && r.models.length){
      rows.push('<div class="kv"><span>可用模型</span><span>' + r.models.length + ' 个，例如 '
        + escapeHtml(r.models.slice(0, 4).join("、")) + '</span></div>');
    }
    if(r.hint){
      rows.push('<div class="kv"><span>说明</span><span>' + escapeHtml(r.hint) + '</span></div>');
    }
    $("cfgTestResult").innerHTML = '<div class="test-card ' + (r.ok ? "ok" : "no") + '">'
      + rows.join("") + '</div>';
    $("cfgTestHint").textContent = r.ok ? "可以用" : "按上面的说明改一下再试";
  }catch(e){
    var msg = e.message || String(e);
    if(e.status === 405){
      msg = "后端还是旧版本：当前进程里没有 /api/llm/test 这个接口（405 Method Not Allowed）。"
          + "这不是 API 地址的问题——关掉那个命令行窗口，重新双击 start.bat 再试。";
    }
    $("cfgTestResult").innerHTML = '<div class="test-card no"><div class="kv"><span>说明</span><span>'
      + escapeHtml(msg) + '</span></div></div>';
    $("cfgTestHint").textContent = "自检失败";
  }finally{
    btn.disabled = false; btn.textContent = "测试连接";
  }
}

/* ---------- 已定题目：中文自动译成英文题名 ---------- */
var TITLE_BUSY = false;
var TITLE_ORIG = "";

function titleHasCJK(s){ return /[\u3400-\u9fff]/.test(String(s || "")); }

function titleNote(html){
  var el = $("s7-title-note");
  if(!el) return;
  el.innerHTML = html || "";
  el.style.display = html ? "block" : "none";
}

function osUndoTranslate(){
  var el = $("s7-title");
  if(el && TITLE_ORIG) el.value = TITLE_ORIG;
  TITLE_ORIG = "";
  titleNote("");
}

async function osTranslateTitle(manual){
  var el = $("s7-title");
  if(!el) return;
  var v = el.value.trim();
  if(!v){ if(manual) titleNote("先填题目，再点翻译。"); return; }
  if(!titleHasCJK(v)){
    if(manual) titleNote("这已经是英文题名，无需翻译。");
    return;
  }
  if(TITLE_BUSY) return;
  TITLE_BUSY = true;
  var btn = $("btnTranslateTitle");
  if(btn){ btn.disabled = true; btn.textContent = "翻译中…"; }
  titleNote("正在译为英文题名…");
  try{
    var r = await api("/api/oneshot/title/translate", Object.assign({title: v}, llmFields()));
    TITLE_ORIG = v;
    el.value = r.title_en || v;
    titleNote('已译为英文题名。原题：' + escapeHtml(v)
      + ' · <a href="javascript:;" onclick="osUndoTranslate()">撤销</a>');
  }catch(e){
    var msg = e.message || String(e);
    if(e.status === 405){
      msg = "后端还是旧版本，没有翻译接口（405）。请重新双击 start.bat 后再试";
    }
    titleNote('翻译没成功：' + escapeHtml(msg) + '。可手动改写成英文，或稍后重试。');
  }finally{
    TITLE_BUSY = false;
    if(btn){ btn.disabled = false; btn.textContent = "译为英文"; }
  }
}

function updateKeyNotice(){
  var n = $("keyNotice");
  if(!n) return;
  // BYOK 模式下服务端 Key 不作数，只有用户自己填了才该消掉提示
  var hasServer = META && META.has_default_key;
  n.style.display = (CFG.api_key || hasServer) ? "none" : "block";
  if(!CFG.api_key && !hasServer && META && META.access && META.access.mode === "byok"){
    n.innerHTML = '⚠️ 本站不提供公共 Key，请在右上角「设置」里填你自己的 API Key'
      + '（DeepSeek / Anthropic / 萤算 任选一家）。Key 只保存在你本机浏览器里。';
  }
}

/* ---------- Markdown 渲染：统一走 Render（GFM 表格 + LaTeX 公式 + 图片） ---------- */
function md(text){
  if (window.Render && Render.md) return Render.md(text);
  return escapeHtml(text || "");
}

/* 按需增强容器：表格滚动、图片放大、公式排版 */
function enhance(el){
  if (el && window.Render && Render.enhance) Render.enhance(el);
  return el;
}

/* ---------- 导航 ---------- */
var TABS = [
  ["home","能力首页"],["stage1","选题"],["stage2","研究设计"],["stage3","初稿写作"],
  ["stage4","引用格式"],["stage5","投稿前审查"],["stage6","投稿返修"],["stage7","一键成稿"]
];
function buildNav(){
  var nav = $("nav");
  nav.innerHTML = TABS.map(function(t){
    return '<button data-tab="'+t[0]+'">'+t[1]+'</button>';
  }).join("");
  nav.addEventListener("click", function(e){
    var b = e.target.closest("button"); if(!b) return;
    switchTab(b.getAttribute("data-tab"));
  });
}
function switchTab(id){
  document.querySelectorAll("nav button").forEach(function(b){
    b.classList.toggle("on", b.getAttribute("data-tab") === id);
  });
  document.querySelectorAll("section").forEach(function(s){ s.classList.remove("on"); });
  var el = $("page-" + id);
  if(el) el.classList.add("on");
  window.scrollTo({top:0, behavior:"smooth"});
}

function buildCapabilities(){
  var caps = [
    ["选题定位","写之前","判断\"做什么方向、值不值得做\"，产出研究问题与 gap 论证。"],
    ["研究设计评审","写之前","校验识别策略、内生性、抽样、对照组与可复现性。"],
    ["初稿写作引导","写之中","按引言/方法/结果/讨论逐段给框架与正反例句。"],
    ["引用格式规范","写之中","四套体系（IEEE/APA/GB7714/脚注）选型与逐条修正。"],
    ["投稿前审查","写之后","结构自检 + 词面检测 + 大模型逐条判读 + 三层风险清单。"],
    ["投稿与返修","投稿阶段","投稿包清单 + rebuttal 结构（逐条回应审稿意见）。"],
    ["一键成稿（学术小白）","全流程","先在选题页用雷达定题，再自动跑设计→大纲→分章成稿→文献装配→自检，产出引用可核实的英文工作稿。"]
  ];
  $("capGrid").innerHTML = caps.map(function(c, i){
    return '<div class="cap" data-tab="stage'+(i+1)+'"><div class="num">'+(i+1)+'</div><div class="t">'+c[0]+'</div><div class="d">'+c[2]+'</div><span class="enter">进入 →</span></div>';
  }).join("");
  $("capGrid").addEventListener("click", function(e){
    var c = e.target.closest(".cap"); if(!c) return;
    switchTab(c.getAttribute("data-tab"));
  });
}

function buildTrackTable(){
  var rows = [
    ["工程/AI（EI、AI 会议；工程类 SCI）","ei-conf / ai-conf","ok","113"],
    ["定量实证（经济/管理/金融/社会学）","quant","ok","56 + 共用"],
    ["预测建模 / 数据科学","predictive","ok","25 + 16"],
    ["质性研究（案例/现象学/扎根/民族志）","qualitative","ok","41"],
    ["博士大论文","dissertation","ok","15 + 共用"],
    ["基础科学实验（化学/生物/材料/物理）","basic-science","warn","24（未校验）"],
    ["临床与医学","clinical","warn","32（未校验）"],
    ["纯理论数理（数学/理论物理/理论经济）","—","no","不支持"]
  ];
  var html = "<tr><th>学科主线</th><th>track</th><th>支持度</th><th>规则数</th></tr>";
  rows.forEach(function(r){
    var b = r[2]==="ok"?"ok":(r[2]==="warn"?"warn":"no");
    var label = r[2]==="ok"?"完整":(r[2]==="warn"?"次要线·未校验":"不支持");
    html += "<tr><td>"+r[0]+"</td><td>"+r[1]+"</td><td><span class=\"badge "+b+"\">"+label+"</span></td><td>"+r[3]+"</td></tr>";
  });
  $("trackTable").innerHTML = html;
}

function fillTrackSelects(){
  if(!META) return;
  var opts = Object.keys(META.tracks).map(function(k){
    return '<option value="'+k+'">'+META.tracks[k]+'（'+k+'）</option>';
  }).join("");
  ["s1-track","s2-track","s3-track","s5-track","s6-track","s7-track"].forEach(function(id){
    $(id).innerHTML = opts;
  });
  var gopts = Object.keys(META.genres).map(function(k){
    return '<option value="'+k+'">'+META.genres[k]+'（'+k+'）</option>';
  }).join("");
  $("s5-genre").innerHTML = gopts;
  $("s7-genre").innerHTML = gopts;
  $("s5-track").addEventListener("change", updateStats);
  // track 联动 genre（basic-science -> sci-journal 等）
  $("s5-track").addEventListener("change", syncGenre);
  syncGenre();
  updateStats();

  // stage1 选题：track 联动目标期刊下拉 + 初始化
  $("s1-track").addEventListener("change", refreshVenueSelect);
  refreshVenueSelect();

  // stage7 一键成稿：体裁跟随主线，语言决定默认引用体系
  $("s7-track").addEventListener("change", function(){
    syncGenre7();
    // 手改主线后，数据卡里的「建议」要重新比对，否则一直显示旧结论
    if(OS_DATA) renderDataProfile(OS_DATA);
  });
  syncGenre7();
  $("s7-lang").addEventListener("change", function(){
    $("s7-citation").value = $("s7-lang").value === "zh" ? "gb7714" : "apa";
  });
  // 数据状态改了，数据卡里的提示要跟着变
  var ds = $("s7-data");
  if(ds) ds.addEventListener("change", function(){
    if(OS_DATA) renderDataProfile(OS_DATA);
    // 选「帮我找数据源 / 演示模式」且已填题目：直接把检索跑起来，省掉再点一次按钮
    var t = ($("s7-title") && $("s7-title").value || "").trim();
    if((ds.value === "find" || ds.value === "demo") && t && (!OS_SOURCES || OS_SOURCES_TOPIC !== t)) osFindSources();
  });
}

/* ---------- 阶段 1：目标期刊下拉（按 track 过滤，可自定义） ---------- */
var VENUES_CACHE = {};  // track -> [venue objects]

async function loadVenues(track){
  if(VENUES_CACHE[track]) return VENUES_CACHE[track];
  try{
    var r = await (await fetch("/api/topic/venues?track=" + encodeURIComponent(track))).json();
    VENUES_CACHE[track] = r.venues || [];
    return VENUES_CACHE[track];
  }catch(e){ return []; }
}

async function refreshVenueSelect(){
  var track = $("s1-track").value;
  var sel = $("s1-venue");
  var venues = await loadVenues(track);
  var html = '<option value="">（不指定 / 自定义）</option>';
  venues.forEach(function(v){
    var label = v.name + (v.en && v.en !== v.name ? " · " + v.en : "") + " ｜ " + (v.tier || "");
    html += '<option value="'+escapeHtml(v.name)+'">'+escapeHtml(label)+'</option>';
  });
  sel.innerHTML = html;
}

/* ---------- 阶段 1：跑 OpenAlex 趋势 ---------- */
var TREND_DATA = null;   // 最近一次趋势结果
var TREND_QUERY = "";    // 该结果对应的检索词（用于判断是否已过期）

/* 当前雷达应使用的检索词：优先 OpenAlex 检索词，留空则用研究方向 */
function radarQuery(){
  return ($("s1-trend").value.trim() || $("s1-dir").value.trim() || "");
}

/* 趋势数据是否与当前检索词脱节（换了题目但没重跑） */
function trendIsStale(){
  if(!TREND_DATA) return false;
  var q = radarQuery();
  return !!q && q !== TREND_QUERY;
}

/* 输入变化时立刻提示“图表已过期”，避免旧图被当成新题目的结果 */
function watchTrendInputs(){
  ["s1-trend", "s1-dir"].forEach(function(id){
    var el = $(id);
    if(!el) return;
    el.addEventListener("input", function(){
      var tip = $("trendStaleTip");
      if(!tip){
        if(!TREND_DATA) return;
        tip = document.createElement("p");
        tip.id = "trendStaleTip";
        tip.className = "hint";
        tip.style.cssText = "color:#e8870c;margin:8px 0 0";
        $("trendBox").appendChild(tip);
      }
      if(trendIsStale()){
        tip.innerHTML = "⚠️ 研究方向/检索词已改成「" + escapeHtml(radarQuery())
          + "」，上方图表仍是「" + escapeHtml(TREND_QUERY) + "」的结果，请重新点「跑趋势」。"
          + "未重跑前，AI 评估不会使用这份过期趋势数据。";
        tip.style.display = "";
      }else{
        tip.style.display = "none";
      }
    });
  });
}

async function runTrend(){
  var topic = radarQuery();
  if(!topic){ alert("请先填写研究方向或趋势检索词"); return; }
  var btn = document.querySelector('[onclick="runTrend()"]');
  var box = $("trendBox");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 拉取中…';
  box.style.display = "block";
  box.innerHTML = '<p class="hint">拉取 OpenAlex 趋势中…</p>';
  try{
    var r = await api("/api/topic/trend", {topic: topic});
    TREND_DATA = r;
    TREND_QUERY = topic;
    renderTrend(r);
  }catch(e){
    box.innerHTML = '<p class="hint" style="color:#d93025">'+escapeHtml(e.message)+'</p>';
  }finally{
    btn.disabled = false; btn.textContent = "跑趋势";
  }
}

function renderTrend(r){
  var box = $("trendBox");
  var groups = r.groups || [];
  if(!groups.length){
    box.innerHTML = '<p class="hint">未检索到发文记录。OpenAlex 为英文库，中文主题请转英文检索词。</p>';
    return;
  }
  var max = Math.max.apply(null, groups.map(function(g){ return g.count; }).concat([1]));
  var bars = groups.map(function(g){
    var cls = "tcol" + (g.partial ? " partial" : "");
    var bar;
    if(g.count > 0){
      var h = Math.max(6, Math.round(g.count / max * 100));
      bar = '<div class="tbar" style="height:'+h+'%"><span class="tval">'+g.count+'</span></div>';
    }else{
      bar = '<div class="tbar zero"></div>';
    }
    return '<div class="'+cls+'"><div class="tslot">'+bar+'</div>'
      + '<div class="tyr">'+g.year+'</div></div>';
  }).join("");

  var html = '<div class="trend-head"><b>「'+escapeHtml(r.topic)+'」近年发文量</b>'
    + '<span class="trend-sub">OpenAlex · 题名+摘要匹配</span></div>'
    + '<div class="tchart">'+bars+'</div>';

  if(groups.some(function(g){ return g.partial; })){
    html += '<div class="trend-legend"><i class="sw-partial"></i>'
      + '斜纹柱为当年（数据截至今日，尚未完整，仅供参考）</div>';
  }

  if(r.growth === null || r.growth === undefined){
    html += '<p class="hint trend-growth">'+escapeHtml(r.label)+' —— '+escapeHtml(r.hint)+'</p>'
      + '<p class="hint" style="color:#6b7280">'+escapeHtml(r.note || '数据不足，无法判断趋势')+'</p>';
  }else{
    var color = r.growth >= 0 ? "var(--ok,#2e7d32)" : "var(--bad,#d93025)";
    var sign = r.growth >= 0 ? "+" : "";
    html += '<p class="hint trend-growth">'
      + escapeHtml(r.base_year || "") + ' → ' + escapeHtml(r.last_year || "") + ' 变化：'
      + '<b style="color:'+color+'">'+sign+r.growth+'%</b> '
      + escapeHtml(r.label) + ' —— ' + escapeHtml(r.hint) + '</p>'
      + '<p class="hint" style="color:#6b7280">'+escapeHtml(r.note || "")+'</p>';
  }
  if(r.small_sample){
    html += '<p class="hint" style="color:#e8870c">⚠️ 样本量偏小（每年不足 10 篇），增长率仅供参考，建议换更通用的检索词再跑一次。</p>';
  }
  box.innerHTML = html;
}
function syncGenre(){
  var t = $("s5-track").value;
  var map = {basic_science:"sci-journal", "basic-science":"sci-journal"};
  // basic-science 结构检查建议用 sci-journal
  if(t === "basic-science"){ $("s5-genre").value = "sci-journal"; }
  else if(t === "clinical"){ $("s5-genre").value = "clinical"; }
  else if(t === "reporting"){ $("s5-genre").value = "sci-journal"; }
  else if(META.genres[t]){ $("s5-genre").value = t; }
}
/* stage7：体裁默认跟随主线；基础科学/临床用期刊体裁做结构检查 */
function syncGenre7(){
  if(!META) return;
  var t = $("s7-track").value;
  var map = {"basic-science":"sci-journal"};
  $("s7-genre").value = map[t] || (META.genres[t] ? t : "sci-journal");
}

function updateStats(){
  if(!META) return;
  var t = $("s5-track").value;
  var st = META.track_stats[t];
  var el = $("s5-stats");
  if(!st){ el.textContent = ""; return; }
  el.textContent = "该主线：适用规则 " + st.rules + " 条 ｜ 词面自动判定 " + st.detectors + " 条 ｜ 需大模型判读 " + st.manual + " 条";
}

/* ---------- 阶段 5：词面检测 ---------- */
function getReviewText(){ return $("s5-text").value; }

async function runLexical(){
  var track = $("s5-track").value;
  var genre = $("s5-genre").value;
  var text = getReviewText();
  if(!text.trim()){ alert("请先粘贴或上传稿件正文"); return; }
  var btn = $("btnReview");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 检测中…';
  try{
    var r = await api("/api/review/lexical", {text: text, track: track, genre: genre});
    LEXICAL = r;
    renderLexical(r);
    $("resultArea").style.display = "block";
    $("s5-hint").style.display = "block";
  }catch(e){
    alert(e.message);
  }finally{
    btn.disabled = false; btn.textContent = "① 词面检测";
  }
}

function sevLabel(s){ return s==="must"?"硬伤":(s==="should"?"建议":"可选"); }

function renderLexical(r){
  var area = $("resultArea");
  var html = '<div class="card"><h3>① 词面检测结果 · '+(META.tracks[r.track]||r.track)+'</h3>';
  html += '<div class="stat">'
    + '<div class="s total"><div class="v">'+r.defect_count+'</div><div class="l">词面命中</div></div>'
    + '<div class="s must"><div class="v">'+r.must_count+'</div><div class="l">硬伤 must</div></div>'
    + '<div class="s should"><div class="v">'+r.should_count+'</div><div class="l">建议 should</div></div>'
    + '<div class="s nice"><div class="v">'+r.nice_count+'</div><div class="l">可选 nice</div></div>'
    + '</div>';
  html += '<div class="muted">词数 '+r.words+' / 汉字 '+r.cjk_chars+' ｜ 适用规则 '+r.applicable_rules+' 条 ｜ 自动检查 '+r.auto_checked+' 条 ｜ 需大模型判读 '+r.manual_only+' 条 ｜ 不适用 '+r.na.length+' 条</div>';

  // 结构检查
  html += '<h3 style="margin-top:20px">结构自检（'+(META.genres[r.genre]||r.genre)+'）</h3><div>';
  r.required.forEach(function(s){
    var ok = r.sections[s];
    html += '<span class="badge '+(ok?'ok':'no')+'" style="margin:2px 4px 2px 0">'+(ok?'有':'缺')+' '+s+'</span>';
  });
  html += '</div>';
  if(r.sections_extended && r.sections_extended.length){
    var lab = {method:'方法', results:'结果', discussion:'讨论'};
    html += '<div style="color:#6b7280;font-size:12.5px;margin-top:2px">其中 '
      + r.sections_extended.map(function(s){ return lab[s] || s; }).join('、')
      + ' 依据中文小标题（如「数据与研究设计」「实证结果」「结论与讨论」）补充识别，规则命中不受影响</div>';
  }
  if(r.missing.length){ html += '<div class="notice warn">缺失 '+r.missing.length+' 个必需章节：'+r.missing.join('、')+'（若无明确标题，建议补章节标题）</div>'; }

  // 通用质量
  var q = r.quality;
  html += '<h3 style="margin-top:20px">通用质量</h3><div>';
  html += '<span class="badge '+(q.gap?'ok':'no')+'" style="margin:2px 4px 2px 0">'+(q.gap?'有':'缺')+' gap 句（研究缺口）</span>';
  html += '<span class="badge '+(q.contrib?'ok':'no')+'" style="margin:2px 4px 2px 0">'+(q.contrib?'有':'缺')+' 贡献声明</span>';
  html += '<span class="badge '+(q.limitation?'ok':'no')+'" style="margin:2px 4px 2px 0">'+(q.limitation?'有':'缺')+' 局限性</span>';
  if(q.ablation !== undefined){
    html += '<span class="badge '+(q.ablation?'ok':'no')+'" style="margin:2px 4px 2px 0">'+(q.ablation?'有':'缺')+' 消融/对照实验</span>';
  }
  html += '</div>';

  // 词面缺陷
  html += renderRiskGroups(r.defects, "词面可判定的缺陷");
  if(r.thin_text){ html += '<div class="notice warn">文本量偏小（疑似仅摘要），require 类命中多为缺章节所致，不代表真实缺陷。</div>'; }
  html += '<div class="notice info">词面检测只覆盖可自动判定的规则。点击下方「② 深度判读」让大模型逐条判读其余 '+r.manual_only+' 条规则，得到完整审查报告。</div>';
  html += '</div>';
  html += '<div id="deepArea"></div>';
  area.innerHTML = html;
}

function renderRiskGroups(defects, title){
  var must = defects.filter(function(d){ return d.severity === "must"; });
  var should = defects.filter(function(d){ return d.severity === "should"; });
  var nice = defects.filter(function(d){ return d.severity === "nice"; });
  var groups = [
    ["must", must, "硬伤（会被直接拒稿）", "#d93025"],
    ["should", should, "建议（会被要求大修）", "#e8870c"],
    ["nice", nice, "可选（优良实践）", "#8a94a6"]
  ];
  var html = '<h3 style="margin-top:20px">'+title+'</h3>';
  groups.forEach(function(gp){
    html += '<div class="risk-group" style="margin-top:14px">';
    html += '<div class="head"><span class="dot" style="background:'+gp[3]+'"></span>'+gp[2]+'（'+gp[1].length+'）</div>';
    if(gp[1].length === 0){ html += '<div class="muted" style="padding-left:18px">无</div>'; }
    gp[1].forEach(function(d){
      html += '<div class="risk-item"><span class="rid">'+d.id+'</span><span class="pill '+d.severity+'">'+sevLabel(d.severity)+'</span>'
        + '<div class="why">'+(d.reason||d.evidence||"")+'</div>'
        + (d.rule ? '<div class="rule">规则：'+escapeHtml(d.rule)+'</div>' : '')
        + (d.fix ? '<div class="fix">改法：'+escapeHtml(d.fix)+'</div>' : '')
        + (d.source ? '<div class="src">出处：'+escapeHtml(d.source)+'</div>' : '')
        + '</div>';
    });
    html += '</div>';
  });
  return html;
}

/* ---------- 阶段 5：深度判读 ---------- */
async function runDeep(){
  var track = $("s5-track").value;
  var text = getReviewText();
  if(!text.trim()){ alert("请先粘贴或上传稿件正文"); return; }
  var btn = $("btnDeep");
  var deepArea = $("deepArea");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 大模型判读中（约 1~3 分钟）…';
  deepArea.innerHTML = '<div class="card"><div class="loading"><span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span> 正在逐条判读规则，请稍候…</div></div>';
  try{
    var body = llmFields();
    body.text = text; body.track = track;
    var r = await api("/api/review/deep", body);
    SESSIONS[5] = r.session_id;
    renderDeep(r);
  }catch(e){
    deepArea.innerHTML = '<div class="card"><div class="notice warn">'+escapeHtml(e.message)+'</div></div>';
  }finally{
    btn.disabled = false; btn.textContent = "② 深度判读（LLM）";
  }
}

function renderDeep(r){
  var s = r.summary;
  var defects = r.verdicts.filter(function(v){ return v.verdict === "defect"; });
  var html = '<div class="card" style="margin-top:16px"><h3>② 深度判读结果（大模型逐条判读）</h3>';
  html += '<div class="stat">'
    + '<div class="s total"><div class="v">'+s.defects+'</div><div class="l">判读命中</div></div>'
    + '<div class="s must"><div class="v">'+s.must+'</div><div class="l">硬伤 must</div></div>'
    + '<div class="s should"><div class="v">'+s.should+'</div><div class="l">建议 should</div></div>'
    + '<div class="s nice"><div class="v">'+s.nice+'</div><div class="l">可选 nice</div></div>'
    + '</div>';
  html += '<div class="muted">大模型判读 '+s.judged+' 条需人工的规则（不适用 '+(s.na||0)+' 条），分 '+r.batches+' 批完成。</div>';
  if(s.unjudged){
    html += '<div class="notice warn">有 '+s.unjudged+' 条规则模型未返回判读（已重试），<b>未计为通过</b>，请人工核对：'
      + escapeHtml((s.unjudged_ids||[]).join('、'))+'</div>';
  }
  if(s.review){
    var rv = r.verdicts.filter(function(v){ return v.verdict === "review"; });
    html += renderRiskGroups(rv, "分块判读冲突、需人工复核");
  }

  html += renderRiskGroups(defects, "大模型判读出的缺陷");

  // 合并词面 + 大模型，给出完整清单提示
  if(LEXICAL && LEXICAL.defect_count > 0){
    html += '<div class="notice info">完整风险清单 = 上方词面命中 '+LEXICAL.defect_count+' 处 + 本栏大模型命中 '+s.defects+' 处。两者互补，覆盖全部适用规则。</div>';
  }
  html += '</div>';

  // 追问区
  html += buildChatBox(5);

  var deepArea = $("deepArea");
  deepArea.innerHTML = html;
}

/* ---------- 结合审查：脚本初筛 → 模型全文复判 → 深审 ---------- */
async function runCombined(){
  var track = $("s5-track").value;
  var text = getReviewText();
  if(!text.trim()){ alert("请先粘贴或上传稿件正文"); return; }
  var btn = $("btnCombined");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 结合审查中（约 2~5 分钟）…';
  $("resultArea").innerHTML = '<div class="card"><div class="loading"><span class="spin" style="border-color:#0f8a5f;border-top-color:transparent"></span> 脚本初筛 → 模型读全文复判 → 深审其余规则…</div></div>';
  try{
    var body = llmFields();
    body.text = text; body.track = track; body.votes = 3; body.with_deep = true;
    var r = await api("/api/review/combined", body);
    renderCombined(r);
  }catch(e){
    $("resultArea").innerHTML = '<div class="card"><div class="notice warn">'+escapeHtml(e.message)+'</div></div>';
  }finally{
    btn.disabled = false; btn.textContent = "③ 结合审查（推荐）";
  }
}

function renderCombined(r){
  var s = r.summary, f = r.findings;
  var by = function(st){ return f.filter(function(x){ return x.status === st; }); };
  var html = '<div class="card"><h3>③ 结合审查结果 · '+(META.tracks[r.lexical.track]||r.lexical.track)+'</h3>';
  html += '<div class="stat">'
    + '<div class="s must"><div class="v">'+s.confirmed_must+'</div><div class="l">确认硬伤</div></div>'
    + '<div class="s total"><div class="v">'+s.confirmed+'</div><div class="l">确认缺陷</div></div>'
    + '<div class="s should"><div class="v">'+(s.review+s.unjudged)+'</div><div class="l">需人工</div></div>'
    + '<div class="s nice"><div class="v">'+(s.dismissed_not_applicable+s.dismissed_passed)+'</div><div class="l">已剔除脚本误报</div></div>'
    + '</div>';
  html += '<div class="muted">脚本命中 '+r.lexical.defect_count+' 处，其中硬伤经大模型读全文复判（'+r.recheck.votes+' 次多数票，共 '+r.recheck.calls+' 次调用）。</div>';

  html += renderRiskGroups(by("confirmed"), "确认缺陷（脚本命中且复判确认 / 模型深审发现）");
  var rev = by("review").concat(by("unjudged"));
  if(rev.length){ html += renderRiskGroups(rev, "需人工复核（票数不过半 / 分块冲突 / 未判读）"); }
  var so = by("script");
  if(so.length){ html += renderRiskGroups(so, "脚本命中（非硬伤，未复判）"); }

  var dis = by("not_applicable").concat(by("passed"));
  if(dis.length){
    html += '<details style="margin-top:16px"><summary>已被复判剔除的脚本命中（'+dis.length+'）</summary>';
    dis.forEach(function(d){
      var why = d.status === "not_applicable" ? "规则不适用本文设计" : "要素已出现（脚本未识别写法）";
      html += '<div class="risk-item"><span class="rid">'+d.id+'</span><span class="pill nice">'+why+'</span>'
        + '<div class="why">'+escapeHtml((d.recheck && d.recheck.evidence)||"")+'</div>'
        + '<div class="src">投票：'+escapeHtml(((d.recheck && d.recheck.votes)||[]).join(' / '))+'</div></div>';
    });
    html += '</details>';
  }
  html += '<div class="notice info">依据：40 篇真实论文实测，脚本硬伤单独精确率约 34%；读全文复判后真缺陷保留 17/17、误报剔除 33/33（标注存在偏差风险，仍建议人工抽查确认硬伤）。</div>';
  html += '</div>';
  $("resultArea").innerHTML = html;
}

/* ---------- 结果卡：渲染 + 导出（md / docx / tex） ---------- */
var RESULTS = {};   // key -> 原始 markdown，导出时用原文，避免二次转换失真

var RESULT_TITLES = {
  "1": "选题定位", "1-radar": "选题雷达评估", "2": "研究设计评审",
  "3": "初稿写作引导", "4": "引用格式检查", "6": "投稿与返修", "7": "一键成稿"
};

function resultHead(){
  return '<div class="card-head"><span class="card-title">生成结果</span>'
    + '<div class="exp-wrap">'
    + '<button class="btn small ghost exp-btn" type="button">导出 ▾</button>'
    + '<div class="exp-menu">'
    + '<button type="button" data-fmt="md">Markdown（.md）</button>'
    + '<button type="button" data-fmt="docx">Word（.docx）</button>'
    + '<button type="button" data-fmt="tex">LaTeX（Overleaf）</button>'
    + '</div></div></div>';
}

function renderResult(out, key, text, extraHtml, metaHtml){
  RESULTS[key] = text || "";
  out.innerHTML = '<div class="card mt">' + resultHead()
    + (key === "1-radar" ? '<div class="copy-bar">把选定题目复制到「一键成稿 → 已定题目」：'
        + '<button class="btn small ghost" type="button" data-copy-title="' + key + '">复制题目</button>'
        + '<button class="btn small ghost" type="button" data-copy="' + key + '">复制全文</button></div>' : "")
    + (metaHtml ? '<div class="result-meta">' + metaHtml + '</div>' : "")
    + '<div class="result-body"></div></div>' + (extraHtml || "");
  var body = out.querySelector(".result-body");
  body.innerHTML = md(RESULTS[key]);
  enhance(body);
  bindExportMenu(out, key);
  var cb = out.querySelector("[data-copy]");
  if(cb) cb.addEventListener("click", function(){ copyResult(cb.getAttribute("data-copy")); });
  var ct = out.querySelector("[data-copy-title]");
  if(ct) ct.addEventListener("click", function(){ copyTitle(ct.getAttribute("data-copy-title")); });
}

/* 从雷达结果里挑出第一个候选的英文题名；挑不到就退回复制全文 */
function pickTitle(text){
  var lines = String(text || "").split(/\r?\n/);
  var re = /^\s*(?:\*\*)?\s*(?:[1１一]\s*[.、)）]|题目\s*1\s*[:：]?)\s*(.+)$/;
  var i, m, s;
  for(i = 0; i < lines.length; i++){
    m = lines[i].match(re);
    if(!m) continue;
    s = m[1].replace(/[*_`]/g, "").trim();
    s = s.split(/[（(]/)[0].trim();          // 去掉「（中文解释）」
    if(/[A-Za-z]{4,}/.test(s) && s.split(/\s+/).length >= 4) return s.replace(/[。；;]$/, "");
  }
  return "";
}

function copyTitle(key){
  var t = pickTitle(RESULTS[key] || "");
  if(!t){ copyResult(key); return; }
  var done = function(ok){
    var el = document.querySelector(".copy-bar");
    if(!el) return;
    var old = el.querySelector(".copy-ok");
    if(old) old.remove();
    el.insertAdjacentHTML("afterbegin", '<span class="copy-ok">'
      + (ok ? "已复制题目：" + escapeHtml(t.slice(0, 60)) + (t.length > 60 ? "…" : "")
            : "复制失败，请手动选中") + '</span>');
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).then(function(){ done(true); }, function(){ done(false); });
  }else{
    done(false);
  }
}

function copyResult(key){
  var t = RESULTS[key] || "";
  if(!t) return;
  var done = function(ok){
    var el = document.querySelector(".copy-bar");
    if(el) el.insertAdjacentHTML("afterbegin",
      '<span class="copy-ok">' + (ok ? "已复制，去「一键成稿」粘贴" : "复制失败，请手动选中") + '</span>');
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).then(function(){ done(true); }, function(){ done(false); });
  }else{
    done(false);
  }
}

function bindExportMenu(scope, key){
  var btn = scope.querySelector(".exp-btn");
  var menu = scope.querySelector(".exp-menu");
  if (!btn || !menu) return;
  btn.addEventListener("click", function(e){
    e.stopPropagation();
    var wasOn = menu.classList.contains("on");
    document.querySelectorAll(".exp-menu.on").forEach(function(m){ m.classList.remove("on"); });
    if (!wasOn) menu.classList.add("on");
  });
  menu.querySelectorAll("button[data-fmt]").forEach(function(b){
    b.addEventListener("click", function(e){
      e.stopPropagation();
      menu.classList.remove("on");
      exportResult(key, b.getAttribute("data-fmt"));
    });
  });
}

document.addEventListener("click", function(){
  document.querySelectorAll(".exp-menu.on").forEach(function(m){ m.classList.remove("on"); });
});

function exportName(key){
  return "AW_" + (RESULT_TITLES[key] || "结果");
}

function saveBlob(blob, name){
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}

// 一键成稿的结果键，导出时须带 AI 水印警示（与后端 AI_WATERMARK_MD 保持一致）
var AI_RESULT_KEYS = {"7": 1};

var AI_WATERMARK_MD = [
  "> ⚠️ **AI 生成内容警示：本文件禁止直接用于投稿、交稿或发表。**",
  ">",
  "> 本文全部文本由 AI 生成，导出或转存的副本可能含可见或不可见的 AI 标记",
  "> （水印 / 隐写标识 / 元数据）。带标记的稿件投稿会被期刊 AI 检测判为代写，",
  "> 且隐写标记**无法通过转 PDF、截图、复制粘贴去除**。",
  ">",
  "> 正确用法：仅作写作骨架。逐段用自己的语言重写；`[TBD: ...]` 填真实数据；",
  "> `[CITE: ...]` 换成可核实文献；最终稿必须是你自己重新写出的文本。",
  "",
  ""
].join("\n");

async function exportResult(key, fmt){
  var text = RESULTS[key] || "";
  if (!text.trim()){ alert("暂无可导出的内容"); return; }
  var ai = !!AI_RESULT_KEYS[key];
  var body = ai ? (AI_WATERMARK_MD + text) : text;
  var name = exportName(key);
  if (fmt === "md"){
    saveBlob(new Blob([body], {type: "text/markdown;charset=utf-8"}), name + ".md");
    return;
  }
  try{
    var res = await fetch("/api/export", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({markdown: text, format: fmt, title: name, ai_generated: ai})
    });
    if (!res.ok){
      var d = await res.json().catch(function(){ return {}; });
      throw new Error(d.detail || ("导出失败（HTTP " + res.status + "）"));
    }
    // LaTeX 含图片时后端返回 Overleaf zip，文件名以响应头为准
    saveBlob(await res.blob(), filenameFromResponse(res, name + "." + fmt));
  }catch(e){ alert(e.message); }
}

function filenameFromResponse(res, fallback){
  var cd = res.headers.get("Content-Disposition") || "";
  var m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (m){
    try{ return decodeURIComponent(m[1]); }catch(e){}
  }
  return fallback;
}

/* ---------- 六阶段工作流（1/2/3/4/6） ---------- */
async function runWorkflow(stage, mode){
  var params = collectStageParams(stage, mode);
  if(params === null) return;
  var key = mode ? (stage + "-" + mode) : String(stage);
  var out = $(mode ? ("out" + stage + "-" + mode) : ("out" + stage));
  out.innerHTML = '<div class="loading"><span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span> 正在生成，请稍候…</div>';
  try{
    var body = llmFields();
    body.stage = stage; body.params = params;
    var r = await api("/api/workflow", body);
    SESSIONS[key] = r.session_id;
    // 选题（含可选雷达）不挂追问框：追问是审查场景的交互，选题结果以导出交付为主
    var extra = (stage === 1) ? "" : buildChatBox(key);
    // 雷达结果加一行"本次依据"，让换了题目却看不出差别的情况一眼可辨
    var meta = (stage === 1 && mode === "radar") ? radarMeta(params) : "";
    renderResult(out, key, r.answer, extra, meta);
  }catch(e){
    out.innerHTML = '<div class="card mt"><div class="notice warn">'+escapeHtml(e.message)+'</div></div>';
  }
}

function radarMeta(p){
  var lv = {bsc: "本科毕设", master: "硕士论文", phd: "博士论文", journal: "期刊投稿", general: "一般性研究"}[p.level] || p.level;
  var bits = ["研究方向「" + escapeHtml(p.dir || "") + "」"];
  if(p.query && p.query !== p.dir) bits.push("检索词「" + escapeHtml(p.query) + "」");
  bits.push("层级 " + escapeHtml(lv || ""));
  if(p.trend){
    bits.push("趋势 " + p.trend.split(",").length + " 年（" + escapeHtml(p.query || p.dir || "") + "）");
  }else{
    bits.push("未使用趋势数据");
  }
  if(p.trend_stale) bits.push("旧趋势「" + escapeHtml(p.trend_stale) + "」已忽略，请重新跑趋势");
  var t = new Date();
  var pad = function(n){ return ("0" + n).slice(-2); };
  bits.push("生成于 " + pad(t.getHours()) + ":" + pad(t.getMinutes()) + ":" + pad(t.getSeconds()));
  return bits.join(" · ");
}

function collectStageParams(stage, mode){
  if(stage === 1){
    var dir = $("s1-dir").value.trim();
    if(!dir){ alert("请填写研究方向"); return null; }
    // 期刊：优先自定义输入，否则取下拉选择
    var venueSel = $("s1-venue").value;
    var venueCustom = $("s1-venue-custom").value.trim();
    var venue = venueCustom || venueSel;
    // 常规选题引导：参数与原版一致（track / dir / venue）
    if(mode !== "radar"){
      return {track: $("s1-track").value, dir: dir, venue: venue};
    }
    // 选题雷达（选题常规一步）：额外带层级、检索词与趋势数据
    var query = radarQuery();
    var trend = "";
    if(TREND_DATA && TREND_DATA.groups && TREND_DATA.groups.length && !trendIsStale()){
      trend = TREND_DATA.groups.map(function(g){ return g.year + ":" + g.count; }).join(", ");
    }
    return {
      track: $("s1-track").value,
      dir: dir,
      venue: venue,
      mode: "radar",
      level: $("s1-level").value,
      query: query,
      trend: trend,
      trend_stale: trendIsStale() ? TREND_QUERY : ""
    };
  }
  if(stage === 2){
    var design = $("s2-design").value.trim();
    if(!design){ alert("请填写研究设计描述"); return null; }
    return {track: $("s2-track").value, design: design};
  }
  if(stage === 3){
    return {track: $("s3-track").value, section: $("s3-section").value, draft: $("s3-draft").value.trim()};
  }
  if(stage === 4){
    return {style: $("s4-style").value, refs: $("s4-refs").value.trim()};
  }
  if(stage === 6){
    var mode = $("s6-mode").value;
    var comments = $("s6-comments").value.trim();
    if(mode === "revision" && !comments){ alert("返修模式请粘贴审稿意见"); return null; }
    return {track: $("s6-track").value, mode: mode, comments: comments};
  }
  return {};
}

/* ---------- 多轮追问 ---------- */
function buildChatBox(key){
  var k = String(key);
  var arg = "'" + k + "'";
  return '<div class="chat mt">'
    + '<div class="chat-history" id="chatHist-'+k+'"></div>'
    + '<div class="chat-input">'
    + '<input type="text" id="chatInput-'+k+'" placeholder="继续追问，例如：为什么判这条？怎么改？" onkeydown="if(event.key===\'Enter\')sendChat('+arg+')">'
    + '<button class="btn" onclick="sendChat('+arg+')">发送</button>'
    + '</div></div>';
}

async function sendChat(stage){
  var input = $("chatInput-" + stage);
  var msg = input.value.trim();
  if(!msg) return;
  var hist = $("chatHist-" + stage);
  hist.innerHTML += '<div class="msg user">'+escapeHtml(msg)+'</div>';
  input.value = "";
  var thinking = document.createElement("div");
  thinking.className = "msg ai";
  thinking.innerHTML = '<span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span> 思考中…';
  hist.appendChild(thinking);
  hist.scrollTop = hist.scrollHeight;
  try{
    var body = llmFields();
    body.session_id = SESSIONS[stage] || "";
    body.message = msg;
    var r = await api("/api/chat", body);
    if(r.session_id) SESSIONS[stage] = r.session_id;
    thinking.innerHTML = '<div class="md"></div>';
    var box = thinking.firstChild;
    box.innerHTML = md(r.answer);
    enhance(box);
  }catch(e){
    thinking.innerHTML = '<span style="color:#d93025">'+escapeHtml(e.message)+'</span>';
  }
  hist.scrollTop = hist.scrollHeight;
}

/* ---------- 样稿 / 上传 ---------- */
function loadSample(grade){
  var t = $("s5-track").value || "quant";
  var samples = {
    "quant": {good:"qnt_good_1.md", bad:"qnt_bad_1.md"},
    "qualitative": {good:"qlt_good_1.md", bad:"qlt_bad_1.md"},
    "clinical": {good:"cln_good_1.md", bad:"cln_bad_1.md"},
    "predictive": {good:"prd_good_1.md", bad:"prd_bad_1.md"}
  };
  var pick = samples[t] || samples["quant"];
  var name = grade === "good" ? pick.good : pick.bad;
  fetch("samples/" + name).then(function(r){ return r.text(); }).then(function(txt){
    $("s5-text").value = txt;
  }).catch(function(){ alert("样稿未内置，请直接粘贴你的稿件"); });
}
function clearText(){
  $("s5-text").value = "";
  $("resultArea").style.display = "none";
  LEXICAL = null;
  s5Note("");
}

/* ---------- 稿件上传：Word / Markdown / LaTeX / PDF / 剪贴板 ---------- */
var DROP_IDLE = "点击或拖拽上传 Word(.docx/.doc) / Markdown / LaTeX / PDF / TXT，或直接在下方粘贴全文（表格、公式、图片会一并解析）";
var IMG_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;

function s5Note(msg, isErr){
  var el = $("s5-filenote");
  if(!el) return;
  el.textContent = msg || "";
  el.style.display = msg ? "block" : "none";
  el.style.color = isErr ? "#d93025" : "";
}

function initUpload(){
  var drop = $("dropZone");
  var input = $("fileInput");
  var ta = $("s5-text");
  if(!drop || !input || !ta) return;

  function setDrop(html, busy){
    drop.innerHTML = html;
    drop.classList.toggle("busy", !!busy);
  }
  function appendMarkdown(text){
    var cur = ta.value.trim();
    ta.value = cur ? (cur + "\n\n" + text) : text;
  }

  async function handleFile(f){
    if(!f) return;
    if((f.type && f.type.indexOf("image/") === 0) || IMG_EXT.test(f.name || "")){
      await insertImage(f);
      return;
    }
    setDrop('<span class="spin"></span> 正在解析 ' + escapeHtml(f.name) + ' …', true);
    try{
      var fd = new FormData();
      fd.append("file", f);
      var res = await fetch("/api/ingest", {method: "POST", body: fd});
      var data = await res.json().catch(function(){ return {}; });
      if(!res.ok) throw new Error(data.detail || ("解析失败（HTTP " + res.status + "）"));
      appendMarkdown(data.markdown || "");
      var bits = ["已解析 " + (data.filename || f.name) + "（" + (data.format || "file") + "）"];
      if(data.images && data.images.length) bits.push("抽取图片 " + data.images.length + " 张");
      (data.warnings || []).forEach(function(w){ bits.push(w); });
      s5Note(bits.join(" ｜ "));
    }catch(e){
      s5Note(e.message, true);
      alert(e.message);
    }finally{
      setDrop(DROP_IDLE, false);
      input.value = "";
    }
  }

  async function insertImage(f){
    if(!f) return;
    try{
      var fd = new FormData();
      fd.append("file", f, f.name || "paste.png");
      var res = await fetch("/api/upload/image", {method: "POST", body: fd});
      var data = await res.json().catch(function(){ return {}; });
      if(!res.ok) throw new Error(data.detail || "图片上传失败");
      appendMarkdown("![](" + data.url + ")");
      s5Note("已插入图片：" + data.url);
    }catch(e){
      s5Note(e.message, true);
      alert(e.message);
    }
  }

  async function convertHtml(html, plain){
    var start = ta.selectionStart, end = ta.selectionEnd;
    try{
      var res = await fetch("/api/ingest/html", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({html: html})
      });
      var data = await res.json().catch(function(){ return {}; });
      if(!res.ok) throw new Error(data.detail || "转换失败");
      var ins = data.markdown || plain || "";
      ta.value = ta.value.slice(0, start) + ins + ta.value.slice(end);
      ta.selectionStart = ta.selectionEnd = start + ins.length;
      s5Note("已把粘贴内容转为 Markdown（表格 / 粗体 / 上下标已保留）");
    }catch(err){
      ta.value = ta.value.slice(0, start) + (plain || "") + ta.value.slice(end);
      s5Note("粘贴内容转换失败，已按纯文本插入：" + err.message, true);
    }
  }

  drop.addEventListener("click", function(){ input.click(); });
  input.addEventListener("change", function(){ handleFile(input.files[0]); });

  ["dragover","dragenter"].forEach(function(ev){
    drop.addEventListener(ev, function(e){ e.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave","drop"].forEach(function(ev){
    drop.addEventListener(ev, function(e){ e.preventDefault(); drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function(e){
    var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    handleFile(f);
  });

  // 粘贴：截图直接落图；Word/网页表格转 Markdown 表格；其余走浏览器默认
  ta.addEventListener("paste", function(e){
    var cd = e.clipboardData;
    if(!cd) return;
    var items = cd.items || [];
    for(var i = 0; i < items.length; i++){
      if(items[i].type && items[i].type.indexOf("image/") === 0){
        e.preventDefault();
        insertImage(items[i].getAsFile());
        return;
      }
    }
    var html = cd.getData("text/html");
    var plain = cd.getData("text/plain");
    if(html && /<table|<img|oMath|<math|<sup|<sub|<strong/i.test(html)){
      e.preventDefault();
      convertHtml(html, plain);
    }
  });
}

/* ---------- 阶段 7：一键成稿（学术小白） ---------- */
var OS_JOB = null;      // 当前任务号
var OS_TIMER = null;    // 轮询定时器
var OS_BUSY = false;
var OS_SOURCES = null;       // 页面已查到的数据源线索（跑批时当缓存用，避免重复联网）
var OS_SOURCES_TOPIC = "";   // 该结果对应的题目；题目变了就作废

// AI 水印警示写进成稿结果区——用户真正可能拿去用的地方，不能只写在页面顶部。
// 隐写标记清不掉：转存、截图、复制粘贴都去不掉，所以只能明令禁止直接使用。
var AI_WATERMARK_HTML = '<div class="notice err" style="margin-bottom:12px">'
  + '<b>⚠️ 严禁直接使用这份成稿：AI 生成内容带水印，且无法清除。</b><br>'
  + '以上文本为 <b>AI 生成内容</b>，平台导出或转存的副本可能含可见/不可见的 AI 标记（水印、隐写标识、元数据）。'
  + '带标记的稿件投稿会被判为 AI 代写，转 PDF、截图、复制粘贴均不能去除标记。<br>'
  + '<b>只当写作骨架用</b>：逐段用自己的语言重写，<code>[TBD: ...]</code> 填真实数据，'
  + '<code>[CITE: ...]</code> 换成可核实文献；最终稿必须是你自己写出的文本。</div>';

function osCfg(){
  var title = $("s7-title").value.trim();
  var status = $("s7-data").value;
  // 页面已查过就带上（只留必要字段，限 10 条）；题目改过则视为失效
  var cached = [];
  if((status === "find" || status === "demo") && OS_SOURCES && OS_SOURCES_TOPIC === title){
    cached = (OS_SOURCES.items || []).slice(0, 10);
  }
  return {
    track: $("s7-track").value,
    genre: $("s7-genre").value,
    venue: $("s7-venue").value.trim(),
    level: $("s7-level").value,
    language: $("s7-lang").value,
    citation: $("s7-citation").value,
    words: parseInt($("s7-words").value, 10) || 7000,
    data: status,
    // 题目即研究方向：不再单独收「研究方向」与「英文检索词」，检索式由模型从题目生成
    title: title,
    dataset_id: OS_DATA ? OS_DATA.id : "",
    sources: cached,
    recheck: !!($("s7-recheck") && $("s7-recheck").checked)
  };
}

/* ---------- 数据文件：只读结构 ---------- */

var OS_DATA = null;   // 当前数据画像（bundle；不含原始行）

var LAYOUT_LABEL = {
  "panel": "面板（实体 × 时间）", "time-series": "时间序列", "cross-section": "截面",
  "text-corpus": "文本语料", "table": "普通表格"
};
var TYPE_LABEL = {numeric:"数值", binary:"二值", year:"年份", date:"日期",
                  text:"文本", "text-long":"长文本", id:"ID"};

function fillPromo(){
  var box = $("osPromo");
  if(box) box.innerHTML = promoHtml("填好地址就能用，不用换客户端。");
}

function osPickData(){
  var input = $("s7-datafile");
  if(!input) return;
  input.value = "";
  input.click();
}

async function osUploadData(fileList){
  var files = Array.prototype.slice.call(fileList || []);
  if(!files.length) return;
  var hint = $("osDataProfile");
  hint.innerHTML = '<div class="hint"><span class="spin"></span> 正在解析 '
    + files.length + ' 个文件…</div>';
  // 换文件前先删旧画像，否则 _datasets 里会堆孤儿 JSON
  if(OS_DATA && OS_DATA.id){
    try{ await api("/api/oneshot/data/delete", {id: OS_DATA.id}); }catch(e){}
  }
  try{
    var fd = new FormData();
    files.forEach(function(f){ fd.append("file", f); });
    var res = await fetch("/api/oneshot/data", {method: "POST", body: fd});
    var data = await res.json().catch(function(){ return {}; });
    if(!res.ok) throw new Error(data.detail || ("解析失败（HTTP " + res.status + "）"));
    OS_DATA = data;
    renderDataProfile(data);
  }catch(e){
    OS_DATA = null;
    hint.innerHTML = '<div class="notice warn" style="margin-top:8px">' + escapeHtml(e.message) + '</div>';
  }
}

function dataPartHtml(p, idx){
  var cols = p.columns || [];
  var tag = p.role || (idx === 0 ? "主表" : "附表 " + idx);
  var html = '<div class="data-part">'
    + '<div class="data-head"><b>' + escapeHtml(tag) + ' · ' + escapeHtml(p.filename || "数据文件") + '</b>'
    + '<span class="muted">' + (p.rows || 0) + ' 行 × ' + (p.cols || 0) + ' 列'
    + (p.truncated ? "（只扫描前 " + (p.scanned || 0) + " 行）" : "") + '</span></div>';
  html += '<div class="data-vars">' + cols.slice(0, 24).map(function(c){
      var t = TYPE_LABEL[c.type] || c.type;
      var miss = c.missing > 0 ? ' · 缺 ' + Math.round(c.missing * 100) + '%' : "";
      return '<span class="dvar"><b>' + escapeHtml(c.name) + '</b><i>' + t + miss + '</i></span>';
    }).join("") + (cols.length > 24 ? '<span class="dvar">…另 ' + (cols.length - 24) + ' 列</span>' : "")
    + '</div></div>';
  return html;
}

function renderDataProfile(p){
  if(!p){ $("osDataProfile").innerHTML = ""; $("btnOsDataClear").style.display = "none"; return; }
  var parts = (p.parts && p.parts.length) ? p.parts : [p];
  var html = '<div class="data-card">';

  if(parts.length > 1){
    html += '<div class="data-head"><b>数据文件 ' + parts.length + ' 份</b>'
      + '<span class="muted">' + (p.rows || 0) + ' 行合计（主表判定用最大的那份）</span></div>';
  }
  html += parts.map(dataPartHtml).join("");

  var st = p.structure || {};
  if(st.layout){
    var bits = ['<b>' + escapeHtml(LAYOUT_LABEL[st.layout] || st.layout) + '</b>'];
    if(st.entity) bits.push("实体 " + escapeHtml(st.entity) + "（" + (st.n_entities || 0) + "）");
    if(st.time) bits.push("时间 " + escapeHtml(st.time) + "（" + (st.n_periods || 0) + " 期）");
    if(st.balanced === false) bits.push("非平衡");
    html += '<div class="data-shape">结构：' + bits.join(" · ") + '</div>';
  }
  var sigs = p.signals || [];
  if(sigs.length){
    html += '<div class="data-sigs">' + sigs.slice(0, 4).map(function(s){
      return '<span class="dvar" title="' + escapeHtml(s.evidence || "") + '">'
        + escapeHtml(s.label) + '</span>';
    }).join("") + '</div>';
  }

  var sug = p.suggest || {};
  if(sug.track){
    var cur = $("s7-track") ? $("s7-track").value : "";
    var same = (sug.track === cur);
    var label = (META && META.tracks && META.tracks[sug.track]) || sug.track;
    html += '<div class="data-suggest' + (same ? "" : " diff") + '">'
      + '<span>建议学科主线：<b>' + escapeHtml(label) + '</b>'
      + (sug.confidence === "low" ? "（把握不大，自行判断）" : "")
      + '</span>'
      + (same ? '<span class="badge ok">与当前选择一致</span>'
              : '<button class="btn small" onclick="osApplyTrack(\'' + escapeHtml(sug.track) + '\')">用这个主线</button>')
      + '</div>';
    if(sug.reasons && sug.reasons.length){
      html += '<div class="hint">依据：' + sug.reasons.map(escapeHtml).join("；") + '</div>';
    }
  }

  // 数据体检：只报「按现有数据哪些分析做不了」，不给模拟值
  var gap = p.gap || null;
  if(gap && gap.items && gap.items.length){
    var bad = gap.items.filter(function(it){ return it.status !== "pass"; });
    if(bad.length){
      html += '<div class="data-gap">' + bad.map(function(it){
        var cls = it.status === "risk" ? "no" : "warn";
        var lab = it.status === "risk" ? "做不了" : "注意";
        return '<div class="gap-row"><span class="badge ' + cls + '">' + lab + '</span>'
          + '<b>' + escapeHtml(it.label) + '</b> ' + escapeHtml(it.detail)
          + (it.fix ? '<div class="hint">怎么办：' + escapeHtml(it.fix) + '</div>' : '')
          + '</div>';
      }).join("") + '</div>';
      if(gap.counts && gap.counts.risk){
        html += '<div class="hint">以上是结构判断，系统不插补、不生成模拟值。'
          + '缺的列可点「查可用数据源」找公开来源。</div>';
      }
    }else{
      html += '<div class="hint">数据体检：样本量、可分析变量、缺失率、结构深度均通过。</div>';
    }
  }

  var warns = p.warnings || [];
  if(warns.length){
    html += '<div class="notice info" style="margin-top:6px">'
      + warns.slice(0, 4).map(escapeHtml).join("；") + '</div>';
  }
  var ds = $("s7-data");
  if(ds && ds.value === "no"){
    html += '<div class="notice warn" style="margin-top:6px">'
      + '已上传数据，但「数据状态」仍是「无数据」——结果章只会写表格骨架与占位。'
      + '如果这就是你的真实数据，把「数据状态」改成「已有真实数据」再开始。</div>';
  }else if(ds && ds.value === "find"){
    html += '<div class="notice info" style="margin-top:6px">'
      + '已选「帮我找数据源」：第 3 步会给出可核实的数据源链接与取法，'
      + '并<b>代下载白名单公开源</b>（世行 / Zenodo / Dataverse）到 _sources/。'
      + '结果章仍按表格骨架 + <code>[TBD: ...]</code> 写；下载文件<b>未经解析与核对</b>，'
      + '请先检查口径再上传。缺的列会按下面的体检结果定向检索。</div>';
  }else if(ds && ds.value === "demo"){
    html += '<div class="notice info" style="margin-top:6px">'
      + '已选「演示模式」：正文仍用 <code>[TBD: ...]</code> 占位，'
      + '另产一份 <b>demo_preview.md</b>（模拟值仅排版预览，标注 SIMULATED，不可投稿）。'
      + '同样会代下载白名单公开源。</div>';
  }
  html += '<div class="hint">只读取列名、类型、缺失率与汇总统计；<b>行级数据不会发给模型</b>，'
    + '也不保存在服务端（只存这份画像）。</div>';
  html += '</div>';
  $("osDataProfile").innerHTML = html;
  $("btnOsDataClear").style.display = "";
}

/** 采纳数据给出的主线建议：改下拉 + 同步体裁，再重绘一次 */
function osApplyTrack(track){
  if(!track) return;
  var sel = $("s7-track");
  if(!sel) return;
  sel.value = track;
  if(typeof syncGenre7 === "function") syncGenre7();
  if(OS_DATA) OS_DATA.__applied = track;
  renderDataProfile(OS_DATA);
}

async function osClearData(){
  if(OS_DATA && OS_DATA.id){
    try{ await api("/api/oneshot/data/delete", {id: OS_DATA.id}); }catch(e){}
  }
  OS_DATA = null;
  renderDataProfile(null);
  var box = $("osDataSources");
  if(box) box.innerHTML = "";
}

/* ---------- 数据不全时：查可公开获取的数据源（只给线索，不落数字） ---------- */
async function osFindSources(){
  var box = $("osDataSources");
  var btn = $("btnOsSources");
  var titleEl = $("s7-title");
  var topic = (titleEl && titleEl.value || "").trim();
  if(!topic){
    box.innerHTML = '<div class="notice warn" style="margin-top:8px">'
      + '先填「已定题目」再查：数据源要按题目主题匹配，没有题目只能给通用入口。</div>';
    return;
  }
  var old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "检索中…";
  box.innerHTML = '<div class="hint" style="margin-top:8px">'
    + '正在检索 Zenodo / Harvard Dataverse，并按题目匹配世行指标…</div>';
  try{
    var body = llmFields();
    body.topic = topic;
    body.need = [];
    body.dataset_id = (OS_DATA && OS_DATA.id) || null;
    var r = await api("/api/oneshot/data/sources", body);
    OS_SOURCES = r;
    OS_SOURCES_TOPIC = topic;
    box.innerHTML = renderSources(r);
  }catch(e){
    box.innerHTML = '<div class="notice warn" style="margin-top:8px">检索失败：'
      + escapeHtml(e.message || String(e)) + '</div>';
  }finally{
    btn.disabled = false;
    btn.textContent = old;
  }
}

function renderSources(r){
  var items = r.items || [];
  var html = '<div class="data-card"><div class="data-head"><b>可用数据源线索</b>'
    + '<span class="muted">检索命中 ' + ((r.counts && r.counts.repo) || 0) + ' 条 · 世行指标 '
    + ((r.counts && r.counts.wb) || 0) + ' 条 · 手工入口 ' + ((r.counts && r.counts.manual) || 0) + ' 条</span></div>';
  if(r.terms && r.terms.length){
    html += '<div class="hint">检索词：' + r.terms.map(escapeHtml).join("；") + '</div>';
  }
  if(r.gap_note){ html += '<div class="notice warn">' + escapeHtml(r.gap_note) + '</div>'; }
  if(!items.length){
    html += '<div class="notice info">没有命中。可在题目里补上主题关键词后重试，'
      + '或直接用下面的人工入口取数。</div>';
  }
  html += '<div class="src-list">' + items.map(function(it){
    return '<div class="src-item">'
      + '<div><a href="' + escapeHtml(it.url || "#") + '" target="_blank" rel="noopener noreferrer">'
      + escapeHtml(it.name || "未命名") + '</a>'
      + ' <span class="badge info">' + escapeHtml(it.kind || "") + '</span>'
      + ' <span class="muted">' + escapeHtml(it.access || "") + '</span></div>'
      + (it.why ? '<div class="hint">' + escapeHtml(it.why) + '</div>' : '')
      + (it.how ? '<div class="hint">怎么取：' + escapeHtml(it.how) + '</div>' : '')
      + (it.cite ? '<div class="hint">引用：' + escapeHtml(it.cite) + '</div>' : '')
      + '</div>';
  }).join("") + '</div>';
  (r.notes || []).forEach(function(n){
    html += '<div class="hint">' + escapeHtml(n) + '</div>';
  });
  if(r.disclaimer){
    html += '<div class="notice info">' + escapeHtml(r.disclaimer) + '</div>';
  }
  var ds = $("s7-data");
  if(ds && (ds.value === "find" || ds.value === "demo")){
    html += '<div class="notice info">选中的「帮我找数据源 / 演示模式」会在开始成稿时'
      + '<b>自动代下载</b>上述白名单公开源（世行 / Zenodo / Dataverse）到任务目录的 _sources/，'
      + '文件不解析、不核对口径，请下载后自行检查再上传。</div>';
  }
  html += '</div>';
  return html;
}

function osResetButtons(){
  var b = $("btnOsStart");
  b.disabled = false; b.textContent = "② 开始一键成稿";
  $("btnOsCancel").style.display = "none";
}

async function osGate(){
  var cfg = osCfg();
  if(!cfg.title){ alert("请先填写「已定题目」：去选题页用雷达定题，点「复制题目」再粘过来"); return; }
  var btn = $("btnOsGate");
  btn.disabled = true; btn.innerHTML = '<span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span> 检查中…';
  try{
    var r = await api("/api/oneshot/gate", {cfg: cfg});
    renderOsGate(r);
  }catch(e){
    $("osGate").innerHTML = '<div class="card mt"><div class="notice warn">'+escapeHtml(e.message)+'</div></div>';
  }finally{
    btn.disabled = false; btn.textContent = "① 前置条件检查";
  }
}

function renderOsGate(r){
  var html = '<div class="card mt"><div class="card-head"><span class="card-title">前置条件检查</span>'
    + '<span class="badge '+(r.ok?"ok":"no")+'">'+(r.ok?"可以开始":"有阻断项")+'</span></div>';
  html += '<div class="table-wrap"><table><thead><tr><th>检查项</th><th>结论</th><th>说明</th></tr></thead><tbody>';
  (r.checks||[]).forEach(function(c){
    var cls = c.status === "pass" ? "ok" : (c.status === "warn" ? "warn" : "no");
    var lab = c.status === "pass" ? "通过" : (c.status === "warn" ? "注意" : "阻断");
    html += '<tr><td>'+escapeHtml(c.label)+'</td><td><span class="badge '+cls+'">'+lab+'</span></td>'
      + '<td>'+escapeHtml(c.detail)+'</td></tr>';
  });
  html += '</tbody></table></div>';
  if(r.fatal && r.fatal.length){
    html += '<div class="notice warn">先解决：'+r.fatal.map(escapeHtml).join("；")+'</div>';
  }
  var plan = r.plan || [];
  if(plan.length){
    var total = plan.reduce(function(a,s){ return a + s.words; }, 0);
    html += '<h3 style="margin-top:18px">章节与字数计划</h3>'
      + '<div class="table-wrap"><table><thead><tr><th>#</th><th>章节</th><th>目标字数</th></tr></thead><tbody>';
    plan.forEach(function(s,i){
      html += '<tr><td>'+(i+1)+'</td><td>'+escapeHtml(s.heading)+'</td><td>'+s.words+'</td></tr>';
    });
    html += '</tbody><tfoot><tr><td></td><td><b>正文合计</b></td><td><b>'+total+'</b></td></tr></tfoot></table></div>';
  }
  html += '</div>';
  $("osGate").innerHTML = html;
}

async function osStart(){
  var cfg = osCfg();
  if(!cfg.title){ alert("请先填写「已定题目」：去选题页用雷达定题，点「复制题目」再粘过来"); return; }
  if(OS_BUSY) return;
  OS_BUSY = true;
  clearTimeout(OS_TIMER);
  var body = llmFields();
  body.cfg = cfg;
  var b = $("btnOsStart");
  b.disabled = true; b.innerHTML = '<span class="spin"></span> 启动中…';
  $("osRun").style.display = "block";
  $("osOut").innerHTML = ""; $("osArtifact").innerHTML = "";
  $("osSteps").innerHTML = ""; $("osLog").innerHTML = ""; $("osPhase").textContent = "正在创建任务…";
  try{
    var r = await api("/api/oneshot/start", body);
    OS_JOB = r.job_id;
    $("btnOsCancel").style.display = "";
    if(r.status) osPaint(r.status);
    osPoll();
  }catch(e){
    OS_BUSY = false;
    osResetButtons();
    $("osPhase").textContent = "未能启动";
    $("osOut").innerHTML = '<div class="card mt"><div class="notice warn">'+escapeHtml(e.message)+'</div></div>';
  }
}

function osPoll(){
  clearTimeout(OS_TIMER);
  if(!OS_JOB) return;
  OS_TIMER = setTimeout(async function(){
    var res, st;
    try{
      res = await fetch("/api/oneshot/status/" + OS_JOB);
      st = await res.json().catch(function(){ return {}; });
      if(!res.ok){
        var err = new Error(st.detail || ("状态获取失败（HTTP " + res.status + "）"));
        err.status = res.status;
        throw err;
      }
    }catch(e){
      if(e.status === 404){
        // 服务重启后内存任务丢失：停止轮询，避免无限重试
        OS_BUSY = false;
        osResetButtons();
        $("osPhase").textContent = "任务已失效";
        $("osOut").innerHTML = '<div class="card mt"><div class="notice warn">'
          + escapeHtml(e.message) + ' 请重新点「② 开始一键成稿」。</div></div>';
        return;
      }
      $("osPhase").innerHTML = '<span style="color:#d93025">'+escapeHtml(e.message)+'</span>';
      OS_TIMER = setTimeout(osPoll, 4000);
      return;
    }
    osPaint(st);
    if(st.status === "running"){
      osPoll();
    }else{
      OS_BUSY = false;
      osDone(st);
    }
  }, 1500);
}

function osPaint(st){
  var html = "";
  (st.steps||[]).forEach(function(s, i){
    var cls = s.status || "pending";
    var dot = cls === "done" ? "✓"
      : (cls === "error" ? "!"
      : (cls === "running" ? '<span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span>' : String(i+1)));
    html += '<div class="os-step '+cls+'">'
      + '<div class="os-dot">'+dot+'</div>'
      + '<div class="os-main"><div class="os-title">'+(i+1)+' · '+escapeHtml(s.title)
      + (s.seconds ? ' <span class="os-time">'+s.seconds+'s</span>' : "")
      + (s.chars ? ' <span class="os-time">'+(s.chars < 1024 ? s.chars+' 字符' : Math.round(s.chars/1024)+' KB')+'</span>' : "")
      + '</div><div class="os-note">'+escapeHtml(s.note || (cls === "running" ? "进行中…" : ""))+'</div></div>';
    if(st.status !== "running" && (cls === "done" || cls === "error" || cls === "interrupted")){
      html += '<button class="btn small ghost" onclick="osRerun(\''+s.key+'\')">重跑</button>';
    }
    html += '</div>';
  });
  $("osSteps").innerHTML = html;

  var cur = (st.steps||[])[st.current] || {};
  var phase = "";
  if(st.status === "running") phase = "第 " + (st.current + 1) + " / " + (st.steps||[]).length + " 步：" + (cur.title || "");
  else if(st.status === "done") phase = "全部完成";
  else if(st.status === "error") phase = "中断于：" + (cur.title || "未知步骤");
  else if(st.status === "interrupted") phase = "服务已重启，任务在第 " + ((st.current|0) + 1) + " 步中断——可点「重跑」接着做";
  else if(st.status === "canceled") phase = "已取消";
  $("osPhase").textContent = phase;

  var logs = (st.log || []).slice(-9);
  $("osLog").innerHTML = logs.map(function(l){
    return '<div class="os-logline"><span class="os-t">'+escapeHtml(l.t)+'</span>'+escapeHtml(l.msg)+'</div>';
  }).join("");
  $("osLog").scrollTop = $("osLog").scrollHeight;
}

function osDone(st){
  osResetButtons();
  if(st.status === "done" && st.manuscript){
    var cfg = st.cfg || {};
    var meta = [
      "主线 " + escapeHtml((META && META.tracks[cfg.track]) || cfg.track || "—"),
      "体裁 " + escapeHtml((META && META.genres[cfg.genre]) || cfg.genre || "—"),
      "语言 " + (cfg.language === "zh" ? "中文（受限）" : "English"),
      "目标 " + (cfg.words || "—") + (cfg.language === "zh" ? " 字" : " words"),
      "数据 " + (st.dataset && st.dataset.rows
        ? (st.dataset.rows + " 行×" + st.dataset.cols + " 列")
        : "未附数据"),
      "文献 " + (st.stats ? (st.stats.refs || 0) : 0) + " 条",
      "TBD " + (st.stats ? st.stats.tbd : 0) + " 处",
      "CITE " + (st.stats ? st.stats.cite : 0) + " 处"
    ].join(" · ");
    renderResult($("osOut"), "7", st.manuscript,
      AI_WATERMARK_HTML + osRefsHtml(st.refs) + osSelfCheckHtml(st.selfcheck), meta);
    if(cfg.data === "demo" && st.demo_preview){
      renderDemoPreview(st.demo_preview, st.downloads);
    }
    if(cfg.data === "find" && st.downloads && st.downloads.downloaded && st.downloads.downloaded.length){
      renderDownloads(st.downloads);
    }
    osArtifacts(st);
  }else if(st.status === "error"){
    $("osOut").innerHTML = '<div class="card mt"><div class="notice warn"><b>任务中断</b>：'
      + escapeHtml(st.error || "未知错误") + '</div>'
      + '<p class="hint mt">已完成的步骤产物保留在下方「单步产物」里；排除问题后点对应步骤的「重跑」即可从中断处继续。</p></div>';
    osArtifacts(st);
  }else if(st.status === "interrupted"){
    // 服务重启打断：不是代码出错，别用「任务中断/未知错误」吓人
    $("osOut").innerHTML = '<div class="card mt"><div class="notice warn">'
      + '<b>服务重启，任务被打断</b>：这不是报错——部署更新或容器重启会让正在跑的任务停下。'
      + '已完成的步骤产物都还在，点上面被打断那一步的「重跑」就能接着做。</div></div>';
    osArtifacts(st);
  }else if(st.status === "canceled"){
    $("osOut").innerHTML = '<div class="card mt"><div class="notice info">任务已取消。已完成步骤的产物保留在下方。</div></div>';
    osArtifacts(st);
  }
}

function renderDownloads(dl){
  if(!dl) return;
  var html = '<div class="card mt"><div class="card-head"><span class="card-title">代下载结果</span>'
    + '<span class="badge warn">未经解析与核对</span></div>';
  html += '<div class="hint">以下公开源文件已自动下载到任务目录 _sources/，请先核对单位、样本期与统计口径再上传。</div>';
  var items = [];
  (dl.downloaded || []).forEach(function(d){
    items.push('<div class="hint">✅ ' + escapeHtml(d.name) + ' → <code>' + escapeHtml(d.file) + '</code>（' + (d.bytes||0) + ' 字节）</div>');
  });
  (dl.skipped || []).forEach(function(s){
    items.push('<div class="hint">⏭ ' + escapeHtml(s.name) + '：' + escapeHtml(s.reason) + '</div>');
  });
  (dl.failed || []).forEach(function(f){
    items.push('<div class="hint">❌ ' + escapeHtml(f.name) + '：' + escapeHtml(f.reason) + '</div>');
  });
  if(items.length) html += items.join("");
  (dl.notes || []).forEach(function(n){ html += '<div class="hint">' + escapeHtml(n) + '</div>'; });
  html += '</div>';
  $("osOut").insertAdjacentHTML("beforeend", html);
}

function renderDemoPreview(demoText, dl){
  var html = '<div class="card mt"><div class="card-head"><span class="card-title">演示稿（demo_preview.md）</span>'
    + '<span class="badge warn">模拟值 · 仅排版预览 · 不可投稿</span></div>';
  html += '<div class="hint">下方正文的数字都是带 <code>*</code> 的模拟值，仅用于预览排版效果；'
    + '正式投稿请用上方 manuscript.md（数值仍为 [TBD]）。</div>';
  html += '<div class="result-body"></div></div>';
  $("osOut").insertAdjacentHTML("beforeend", html);
  var body = $("osOut").querySelector(".card:last-child .result-body");
  body.innerHTML = md(demoText);
  enhance(body);
}

function osRefsHtml(rf){
  if(!rf || !rf.summary || !rf.summary.markers) return "";
  var s = rf.summary;
  var html = '<div class="card mt"><div class="card-head"><span class="card-title">文献装配（第 6 步）</span>'
    + '<span class="badge '+(s.unresolved ? "warn" : "ok")+'">'
    + (s.unresolved ? "有未解决占位" : "全部装配") + '</span></div>';
  html += '<div class="stat">'
    + '<div class="s total"><div class="v">'+(s.unique||0)+'</div><div class="l">参考文献</div></div>'
    + '<div class="s nice"><div class="v">'+(s.ok||0)+'</div><div class="l">强匹配</div></div>'
    + '<div class="s should"><div class="v">'+(s.weak||0)+'</div><div class="l">弱匹配需核对</div></div>'
    + '<div class="s must"><div class="v">'+(s.unresolved||0)+'</div><div class="l">未解决占位</div></div>'
    + '</div>';
  html += '<div class="muted">正文占位 '+(s.markers||0)+' 处 ｜ 去重后 '+(s.unique||0)+' 条 ｜ 含 DOI '
    + (s.with_doi||0)+' 条 ｜ 检索源 OpenAlex</div>';

  var entries = rf.entries || [];
  if(entries.length){
    html += '<details class="os-refs"><summary>查看参考文献（'+entries.length+' 条）</summary><div class="os-reflist">';
    entries.forEach(function(e, i){
      html += '<div class="os-ref"><span class="os-refn">'+(i+1)+'</span><span>'+escapeHtml(e)+'</span></div>';
    });
    html += '</div></details>';
  }

  var bad = (rf.items || []).filter(function(it){ return it.status !== "ok" && it.status !== "weak"; });
  if(bad.length){
    html += '<h3 style="margin-top:16px">未解决的位置（正文保留占位）</h3>'
      + '<div class="table-wrap"><table><thead><tr><th>#</th><th>原文需要什么来源</th><th>原因</th></tr></thead><tbody>';
    bad.forEach(function(it){
      html += '<tr><td>'+it.n+'</td><td>'+escapeHtml(it.marker || "")+'</td><td>'+escapeHtml(it.reason || "")+'</td></tr>';
    });
    html += '</tbody></table></div>';
  }
  html += '<div class="notice info">所有条目都带 DOI，可点开核对来源。弱匹配只说明主题相关，'
    + '不等于它就是该论点最合适的出处；逐条对照见「单步产物 · 06_refs.md」。</div>';
  html += '</div>';
  return html;
}

function osSelfCheckHtml(sc){
  if(!sc || sc.applicable === undefined) return "";
  var missing = sc.missing || [];
  var q = sc.quality || {};
  var a = sc.assets || {};
  var tmiss = (a.table_missing || []).map(function(n){ return "Table " + n; });
  var fmiss = (a.figure_missing || []).map(function(n){ return "Figure " + n; });
  var missAssets = tmiss.concat(fmiss);
  var tdup = (a.table_dup || []).map(function(n){ return "Table " + n; });
  var fdup = (a.figure_dup || []).map(function(n){ return "Figure " + n; });
  var dupAssets = tdup.concat(fdup);
  var html = '<div class="card mt"><h3>自检结果（第 7 步）</h3>';
  html += '<div class="stat">'
    + '<div class="s total"><div class="v">'+(sc.hits||0)+'</div><div class="l">词面命中</div></div>'
    + '<div class="s must"><div class="v">'+(sc.must||0)+'</div><div class="l">硬伤 must</div></div>'
    + '<div class="s should"><div class="v">'+(sc.tbd||0)+'</div><div class="l">待填 TBD</div></div>'
    + '<div class="s nice"><div class="v">'+(sc.cite||0)+'</div><div class="l">待补 CITE</div></div>'
    + '</div>';
  html += '<div class="muted">词数 '+(sc.words||0)+' ｜ 适用规则 '+(sc.applicable||0)+' 条 ｜ 自动判定 '+(sc.auto||0)
    + ' 条 ｜ 需人工判读 '+(sc.manual||0)+' 条</div>';
  html += '<div style="margin-top:10px">'
    + '<span class="badge '+(q.gap?"ok":"no")+'" style="margin:2px 4px 2px 0">'+(q.gap?"有":"缺")+' gap 句</span>'
    + '<span class="badge '+(q.contrib?"ok":"no")+'" style="margin:2px 4px 2px 0">'+(q.contrib?"有":"缺")+' 贡献声明</span>'
    + '<span class="badge '+(q.limitation?"ok":"no")+'" style="margin:2px 4px 2px 0">'+(q.limitation?"有":"缺")+' 局限性</span>'
    + (missing.length ? '<span class="badge no" style="margin:2px 4px 2px 0">缺章节 '+escapeHtml(missing.join("/"))+'</span>' : "")
    + ((a.tables || []).length || (a.figures || []).length
        ? '<span class="badge ok" style="margin:2px 4px 2px 0">表 '+((a.tables||[]).length)+' 张 / 图 '+((a.figures||[]).length)+' 个</span>'
        : '<span class="badge no" style="margin:2px 4px 2px 0">稿内无表无图</span>')
    + (missAssets.length ? '<span class="badge no" style="margin:2px 4px 2px 0">缺 '+escapeHtml(missAssets.join("、"))+'</span>' : "")
    + (dupAssets.length ? '<span class="badge no" style="margin:2px 4px 2px 0">重号 '+escapeHtml(dupAssets.join("、"))+'</span>' : "")
    + '</div>';
  html += '<div class="notice '+(sc.must ? "warn" : "info")+'">'
    + (missAssets.length ? "正文引用了稿内不存在的 " + missAssets.join("、") + "，导出后会对不上；" : "")
    + (dupAssets.length ? "编号 " + dupAssets.join("、") + " 在稿内出现了多次标题，导出后会重号；" : "")
    + (sc.must ? "有 " + sc.must + " 条硬伤需要先处理；" : "")
    + '完整缺陷清单见「单步产物 · 07_check.md」。自检只覆盖可词面判定的规则，'
    + '其余 ' + (sc.manual||0) + ' 条建议交回「投稿前审查」做大模型深度判读。</div>';
  html += '</div>';
  return html;
}

function osArtifacts(st){
  var names = Object.keys(st.artifacts || {});
  if(!names.length){ $("osArtifact").innerHTML = ""; return; }
  names.sort();
  var html = '<div class="card mt"><div class="card-head"><span class="card-title">单步产物</span>'
    + '<span class="muted">点开查看 Markdown 原文</span></div><div class="row">';
  names.forEach(function(n){
    html += '<button class="btn small ghost" onclick="osViewArtifact(\''+n+'\')">'+escapeHtml(n)+'</button>';
  });
  html += '</div><div id="osArtifactBody"></div></div>';
  $("osArtifact").innerHTML = html;
}

async function osViewArtifact(name){
  if(!OS_JOB) return;
  var box = $("osArtifactBody");
  if(!box) return;
  box.innerHTML = '<div class="loading"><span class="spin" style="border-color:#2f6fe0;border-top-color:transparent"></span> 读取中…</div>';
  try{
    var res = await fetch("/api/oneshot/artifact/" + OS_JOB + "/" + encodeURIComponent(name));
    var r = await res.json().catch(function(){ return {}; });
    if(!res.ok) throw new Error(r.detail || "读取失败");
    box.innerHTML = '<div class="card mt"><div class="card-head"><span class="card-title">'+escapeHtml(r.name)
      + '</span><button class="btn small ghost" onclick="osHideArtifact()">收起</button></div>'
      + '<div class="result-body"></div></div>';
    var body = box.querySelector(".result-body");
    body.innerHTML = md(r.markdown);
    enhance(body);
    box.scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){
    box.innerHTML = '<div class="notice warn">'+escapeHtml(e.message)+'</div>';
  }
}

function osHideArtifact(){
  var box = $("osArtifactBody");
  if(box) box.innerHTML = "";
}

async function osRerun(step){
  if(!OS_JOB || OS_BUSY) return;
  if(!confirm("重跑「" + step + "」及其后的所有步骤？已生成的后续内容会被覆盖。")) return;
  // 重跑要带上 Key：服务端重启恢复的任务内存里没有 llm 配置（不落盘），
  // 不带就会在后端报「未配置 API Key」，而用户明明在设置里填过。
  var body = {job_id: OS_JOB, step: step};
  var llm = llmFields();
  if(llm.api_key) { body.api_key = llm.api_key; body.base_url = llm.base_url; body.model = llm.model; }
  OS_BUSY = true;
  try{
    await api("/api/oneshot/rerun", body);
    $("osOut").innerHTML = ""; $("osArtifact").innerHTML = "";
    $("btnOsCancel").style.display = "";
    $("osPhase").textContent = "重新执行中…";
    osPoll();
  }catch(e){
    OS_BUSY = false;
    alert(e.message);
  }
}

async function osCancel(){
  if(!OS_JOB) return;
  try{
    await api("/api/oneshot/cancel", {job_id: OS_JOB});
    $("osPhase").textContent = "正在取消（当前步骤结束后停止）…";
  }catch(e){ alert(e.message); }
}

/* 后端版本自检：旧进程缺接口时，报错会是 405，用户会误以为是地址填错 */
function checkBackend(){
  var box = $("staleNotice");
  if(!box) return;
  var f = (META && META.features) || [];
  var stale = !f.length || f.indexOf("title_translate") < 0;
  box.style.display = stale ? "block" : "none";
}

/* ---------- 启动 ---------- */
async function doLogout(){
  try{ await fetch("/api/auth/logout", {method: "POST", credentials: "same-origin"}); }
  catch(e){ /* Cookie 清不掉也照样跳，至少本地不再显示内容 */ }
  location.href = "/login.html";
}

function renderAccess(meta){
  // 只有口令模式下才有「退出」的意义；本地桌面版不显示，免得用户以为要登录
  var b = $("btnLogout");
  if(b) b.style.display = (meta && meta.access && meta.access.mode !== "private")
    ? "inline-block" : "none";
}

async function init(){
  buildNav();
  buildCapabilities();
  buildTrackTable();
  initUpload();
  watchTrendInputs();
  var df = $("s7-datafile");
  if(df) df.addEventListener("change", function(){
    osUploadData(this.files);
  });
  var ti = $("s7-title");
  if(ti){
    // 离开输入框就试着英译：从选题页复制过来的多是中文题名
    ti.addEventListener("blur", function(){ osTranslateTitle(false); });
    ti.addEventListener("paste", function(){
      setTimeout(function(){ osTranslateTitle(false); }, 60);
    });
  }
  try{
    var res = await fetch("/api/meta");
    META = await res.json();
    fillTrackSelects();
    renderProviders();
    fillPromo();
    checkBackend();
    renderAccess(META);
  }catch(e){ /* meta 加载失败不阻塞 */ }
  try{
    var h = await (await fetch("/api/health")).json();
    // 服务端已配好 Key 时，界面上不该再提示「尚未配置」
    if(h.has_default_key && META) META.has_default_key = true;
  }catch(e){}
  updateKeyNotice();
}

init();
