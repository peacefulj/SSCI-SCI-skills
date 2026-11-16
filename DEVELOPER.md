# PaperMate 二次开发指南

这份文档写给接手继续开发的人。**先读这一页，再看 README 的功能说明。**
README 讲「这个工具能做什么」，这里讲「代码在哪、改哪里、哪些不能碰」。

- 交付版本：v1.2.4（2026-11-12）
- 技术栈：Python 3.10+ / FastAPI / 原生 JS（无构建、无 npm）
- 运行形态：单进程本地 Web 应用，`python server.py` → `http://127.0.0.1:8000`

---

## 0. 包里有什么、没有什么

| 有 | 没有（刻意排除，见 `.gitignore`） |
|---|---|
| 全部源码（后端 10 个 py + 前端 4 个文件） | `.env`（真实 API Key，已从包内剔除） |
| `skill/` 完整规则库（393 条规则 + 95 检测器 + 31 本书单 + 雷达扩展包） | `__pycache__/`、`*.pyc` |
| `static/vendor/`（marked + MathJax 完整版，离线可用，2.2 MB） | `_oneshot/`（历史成稿产物） |
| `requirements.txt`、`start.bat` / `start.sh`、`env_check.py`、`.env.example` | `_exports/`、`uploads/`（运行时生成） |
| 本文件 + `README.md` | 任何真实 API Key / 账号凭据 |

自带规则库来源见 `skill/academic-writing-v1.1/references/book-index.md`，
每条规则标注到章节与页码，不是凭空写的。

---

## 1. 三分钟跑起来

```bash
# 0) 环境自检（缺什么会直接说，加 --install 自动装）
python env_check.py

# 1) 依赖（Python 3.10+）
python -m pip install -r requirements.txt

# 2) 配 Key：二选一，效果等价
cp .env.example .env && vim .env      # 写 DEEPSEEK_API_KEY=...
# 或者启动后在网页右上角「设置」里填（请求体优先于 .env）

# 3) 启动
python server.py                       # Windows 也可双击 start.bat
```

> **务必不要**用 `uvicorn --reload` 之外的方式热改后端。这个项目已经出现过两次
> 「改了代码但用户看到的还是报错」，原因都是**旧进程没重启**：旧进程里没有新路由，
> 前端拿到的就是 `405 Method Not Allowed`。改完后端必须重启进程。

### 1.1 启动流程（`server.py` 的 `main()`）

```
main()
 ├─ sys.stdout 改为 UTF-8 + 行缓冲（否则重定向时横幅迟迟不出现）
 ├─ 读 PAPERMATE_PORT（默认 8000）
 ├─ 该端口已有健康的 PaperMate？ → 打印「已经在运行」+ 打开浏览器 + exit 0
 │    （两个实例的任务表在各自内存里，不共享，起第二个只会让人以为「没反应」）
 ├─ 端口被别的程序占用？ → 顺延 8001…8019，实在没有就让系统分配
 │    旧版本这里直接抛 [Errno 10048] 退出，用户只看到一屏英文
 ├─ _banner()：Python 版本 / 必需依赖 / 可选组件 / API Key / 目录写权限
 └─ uvicorn.run(log_level="warning")
```

`_banner()` 是用户「起不来」时唯一的自解释入口，**加新依赖时记得同步这里的检查列表**。

环境变量：

| 变量 | 作用 |
|---|---|
| `PAPERMATE_PORT` | 首选端口（默认 8000） |
| `PAPERMATE_NO_BROWSER` | 设为任意值则不自动开浏览器（服务器/远程场景） |
| `SOFFICE_PATH` | 手动指定 LibreOffice 可执行文件（装在非标准路径时） |

### 1.2 依赖分层：什么坏了不影响主流程

| 层 | 包 | 缺了会怎样 |
|---|---|---|
| 必需 | fastapi / uvicorn / PyYAML / requests / python-multipart / python-docx / lxml | 起不来，横幅报 `[缺]` |
| 必需（数据） | openpyxl | 只能传 csv/tsv，xlsx 报「缺少 openpyxl」（**曾漏在 requirements 里，已修**） |
| 必需（摄取） | PyMuPDF（1.25–1.x） | PDF 上传报「未安装 PyMuPDF」，其余格式正常 |
| 可选 | pandas | `.dta/.sav/.parquet` 不可读，给「另存为 csv」指引 |
| 可选 | LibreOffice（外部程序） | `.doc/.xls/.ods` 不可读；`.docx/.xlsx` 不受影响 |

**PyMuPDF 为什么锁 `<2`**：2.x 会连带 `onnxruntime`(48 MB)+`pymupdf_layout`+`numpy`，
site-packages 从约 110 MB 涨到 278 MB，国内网络装失败率明显上升。1.25+ 同时提供
`pymupdf` 与 `fitz` 两个模块名，`ingest.py` 两条路都试，锁 1.x 不损失功能。

### 1.3 `env_check.py`（用户自查 + CI）

只用标准库，所以「什么都没装」时也能跑。三个用途：

```bash
python env_check.py            # 人读报告，缺项退出码 1
python env_check.py --install  # 缺必需依赖则装（默认源 → 清华 → 阿里云）
python env_check.py --json     # 机器读（字段见 collect()）
```

改依赖时同步 `REQUIRED` 列表与 `server.py` 的 `_banner()`，否则自检会漏报。

自检清单（复制即可）：

```bash
curl -s http://127.0.0.1:8000/api/meta | python -c "import json,sys;d=json.load(sys.stdin);print(d['features'],d['has_default_key'])"
curl -s -X POST http://127.0.0.1:8000/api/llm/test -H "Content-Type: application/json" -d '{}'
```

`features` 应含 `llm_test / title_translate / dataset_profile / oneshot_v2` 四项。
少任何一项 → 跑的是旧代码。

---

## 2. 代码地图

### 2.1 后端

| 文件 | 行数 | 职责 | 改它之前要知道 |
|---|---|---|---|
| `server.py` | 787 | FastAPI 全部路由、请求模型、`resolve_llm()`（请求体 → .env → 环境变量）、启动期端口探测与环境横幅 | 路由都是函数级 `@app.post`；启动逻辑见 1.1，加依赖要同步 `_banner()`；静态文件挂在根路径（`/app.js` 而不是 `/static/app.js`） |
| `engine.py` | 357 | 加载 `skill/` 的规则与检测器；章节切分；词面检测；期刊清单；扩展包状态 | **直接 import skill 自带脚本**（`score.py` / `check_structure.py`），不重写检测逻辑 |
| `llm.py` | 812 | 三家接入（OpenAI 兼容 + Anthropic Messages）、地址归一化、错误翻译、深度判读、六阶段工作流提示词 | 所有模型调用都走 `chat()`；不要绕过它直连 requests |
| `oneshot.py` | 1947 | 一键成稿七步流水线、任务状态机、前置检查、数据画像注入与体检、**图表清单分发与自检** | 最大的文件。改流程看 `STEPS` / `STEP_ARTIFACT` / `_step_*`；改图表看 3.2 末段列的四个函数；改体检看 3.4 |
| `refs.py` | ~1120 | 文献装配：需求分流（数据源 / 点名文献 / 普通）+ **三源检索（缓存 → OpenAlex → Crossref 兜底）** + 白名单校验 + 四套著录 | 只装配真实存在的文献；查不到就留空，不编造。分流与阈值的取舍见 3.5；兜底与缓存见 3.6 |
| `cite_check.py` | 296 | 引用格式对账：卷期、DOI、作者名、来源类型、双向对应 | 只读 skill 的 `citation-*.md` 当依据（**skill 只读，检测器只能建在这里**）；只判词面硬错误，不判引用是否切题 |
| `dataset.py` | 1035 | 数据画像：多格式解析（csv/tsv/txt/xlsx/xls/ods/json，多文件合并）+ 类型判定 + 结构/方法族推断 + 学科线建议 + **数据体检 `gap_report()`** | 只用标准库 csv + openpyxl + LibreOffice 转换，**不引 pandas**（只在恰好装了时借用读 dta/sav）；不存原始行；体检只判结构、不插补 |
| `datasource.py` | ~430 | 数据源荐引：世行指标白名单（本地关键词匹配）+ Zenodo / Harvard Dataverse 检索 + 手工/授权入口 + `download()` 代下载白名单公开源 | **给线索 + 代下载白名单源，仍不解析不写回**：授权/付费站拒绝，下载失败降级不阻断 |
| `ingest.py` | 833 | 文档摄取：docx/doc/tex/html/pdf → Markdown（表格/图片/OMML 公式） | 按文件内容判断格式，不只看扩展名；`UPLOAD_DIR` 不可写时退到系统临时目录（只读盘也能启动） |
| `export.py` | 1014 | Markdown → docx（真表格 + OMML 公式）/ tex（ctexart） | docx 用 python-docx 手写；公式转 OMML 是自研逻辑 |
| `topic_trend.py` | 114 | 选题雷达：OpenAlex 发文趋势（标准库 urllib） | 外部服务 503 时降级为「未获取到」，不阻断流程 |
| `litcache.py` | ~130 | **文献检索缓存**（SQLite，跨进程/跨重启）：`get()` / `put()` / `stats()` / `clear()` | 只缓存原始记录，不缓存匹配判定；任何异常都静默降级，缓存不能成为新故障点。见 3.6 |
| `env_check.py` | 260 | 环境自检/装依赖（纯标准库） | 改依赖时同步这里的 `REQUIRED` 与 `server._banner()`；打包模式下依赖已内置，`--install` 直接退出 |
| `paths.py` | 116 | **路径解析**：`resource_root()`（只读资源）/ `data_root()`（可写数据）/ `env_path()` / `cache_path()` | **新代码禁止直接写 `Path(__file__).parent`**——打包后它指向只读的 `_MEIPASS`。详见 8.1 |
| `launcher.py` | 95 | 打包入口：建可写目录、补 `.env`、切工作目录，再交给 `server.main()` | 只做分发期的事，不放业务逻辑；启动失败会打印 `paths.describe()` 便于远程排障 |

### 2.2 前端（无框架，无构建）

| 文件 | 行数 | 职责 |
|---|---|---|
| `static/index.html` | 402 | 全部页面结构（七大能力 + 一键成稿 + 设置弹窗）。单页多 tab，切换靠 `switchTab()` |
| `static/app.js` | 1740 | 全部交互逻辑：请求封装 `api()`、状态、渲染、一键成稿轮询、数据体检与数据源渲染 |
| `static/render.js` | 249 | Markdown 渲染（marked + MathJax），表格/公式/图片 |
| `static/style.css` | 325 | 全部样式，CSS 变量在文件头部 |
| `static/vendor/` | — | marked.min.js、mathjax/tex-svg.js（**完整版 2,275,113 字节 ≈ 2.17 MB**，含 boldsymbol/operatorname/tag 等扩展，勿换回精简版），本地内置，断网可用 |
| `static/samples/` | — | 各体裁好坏样稿，用于演示与回归 |

约定：前端不打包、不转译，改完 `Ctrl+F5` 即可。**注意浏览器缓存**——改 `app.js`
后如果不强刷，看到的还是旧逻辑。

---

## 3. 三条数据流

### 3.1 投稿前审查（词面 + 深度判读）

```
稿件(文本/md/docx/tex/pdf)
   │
   ├─ ingest.py ──→ Markdown
   │
   ├─ engine.lexical_review()  ── 95 条可词面判定 ──→ 命中清单（毫秒级，不花钱）
   │
   └─ llm.deep_review()        ── 298 条需人工判读 ──→ 分批（每批 10 条）对照 signal
                                     └─→ 三层风险：硬伤 / 建议 / 可选 + 出处 + 改法
```

### 3.2 一键成稿（七步）

```
cfg(title/track/genre/level/words/data/citation/venue/dataset_id)
   │
   ├─ gate_check()       前置检查 + 章节字数计划（不调模型）
   ├─ start()            中文题名先英译；建 job；后台线程跑
   │
   ├─ 01 topic   题目体检（有 title 时不生成候选，强制保留作者原题）
   ├─ 02 chosen  定题落位（source=author 时不调模型，直接落盘）
   ├─ 03 design  研究设计（变量画像只注入这里 + draft 的 method/results）
   ├─ 04 outline 大纲与字数分配
   ├─ 05 draft   分章成稿（逐章调模型，拼 manuscript.md）
   ├─ 06 refs    refs.py 装配真实文献（OpenAlex + 白名单）
   └─ 07 check   selfcheck（TBD/CITE 计数 + 词面复检）
   │
   └─ 产物 _oneshot/<job_id>/01_topic.md … 07_check.md + manuscript.md（find 档另有 03b_sources.md）
```

任务状态在内存 `oneshot.JOBS`（进程重启即丢），产物在磁盘（不会丢）。
`GET /api/oneshot/status/{id}` 返回结构：

```json
{
  "id": "6d1444ce7c57", "status": "running|done|failed|canceled",
  "current": "draft", "error": null,
  "cfg": {}, "plan": [], "steps": [{"key":"topic","title":"选题与候选","status":"done","note":""}],
  "log": ["…最多 60 行"], "artifacts": {"topic":"01_topic.md"},
  "manuscript": "（仅 draft 完成后下发，避免轮询传几十 KB）",
  "selfcheck": {}, "refs": {}, "dataset": {},
  "stats": {"chars":0,"sections":0,"tbd":0,"cite":0,"refs":0,"hits":0}
}
```

#### 图表是怎么从大纲流到成稿的（改这块看这四个函数）

第 4 步大纲产出 `job["data"]["tables"]` / `job["data"]["figures"]`（每项 `{id, caption, section, notes}`），
第 5 步按章节消费，第 7 步回头核对。四个函数串起整条链：

| 函数 | 位置 | 作用 |
|---|---|---|
| `_section_assets(job, key)` | `oneshot.py` | 把清单按 `section` 收敛到本地章节 key（`_asset_sec()` 做别名映射：methodology→method、empirical→results…），返回本节该产出的表/图 |
| `_assets_prompt(job, key)` | `oneshot.py` | 生成本节提示词块：列出编号+标题+要展示什么，并给出硬性写法（表=GFM 至少 2 行、图=引用块占位、编号不得重复、无数据用 `[TBD]`） |
| `_inject_figure_blocks(job)` | `oneshot.py` | 全章写完后补漏：清单里有、稿内没有的图，按节插入占位块。**全篇查重**（不是按节查），避免同一编号在两节各出现一次 |
| `_assets_audit(man)` | `oneshot.py` | 第 7 步核对：稿内真实表/图编号 vs 正文引用，返回 `table_missing` / `figure_missing` / `table_dup` / `figure_dup` / `table_rows`，写入 `selfcheck.assets` |

三个容易踩的坑：

1. **别只把清单塞进提示词就完事**。实测模型会「正文写 Table 3、稿内一张表都没有」，所以 `_step_draft` 生成后要用 `_count_tables()` / `"$$" in text` 校验，缺表或该给公式没给时**重写一次**（只重试一次，避免烧钱死循环）。
2. **编号重复要在提示词里禁，也要在自检里报**。前者降低概率，后者兜底——重号只有导出到 Word 才会暴露成两张 Table 1。
3. **图是占位块，不是图片**。不要为了「看起来完整」去接 matplotlib 生成假图，那违反「不编数据」这条不变量。

### 3.3 数据导入（只送画像，不送原始行）

```
csv/tsv/txt/xlsx/xls/ods/json ── dataset.profile_files() ──→ bundle
   │  （xls/ods 先经 LibreOffice 转 xlsx；dta/sav 只在恰好装了 pandas 时读）
   │
   ├─ 每份文件一个 part：{filename, kind, rows, cols, cols_profiled, truncated,
   │                      columns[{name,type,missing,unique,mean,sd,min,max,share,avg_len,examples}],
   │                      meta{sheet,sheets,converted_from,header_synthesized}, id_like[]}
   ├─ 结构判定 structure：panel / time-series / cross-section / text-corpus / table
   │     └─ entity / time / n_entities / n_periods / balanced
   ├─ 方法族信号 signals：panel / did / iv / rdd / survival / classification / experiment /
   │                      ml-eval / medical / text（每条带 evidence 与 confidence）
   ├─ 学科线建议 suggest：{track, genre, reasons[], confidence}
   └─ 落盘 _oneshot/_datasets/<id>.json（只有画像，没有原始行）
```

消费方三处：

| 位置 | 用画像做什么 |
|---|---|
| `oneshot._ctx_block()` | 03 设计 / 04 大纲 / 05 成稿的 method·results·data 节：变量名照抄、ID 列不进回归、结构与方法族信号 |
| `oneshot._data_shape_hint()` | 03 设计：中文版的结构信号 + 「不符要给理由」，防止面板数据被写成截面回归 |
| `oneshot.gate_check()` 的 `autotrack` | 与用户所选学科线比对，不一致就 warn（**不改用户选择**），前端另有「用这个主线」按钮 |
| `oneshot.gate_check()` 的 `data_gap` / `_step_check()` 的「数据体检」 | 按画像判「哪些分析做不了」，见 3.4 |
| `POST /api/oneshot/data/sources` | 按题目荐数据源（`datasource.suggest()`），只给链接 |

这条红线在 UI 上也写明：**原始行不上云、不存服务端**。注意 `examples` 是**真的会发给模型**的
3 个示例值（文本列），所以疑似姓名/手机/邮箱/地址的列已在 `_mark_ids` 之前按 `_PII_HINTS`
替换成「（已脱敏）」。改这条逻辑前先想清楚隐私后果。

### 3.4 数据不全怎么办（体检 + 荐源，**不做自动补数**）

用户问得最多的是「数据不全，能不能全网找数据补上，或者用模拟数据填充」。
结论是**一半可行、一半是红线**，代码也按这个结论分工。

**先分清三种缺口**，处置完全不同（这张表是这一节的核心）：

| 缺口类型 | 例子 | 能自动补吗 | 处置 |
|---|---|---|---|
| 缺列 / 缺变量 | 想做 DiD，但表里没有 treat 列 | 极难（口径要人判断） | 荐源 + 改设计 |
| 单元格缺失 | 某变量 30% 是空的 | 技术上可插补 | 需原始行 + 方法学声明；**本系统不做**（只存画像，没有行） |
| 样本期 / 样本量不足 | 只有 3 期面板、n=18 | **不能** | 只能改研究设计 |

**P1 数据体检**（`dataset.gap_report()`，纯本地、无网络）
判 6 件事：样本量、可分析变量数、关键变量缺失率、面板深度/时序长度、
取值退化（数值列只有 2 个不同值）、多表能否按实体键连接。
阈值都在 `dataset.py` 顶部（`_GAP_MIN_ROWS` / `_GAP_MISS_RISK` …），要调只改那里。

出口三处，共用同一份结果：
- `gate_check()` 的 `data_gap` 检查项 → 生成前就能看到「阻断 N 项」
- `_step_check()` 的「数据体检」小节 → 写进 `07_check.md`，并把阻断项加进「投稿前必须处理」
- `_data_shape_hint()` → 进 03 设计的提示词，附一句「不得掩盖、不得编造缺失部分」

**P2 数据源荐引**（`datasource.py` + `POST /api/oneshot/data/sources`）
- 世行指标：本地关键词匹配（18 个指标，代码逐一实测存在），给 `data.worldbank.org` 页面入口。
  **不给 csv 直链**：实测 CSV 端点常超时（45s 无响应），而网页 200/8s，给直链等于给死链。
- Zenodo / Harvard Dataverse：真检索，命中带 DOI。Zenodo 加 `type=dataset` 过滤，
  标题还要过 `_relevant()`（≥2 个检索词命中）——否则查「digital transformation」会捞回德文
  《Transformation in der heterogenen Gruppe》这类噪声（实测踩过）。
  **不要加 `sort=mostrecent`**：那是按上传时间而非相关性排，实测同一检索式下相关率从 3/5 掉到 0/5。
- 国家统计局 / 北大开放数据 / CSMAR：只给入口与取数步骤。统计局实测 403，任何脚本直连都不通。
- 微观题（题名含 firm / enterprise / listed / 企业 / 上市公司…，见 `_micro_level()`）：
  手工与授权入口排在前面，世行只留 1 条兜底并标注「仅当设计是省/国别面板时适用」。
  给「企业绿色创新」推国别 GDP 是没有意义的。
- 中文题目：用一次轻量模型调用转英文检索词；没有 key 就跳过在线检索、只给白名单（不报错）。

**P3 `find` 档：把「帮我找数据」做成一个数据状态**（v1.2.5）

`cfg["data"]` 四个值：`yes` / `partial` / `no` / `find`。
`find` = 「无数据 + 请求荐源」：**写作行为与 `no` 完全一致**（结果章照样骨架 + `[TBD]`），
差别只在第 3 步多一份「可核实的数据源清单」，并且清单会落盘成 `03b_sources.md`。

改这一档时最容易犯的错，是只加前端 option、忘了后端白名单：
`normalize_cfg()` 会把不认识的值静默改回 `no`——界面上选了、流程也跑完了，
但检索根本不触发，属于最难查的那类失效。所以：

- 判断「有没有数据」一律走 `_nodata(cfg)`，不要再手写 `in ("no", "partial")`
- 提示词里给模型看的是 `DATA_EN` 的人话，不是裸枚举值（`find` 单独丢过去没有语义）
- 检索结果缓存在 `cfg["sources"]`（前端页面已查过就带过来，`normalize_cfg` 裁到 10 条 × 7 字段），
  跑批时命中就不联网；`_sources_for()` 里缓存优先，没缓存才检索，任何异常都降级为空清单
- 失败时的底线：清单为空 → 提示词改成「不要凭印象点名数据库」+ 白名单入口仍在，
  成稿不受影响。**检索失败绝不能让成稿失败**

**明确不做的事**（改动前请先读第 5 节不变量）
1. 不解析数值、不写入画像 —— 返回值里没有任何数字。
2. 不插补、不自动填表。
3. `find` 不改变结果章的写法。它只回答「去哪儿取」，不回答「数值是多少」。

### 3.6 代下载 + 演示模式（v1.2.7 的边界放宽与红线收紧）

v1.2.7 起，用户把上一轮的界线「只给线索、不代下载、不落数字」放宽成两件事，同时新增
第 5 个数据状态 `demo`：

**① `find` 档代下载公开源（边界放宽）**
- `datasource.download()`：只代下载白名单来源（世行 `api.worldbank.org`、Zenodo、
  Harvard Dataverse、`doi.org`）；授权/付费/反爬站点（统计局、北大、CSMAR、CFPS）一律
  拒绝并说明「请手工取」。白名单是硬编码的 `ALLOWED_HOSTS`，不是靠 url 猜。
- 下载落盘到 `_oneshot/<job>/_sources/`，**不解析、不写回画像、不注入正文**；单文件上限
  50MB，超了就只给链接。
- 触发是自动的：`_step_design` 在 `find`/`demo` 档调 `_sources_download()`；失败只记日志，
  绝不阻断成稿。前端 `osFindSources` 只检索不下，下载交给成稿流程（避免重复联网）。

**② 新增 `demo` 档（演示模式，模拟值隔离）**
- `cfg["data"]` 第五个值：`demo` = 「正文仍 [TBD] 占位 + 另产一份带模拟值的演示稿」。
- `_write_demo_preview()` 生成 `demo_preview.md`：把正文里的数据占位 `[TBD: ...]` 换成
  带 `*` 的模拟值，文件头大字声明 `SIMULATED DATA — LAYOUT PREVIEW ONLY, NOT FOR SUBMISSION`。
- **红线（比上一轮更收紧）**：模拟值绝不进正文 `manuscript.md`。三层隔离：
  1. 产物隔离——`manuscript.md` 永远 `[TBD]`，模拟值只在 `demo_preview.md`；
  2. 标注隔离——每个模拟值带 `*`，文件头大字声明；
  3. 链路隔离——`refs`/`check`/`_body_counts` 只看 `draft_sections`（正文），demo 稿不参与。
- 正负向后顾正则 `(?<!`)... (?!`)` 保证元数据说明里的 `` `[TBD: ...]` ``（草稿声明）不被
  误替换成模拟值。

**新增档位最容易犯的错**（与 `find` 当年一致）：只加前端 option、忘了 `normalize_cfg`
白名单 → 界面选了、流程跑完、但被静默改回 `no`。所以 `normalize_cfg` 的白名单、
`_nodata()` 的判断、`gate_check` 的 data 分支、`_step_check` 的 find/demo 分支都要同步。
`DATA_EN` 里给模型看的是人话（"demo ... A SEPARATE demo file may contain clearly-labeled
simulated values"），不是裸 `demo` 这个词。

---

### 3.5 引用装配为什么容易出错（v1.2.6 的分流与对账）

一份真实稿的实测：30 处引用需求 → 强匹配 3、弱匹配 16、未解决 11，其中多条是硬错：
要 World Bank 的 `IT.NET.USER.ZS` 指标，配了一篇讨论 WDI 的俄文文章；
点名 "Autor, Levy and Murnane"，配了 2024 年别人写的《The Task Content of Occupations》；
点名 Romano–Wolf，配了另一篇置换检验。

**根因不是"检索不准"，是三个层面的错配**：

1. **skill 的 CIT 族在当前体裁下不适用。** `rules.yaml` 里 16 条 CIT 规则的 `genre`
   只挂 ei-conf / ai-conf / sci-journal / ssci / dissertation，**不含 `quant`**——
   而一键成稿默认就是 quant。所以整族规则一条都不会被选中。
2. **有规则没检测器。** 16 条里只有 4 条带检测器，且全是 GB/T 与 IEEE 专用；
   APA 四条全无，`CIT-CHK-001`（正文与文献表双向对应）也无。
3. **代码绕开规范。** `refs.py` 自己实现了四套格式化，从未读 `citation-*.md`，
   于是出现 `Vol. 51(1)`、`A, H. D.`、把 `Emerald … eBooks` 当刊名。

**改法一：引用需求先分流，再检索**（`assemble()` 开头）

| 需求类型 | 识别 | 处置 |
|---|---|---|
| 要一份数据 | `_match_dataset()`：命中机构名 + 出现 data/indicator/统计/方法学 等词 | 直接生成数据集引用（机构 + 年份 + 数据集名 + URL），**不检索论文** |
| 点名某篇 | `_named()`：`Autor (2003)` / `Autor and Dorn (2013)` / `Romano–Wolf (2005)` / 三姓并列无年份 | 按「作者 + 年份」精确取（`_find_by_author()`） |
| 普通文献 | 其余 | 原关键词检索 |

三个必须守住的取舍：

- **点名文献定位不到就留空。** 旧代码在精确检索失败后会静默落回关键词检索，
  结果把 "Altonji, Elder and Taber (2005)" 配成一篇抗精神病药物研究。
  现在失败直接标 unresolved，并在 `06_refs.md` 写明"请手工补这一条，不要用相近文献顶替"。
- **机构叙述句不算点名。** `World Bank (2020) shows that…` 会被 `NAMED_YEAR` 解析出
  `(Bank, 2020)`，所以 `_named()` 里有 `ORG_WORDS` 黑名单。
- **同名作者要用第二条路径兜。** `/authors?search=Romano` 首条是 1949 篇作品的
  "M. Romano"，不是 Joseph P. Romano。`_find_by_author()` 先走作者 ID，
  落空再用「主题词 + 年份」检索、本地筛作者。

**改法二：格式对账建在应用侧**（`cite_check.py`）

`skill/**` 只读，检测器不能往 `detectors.yaml` 里加。所以 `cite_check.py` 只读
`assets/citation-*.md` 当依据（报告里的 `basis` 字段就是出处），自己实现词面检查：
卷期 `Vol.`/空格、DOI 形式（APA 要链接、IEEE/GB 不要）、作者名合法性
（单字母姓即解析失败）、来源类型（平台字段名不是刊名）、体系混用（CIT-STY-001）、
双向对应（CIT-CHK-001/003）。

**只检测不自动改**的地方：题名 sentence case。自动转换会把 `China`、`GDP`、`ICT`
一起降成小写，比不改更糟，所以只报"12 条题名仍是 Title Case"，让人确认。

**动手改这里的顺序建议**：先跑 `python cite_check.py <稿件.md> apa` 看现状 →
改 `refs.record()` 的字段清洗 → 再看分流是否误判（`_match_dataset` / `_named` 都可单独调用验证，
不联网）→ 最后才动阈值。

### 3.7 检索不稳怎么办（三级兜底 + 本地缓存）

学术 API 没有一个是稳的：OpenAlex 偶发 429/5xx，Semantic Scholar 无 Key 时几乎全程 429。
**我们不换掉 OpenAlex**（它的 `cited_by_count` 供相关性打分、`primary_location.source.type`
供过滤预印本，Crossref 给不了），而是在它前后各加一层：

```
search(query, per_page)
   ├─ ① litcache.get("merged", …)     命中 → 毫秒级返回，不发请求
   ├─ ② _search_openalex()            主源，字段最全
   └─ ③ _search_crossref()            兜底，DOI 官方注册机构，稳定性最好
          └─ cr_to_work() 转成 OpenAlex 结构，下游代码完全不用区分来源
```

**三条设计约束，改之前务必看清：**

1. **兜底结果也写进缓存。** OpenAlex 挂掉时 Crossref 的结果会写入 `merged` 键，
   于是 OpenAlex 恢复前的重复检索不必每次都先白等一轮超时。
2. **`cr_to_work()` 只填下游真会用到的字段，缺就留空、不猜。** 两类记录会被直接丢弃：
   - **没有作者**的（Crossref 上真实存在，出版商上传元数据时就没给）。作者是参考文献
     必需项，著录一条无作者的文献属残次品，不如留空让作者手补。
   - `type` 不在 `CR_TYPE` 映射表里的（`posted-content` = 预印本等），保持原样交给
     白名单判「非正式出版物」。**不要为了「多装几条」去放宽映射表。**
3. **熔断靠异常类型，不靠文案。** 两源都挂时抛 `refs.SearchDown`，`assemble()` 用
   `isinstance(e, SearchDown)` 计数，连续 3 次即熔断。早先这里的实现是匹配报错字符串里的
   「OpenAlex 检索失败」——文案一改就静默失效，连续失败时会把几十条检索挨个白等一遍。
   **新增报错分支时不要再回到字符串匹配。**

**缓存（`litcache.py`）**

- 位置 `paths.cache_path()` → 可写数据目录的 `cache/litcache.sqlite3`。
  **绝不能写进 `_MEIPASS`**（打包后只读，会 PermissionError 或静默丢缓存）。
- 只缓存**原始记录列表**，不缓存 `pick()` 的匹配结论——规则改了就现算，不会读到旧判定。
- 键 = `来源|归一化检索词|per_page`，检索词做小写 + 折叠空白（模型两次生成常只差空格大小写）。
- TTL：查到结果 30 天，查不到 3 天（负缓存，否则空词会被反复重查）。
- **所有异常静默降级**：缓存是优化，不能变成新的故障点。
- `litcache.clear()` 可清空；`litcache.stats()` 看条目数。

**验证兜底是否还活着**（不联网也能测）：

```bash
python -c "
import refs, litcache
litcache.clear()
refs._search_openalex = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('模拟挂掉'))
r = refs.search('digital financial inclusion rural households', 8)
print('来源:', {w.get('_source') for w in r}, '条数:', len(r))
"
```

预期输出 `来源: {'crossref'}`。若打印 `{'openalex'}` 或直接抛错，说明兜底链路断了。

---

## 4. 常见改造，从哪下手

### 4.1 加一个模型服务商

1. `llm.py` 的 `PROVIDERS` 加一项：`label / protocol(openai|anthropic) / base_url / models / note / signup`
2. 同文件 `PROVIDER_ORDER` 加 key（控制设置面板顺序）
3. `_HOST_ALIASES` 加域名别名（用户填官网域名时自动纠正）
4. 如果协议既不是 OpenAI 也不是 Anthropic：在 `chat()` 里加分支，并在 `protocol_of()` 里认出来
5. 前端无需改：设置面板按 `/api/meta` 的 `providers` 动态渲染

### 4.2 改判读提示词 / 判读粒度

- 单批判读提示词：`llm.judge_batch()`（每批 10 条，改 `range(0, len(group), 10)` 调批量）
- 整体编排与章节分组：`llm.deep_review()`
- 六阶段引导提示词：`llm._SYSTEM_WORKFLOW` 与各阶段 `_prompt_*` 函数
- 输出结构（三层风险）在 `_summarize()`，前端按 `verdicts[].level` 上色

### 4.3 一键成稿加一步 / 改某一步

1. `oneshot.STEPS` 加 `(key, 中文标题)`
2. `oneshot.STEP_ARTIFACT` 加 `key → 08_xxx.md`
3. 写 `_step_xxx(job, cfg)`，参照现有步骤：取上下文 → `llm.chat()` → 写产物 → `_done()`
4. 在 `_STEP_FUNCS`（`oneshot.py` 末尾的 key → 函数映射表）里注册
5. 前端 `static/app.js` 的步骤渲染按 `status.steps` 动态生成（`osPaint()`），一般不用改；
   若要显示新产物，在 `osArtifacts()` 里加一条

### 4.4 改章节配比 / 字数

`oneshot.SECTION_PLANS`：`genre → [(key, 英文标题, 权重)]`，权重和需为 1，
`abstract` 单独固定字数、不参与配比。字数上下限在 `WORD_MIN` / `WORD_MAX`。

### 4.5 前端加一个输入字段（前后端约定）

1. `index.html` 加控件，`id="s7-xxx"`
2. `app.js` 的 `osCfg()` 里加 `xxx: $("s7-xxx").value`（**这是唯一的提交入口**，
   漏了这步后端永远收不到）
3. `oneshot.normalize_cfg()` 里加默认值与类型收敛（不要信任前端传值）
4. 需要阻断就在 `gate_check()` 加 `add(key, 名称, "fail", 说明)`
5. 要进提示词，加到 `_ctx_block()`；**注意区分「所有步骤都该看」和「只有 method/results 该看」**
   ——数据画像就是后者

### 4.6 升级规则库

把新版本 `skill/academic-writing-v1.1/` 整目录替换即可，代码不用动。
替换后校验：

```bash
python -c "import engine; print(engine.track_stats())"
python -c "import json;print(json.load(open('skill/academic-writing-v1.1/.radar-addon/manifest.json'))['baseline_sha256'])"
```

`.radar-addon/manifest.json` 记录了挂载前 `rules/`、`SKILL.md` 的 sha256。
**规则文件被改动而指纹没更新，视为污染**，`/api/meta` 会报扩展包状态异常。

### 4.7 换推广链接 / 文案

- 推广卡文案与链接：`static/app.js` 顶部 `PROMO` 常量（链接集中一处，便于换邀请码）
- 设置面板里的服务商说明：`llm.py` 的 `PROVIDERS[*].note` / `signup`
- 广告必须保留「推广」标识与「价格以平台实时页面为准」的免责小字——
  这是合规底线，不要为了好看删掉

### 4.8 改导出（`export.py`）前必读的三个坑

这三处都是「以为改好了、导出到 Word 才发现」的类型，改动前后都用真实稿件导一遍核对：

| 坑 | 现象 | 现在的做法 |
|---|---|---|
| **LaTeX 命令漏进 OMML 文本** | Word 公式里出现字面量 `tag1`、`bigl(`、`boldsymbolθ` | `_latex_fixups()` 在转换前预处理：`\tag{1}`→`\qquad\text{(1)}`、去掉 `\bigl/\bigr` 尺寸命令、`\boldsymbol`→`\mathbf`、`\operatorname`→`\mathrm`。**出现新的「公式里夹英文单词」优先查这里** |
| **显示公式不居中** | 独立公式和正文挤在同一个段落里，不是居中块 | `_omml_para()` 包 `m:oMathPara` + `m:jc val="center"`，仅当段落还没有别的内容（`not p.runs`）时才用，否则内联 |
| **标题层级整体错位** | 一个 `\section` 吃掉文章标题，7 个正文章节全变 `\subsection` | `_tex_heading_base()` 判断首个 H1 是文章标题还是第一章（按结构判断，不靠标题文本比对），并由 `title_skipped` 标志位保证只跳过那一个 H1 |

另外两件小事：`_strip_stat_note()` 会剔除稿末「### 生成说明」块（两个导出入口都要调）；图片走 `_resolve_image()`，会试 `/media/`、`uploads/`、绝对路径、项目根目录四种来源。

### 4.9 加一种数据格式 / 调数据推断

**加格式**只动 `dataset.py` 的 `profile_file()` 分派，返回 `(header, rows, meta)` 三件套即可：

```python
elif ext == ".sas7bdat":
    header, rows, meta = parse_sas7bdat(raw)   # 自己实现，或转 csv
```

三个约束别破：

1. **不新增必须安装的依赖**。xls/ods 走本机 LibreOffice（`_convert_to_xlsx` + `_soffice_path`），
   dta/sav/parquet 走 `_via_pandas()`——只在 pandas 恰好存在时借道，没有就给「另存为 csv」的明确指引。
   本地装不上 pandas 是常态，写死 import 会让整个应用起不来。
2. **行数不能说谎**。xlsx 的 `read_only` 模式在迭代前 `max_row` 是 `None`，旧实现读到 2 万行就 break，
   于是 3 万行的表报「20000 行、未截断」。现在边流式读边计数，`total_rows` 是真实值，`truncated` 才可信。
3. **多工作表不能盲取第一页**。`_sheet_score()` 按「宽 / 有数据 / 首行像表头 / 下面有数字」打分，
   再对 data/main/数据 这类页名加分；选中的页与未使用的页都会写进 `warnings`，前端原样展示。

**调推断**看两个函数，都是纯规则、可单测：

| 函数 | 输入 | 输出 | 改它的时候注意 |
|---|---|---|---|
| `_structure(p)` | 画像的列 | `layout` + entity/time/期数/是否平衡 | 面板至少 2 实体 × 2 期且 ≥8 行；时序要 ≥5 期，否则小表会被误判成时间序列 |
| `_signals(p)` | 画像的列 | 方法族信号 + evidence | 每条信号都要能在正文里说清「凭什么」（`evidence` 会原样出现在提示词里） |
| `_suggest(p)` | structure + signals | `track` / `genre` / `reasons` / `confidence` | 没有把握就给 `confidence: "low"`，前端会写「把握不大，自行判断」；猜错比不猜更糟 |

`_TRACK_GENRE` 与前端 `syncGenre7()` 的映射必须一致（basic-science → sci-journal），
改一处要同步另一处，否则「应用建议」后体裁会与主线不匹配。

判定 ID 列是 `_mark_ids()`：**强命名**（`_id` / 代码 / 编号 / stkcd…）直接认定，
**弱命名**（index / code / no）要求唯一率 ≥90%，**形状**（整数、唯一率 ≥95%、量级 ≥100）兜底。
旧实现要求 `type == "text"`，导致 `firm_id` 被当成连续变量给出「均值 1029.5」，
而 `dfi_index` 又因为名字里有 index 被误判成 ID——两头都错。

---

## 5. 不能碰的东西（不变量）

1. **`skill/` 目录是规则源，不是应用代码。**
   应用层只读不写。任何「逻辑不对」都不许改规则文件来迁就代码；
   要补充识别就写在应用层（`engine.py` 已有先例：中文复合标题的展示层补充识别，
   不改命中、不改规则）。

   **唯一的破例（v1.2.8，用户明确授权）**：`skill/.../scripts/topic_radar.py`
   的 `mailto` 从假邮箱 `research@example.com` 改成真实联系方式。理由是它直接决定
   能不能进 OpenAlex 的「礼貌池」，属运维参数、不涉规则判定。破例的边界要守住：
   **`rules/` 与 `references/` 一个字都不许动**（规则指纹 `rules.yaml=0b9aa8fe`、
   `detectors.yaml=5724c3f3` 是校验锚点），`scripts/` 只允许改这类外部服务的联系方式与
   接口地址。改完必须复核指纹：

   ```bash
   for f in skill/academic-writing-v1.1/rules/*.yaml; do sha256sum "$f" | cut -c1-8; done
   # 必须是 0b9aa8fe 与 5724c3f3
   ```
2. **产出英文期刊稿优先。** `language=zh` 是受限通道，默认 `en`、引用默认 APA；
   中文题名会自动英译（`oneshot.translate_title()`）。改提示词别把这条弄反。
3. **不编数据、不造文献。** 缺数据写 `[TBD: ...]` 占位；文献由 `refs.py` 从
   OpenAlex / Crossref 拉真实条目并校验白名单。任何「让模型补一个合理数字」的改动都是红线。
   兜底源只能**换成另一个真实注册库**，不许拿模型生成的书目顶上。

   **v1.3.0 起，参考文献改为「先建库、再写作」**，这条不变量的落实方式随之改变：
   - `refs.build_library()` 在成稿**之前**按题目+大纲建库（`oneshot._step_draft` 开头），
     库内每条都过 `whitelist_problems()`（必须有 DOI、正式出版物、非仓储预印本）。
   - 正文只准写库内编号 `[n]`，由 `oneshot._resolve_library()` 解析。**不要退回
     「写完正文再按 `[CITE:]` 描述去猜」的老路**——实测那条路上一条文献会被
     4 个不同位置同时命中，或者把「Akerman et al. (2015)」配成一篇青少年研究。
   - 越界编号一律标 `[TODOFIX: ...]` 交给人，**不许落回关键词检索去补一篇**：
     那等于把模型编的编号洗成看起来合规的引用，比留空更糟。
   - 同一篇文献全文最多复用 `pick()` 里的 `MAX_REUSE=2` 次。放宽这个值前先看
     `06_refs.md` 的「引用高度集中」告警。
   - 参考文献表只列**正文真正引用过**的条目（APA/IEEE 都不列未引文献）。
   - `refs.pick()` 的领域词校验（`_METHOD_WORDS` 剔除后的交集）也不许删：
     它拦的是「术语重合但主题无关」，删了就会重新出现筋膜论文挂在感官评审句后。
4. **产物是工作稿，不是成品。** UI 与 README 都这么承诺，不要改文案成「一键出可投稿论文」。
   **AI 生成内容带水印，禁止直接使用**——这是合规要求，不是提示文案的修辞：
   平台侧导出/转存的副本可能含可见或不可见的 AI 标记（水印、隐写标识、元数据），
   转 PDF、截图、复制粘贴均无法去除，带标记的稿件投稿会被期刊 AI 检测判为代写。
   落实位置（改动时要同步，漏一处就算回归）：
   - 页面：`static/index.html` 的 `#osAiWatermark`（一键成稿页顶部）与能力边界条目
     `bound-aiwatermark`；
   - 结果区：`static/app.js` 的 `AI_WATERMARK_HTML`，由 `osDone()` 注入成稿结果；
   - 导出：`/api/export` 的 `ai_generated` 字段（`server.py` 的 `AI_WATERMARK_MD/TEX`），
     前端本地生成的 md 用 `AI_WATERMARK_MD` 补齐；
   - **新增任何 AI 产出类结果时，必须登记进 `AI_RESULT_KEYS`**，否则导出会静默丢警示。
   验证脚本：`python _verify_watermark.py`（25 项，含反例：普通阶段不得带警示）。
   - **正文里不许出现流水线内部提示**（`Plot type:` / `Required inputs:` / `Status:`）。
     这些是给作者的待办，写进正文会让读者看到 "author to choose" 这种口吻。
     由 `oneshot._scrub_internal_notes()` 在 `_assemble()` 里统一剥离，画法要点
     改由 `_figure_todos()` 汇总到稿末「待补图表」。新增此类内部标签时记得加进
     `_FIG_INTERNAL_RE`。
5. **密钥只走 `.env` 或前端设置。** 不许写进 README、日志、示例文件、记忆文件。
6. **地址必须到 `/v1` 为止。** `normalize_base_url()` 已处理官网域名误填与端点尾巴；
   新增服务商时别绕开它。
7. **数据不全只诊断，不伪造（正文）。** `[TBD: ...]` 是正文里唯一允许的「缺数据」表达方式。
   不许插补缺失值、不许把外部检索到的二手数字自动写进正文表格。
   `dataset.gap_report()` 只返回结构判断。
   **唯一的例外是 `demo` 档**：`demo_preview.md` 里的模拟值必须同时满足三层隔离——
   ① 独立文件（绝不进 `manuscript.md`）② 每个值带 `*` + 文件头 `SIMULATED` 水印
   ③ 不参与 refs/check/计数。任何让模拟值渗进正文的改动都是红线。
   `datasource.py` 的代下载只碰白名单公开源，落盘后不解析、不写回画像；授权/付费站一律拒绝。
8. **路径必须经 `paths.py`。** 不许在新代码里写 `Path(__file__).resolve().parent`
   去拼 `static/`、`skill/`、`uploads/`、`.env`。打包后 `__file__` 指向只读的
   `_MEIPASS`，这样写的代码在源码模式下完全正常、打出来的 exe 里静默失效
   （最典型的症状：规则库 393 条变成 0 条，而 `/api/meta` 依然返回 200）。
9. **用户数据与程序分离。** 安装器把数据放在 `%LOCALAPPDATA%\PaperMate`，
   卸载只删程序目录。不许让安装器或卸载器去动用户数据目录，
   也不许把 `uploads/` 改回程序目录——那会让用户升级一次丢一次稿子。

---

## 6. 已知问题 / 建议下一步

| 项 | 现状 | 建议 |
|---|---|---|
| **出稿质量只做过单题实测** | 真实 Key 跑通 1 单 3000 词（7 步全 done，约 234s，5 表 58 行 / 2 图占位 / 5 公式块），链路与格式已验证；不同学科、不同体裁的质量分布未评测 | 用 3–5 个不同 track 的题目各跑一单，人工评分（结构完整性/术语准确性/文献相关性）后再定付费档 |
| 任务不持久化 | `JOBS` 在内存，重启丢任务；产物在磁盘不丢 | 若要多用户，先换 SQLite + 后台队列；单进程内存模型撑不住并发 |
| 无鉴权、无多用户 | 本地单人使用，`127.0.0.1` 绑定 | 要上公网必须先加登录 + 限流 + 密钥服务端托管（现在前端可填 key，等于把 key 放在浏览器） |
| 长任务无退避重试 | 模型 5xx 直接失败该步 | 给 `llm.chat()` 加 2–3 次指数退避，仅 429/5xx 重试 |
| 推广链接是通用 UTM | 没绑定具体邀请码 | 换成你的专属链接，改 `static/app.js` 的 `PROMO` 一处即可 |
| `_exports/` 无清理策略 | 导出文件一直累积 | 加定时清理或改成流式下载不落盘 |
| 前端无构建、无测试 | 手写 JS，靠 headless 截图回归 | 若要长期维护，考虑抽一层轻量构建 + Playwright 冒烟 |

---

## 7. 验收脚本（改完跑一遍）

```bash
# 语法
python -m compileall -q *.py && node --check static/app.js && echo "syntax ok"

# 规则库可加载、统计正常
python -c "import engine; s=engine.track_stats(); print(s)"

# 前置检查两分支：无题必阻断、有题应通过
python -c "
import oneshot
base={'track':'quant','genre':'quant','level':'journal','language':'en','citation':'apa','words':7000,'data':'no'}
g=oneshot.gate_check(base); print('无题 ok=',g['ok'],'| fatal=',(g['fatal'] or ['—'])[0][:40])
g2=oneshot.gate_check(dict(base,title='Digital Financial Inclusion and Firm Investment Efficiency: Evidence from County-Level Firms'))
print('有题 ok=',g2['ok'],'| 检查项=',len(g2['checks']))"

# 地址归一化（12 组常见误填）
python -c "
import llm
for u in ['www.lumdatech.com','api.lumdatech.com/chat/completions','https://api.deepseek.com/v1/chat/completions','www.anthropic.com','https://api.anthropic.com/v1/messages']:
    print(f'{u:50s} -> {llm.normalize_base_url(u)[0]}')"

# 真实模型连通（需要 .env 里的 key；只查 /models，不花 token）
curl -s -X POST http://127.0.0.1:8000/api/llm/test -H "Content-Type: application/json" -d '{}'

# 图表自检（不调模型，纯文本）
python -c "
import oneshot
man='''## Results

**Table 1.** Main
| a | b |
| --- | --- |
| 1 | 2 |

**Table 1.** Again
| a | b |
| --- | --- |
| 1 | 2 |

As Table 4 shows.
'''
print(oneshot._assets_audit(man))"

# 数据体检（三种典型缺口：小样本 / 正常面板 / 多表无键）
python -c "
import dataset
a=b'firm,year,roa\nA,2020,0.1\nA,2021,0.2\nB,2020,0.3\nB,2021,\nC,2020,0.5\n'
rows=['firm_id,year,treat,post,roa,size']
[rows.append(f'F{i},{y},{i%2},{(y>=2021)*1},{0.05+0.001*i},{10+i}') for i in range(30) for y in range(2019,2023)]
for tag,items in [('小样本',[(a,'a.csv')]),
                  ('面板',[('\n'.join(rows).encode(),'p.csv')]),
                  ('多表',[(b'id,v\n1,2\n', 'm.csv'),(b'code,l\n9,x\n','e.csv')])]:
    g=dataset.gap_report(dataset.profile_files(items)); print(tag, g['level'], g['counts'])"
# 期望：小样本 risk、面板 ok、多表 risk（2 行样本）+ join 警告
# 注意：数值列若是常数，会额外触发「变量变异」警告，这是检查在起作用，不是 bug

# 数据源荐引（联网；断网时应降级为白名单条目而不是报错）
python -c "
import datasource
r=datasource.suggest('Digital transformation and corporate green innovation: evidence from Chinese firms')
print(r['terms'], r['counts']); print([i['kind'] for i in r['items']])"

# LaTeX 导出修正（tag / 尺寸命令 / boldsymbol）
python -c "
import export
print(export._latex_fixups(r'\boldsymbol{\theta} \tag{1} \bigl( x \bigr)'))"
# 期望：\mathbf{\theta} \qquad\text{(1)} ( x )
```

一键成稿不要用真实 key 反复跑全流程（贵且慢）。开发期建议起一个本地假模型：

```bash
# 任意 OpenAI 兼容 mock，监听 127.0.0.1:8123，返回固定 JSON 即可
# 然后在设置里把地址填 http://127.0.0.1:8123/v1
```

---

## 8. 打包/交付说明

交付有两条路，按对象选：

| 路线 | 产物 | 给谁 |
|---|---|---|
| **A. 安装包** | `dist_installer\PaperMate-Setup-<ver>.exe`（68 MB） | 普通用户（不需要 Python） |
| **B. 源码包** | `academic-writing-agent-<ver>.tar.gz` | 二次开发者 |

下面先讲 A（对外分发的主路径），再讲 B。

---

### 8.1 路线 A：安装包（v1.2.7 起）

```bash
# Windows 双击即构建；脚本会依次检查 Python / PyInstaller / Inno Setup
build_installer.bat

# 等价于手动两步
python -m PyInstaller --noconfirm --clean PaperMate.spec   # -> dist\PaperMate\（141 MB）
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" PaperMate.iss  # -> dist_installer\（68 MB）
```

**打包机前置**：Python 3.10+、`pip install pyinstaller`、Inno Setup 6
（`winget install JRSoftware.InnoSetup`）。语言文件已随包放在 `installer/`，
不依赖 Inno 安装目录——官方包已不再自带简体中文，从外部路径引用会让别人的机器编译失败。

#### 关键设计：只读资源 vs 可写数据

打包后 `__file__` 指向 `sys._MEIPASS`（只读、每次升级会变），而本应用同时需要两类路径。
`paths.py` 就是为这件事存在的，**任何新代码都不要直接写 `Path(__file__).parent`**：

| 类别 | 取法 | 打包后位置 | 典型文件 |
|---|---|---|---|
| 只读资源 | `paths.resource_root()` | `<安装目录>\_internal\` | `static/`、`skill/` |
| 可写数据 | `paths.data_root()` | `%LOCALAPPDATA%\PaperMate\`（靠 `<安装目录>\datahome.txt` 告知，见下） | `uploads/`、`_oneshot/`、`.env`、`cache/` |

搞反的后果是具体的：`uploads` 写进 `_MEIPASS` → 装到 Program Files 后 `PermissionError`；
`skill` 从数据目录读 → 升级后规则库失联，393 条规则静默变成 0 条。

**安装版怎么知道该用 `%LOCALAPPDATA%`：靠 `<安装目录>\datahome.txt`，不是环境变量。**

`data_root()` 优先级：`PAPERMATE_DATA_DIR` 环境变量 > `datahome.txt` > exe 同级 `data/`（绿色版）。

用文件而非环境变量，是因为用户可能从开始菜单、桌面快捷方式、或直接双击 exe 启动，
后两种拿不到安装时设的环境变量。v1.2.7 就是踩了这个坑：安装器建了 `%LOCALAPPDATA%\PaperMate`
却没说给程序，数据全落进程序目录，**卸载或覆盖升级会连同稿件一起删掉**。

`datahome.txt` 由 `PaperMate.iss` 的 `CurStepChanged(ssPostInstall)` 写入。
**静默安装后必须验证它存在**——这是"升级不丢稿"的唯一保障。

#### 为什么是 onedir 不是 onefile

1. onefile 每次启动都要把 141 MB 解包到临时目录，冷启动常 10s+，用户会以为没反应；
2. onefile 的 `_MEIPASS` 每次运行都换路径，杀软更容易重复扫描、更容易误杀；
3. `skill/` 规则库需要稳定落盘，onedir 天然满足。

#### 体积排除（`PaperMate.spec` 的 `EXCLUDES`）

实测各包体积：`pymupdf` 105.6 MB、`numpy` 51.5 MB、`onnxruntime` 45.7 MB。
`ingest.py` 只用 `pymupdf.open()` + `get_text()`，**不需要版式模型**，
所以排除 `pymupdf_layout` / `pymupdf4llm` / `onnxruntime` / `numpy` / `pandas`。
排除后 PDF 解析实测正常（见 8.3 验收清单）。

**加新依赖时**：若被误排除，表现为"源码能跑、exe 报 ImportError"。
先看启动日志有没有 `ModuleNotFoundError`，再从 `EXCLUDES` 里去掉该模块重新构建。
`uvicorn` 的子模块必须用 `collect_submodules` 显式收集——它走 importlib 动态加载协议实现，
静态分析看不到，漏了会在启动后立刻退出且不打报错。

#### 安装器做了什么（`PaperMate.iss`）

- **用户级安装**（`PrivilegesRequired=lowest`），装进 `%LOCALAPPDATA%\Programs\PaperMate`，全程不弹 UAC。
  学术用户多为学生/老师，机房和单位电脑常常拿不到管理员。
- **环境体检页**（`[Code]` 段的 `BuildEnvReport`）：系统版本 / 位数 / 内存 / 磁盘 / 目录可写 /
  端口 / 旧版进程 / VC++ 运行库。硬性项不满足直接拦下并说清原因，软性项只提示。
- **数据与程序分离**：程序在 `Programs\PaperMate`，数据在 `%LOCALAPPDATA%\PaperMate`。
  `[UninstallDelete]` 只删程序目录，**卸载不删用户稿子**。
- `MinVersion=10.0` + `ArchitecturesAllowed=x64compatible`：内置 Python 3.13 需要 Win10+ 64 位，
  低于这个版本装上也跑不起来，不如安装前就拦住。

**改 `[Code]` 段时踩过的三个坑**（都是编译期就报错的，不是运行期）：

1. `Exec()` 的出参是 `Integer` 退出码，不能直接传给 `Boolean` 的 `Result`（报 `Type mismatch`）；
2. `StringChange` 在 Inno Pascal 里是**过程**（原地改第一个参数），不是函数（报 `Variable Expected`）；
3. `FileExists` 只认文件，对目录**永远返回 False**——判断目录可写必须真的写一个探针文件。
   这条曾导致所有用户都被误判成"用户目录不可写"而拦住安装，是最值得记住的一个。

---

### 8.2 路线 B：源码包

本包由项目根目录按白名单打包，排除项见 `.gitignore` 与本文第 0 节。
包内附 `PACKAGE_MANIFEST.txt`：逐文件大小与 sha256，可用来确认交付完整。

**新增顶层文件时记得同时改打包脚本的 `ROOT_FILES`**（`%TEMP%\pack_papermate.py` 是打包脚本，
不在包内；`env_check.py` 就是这样漏过一次的候选）。

```bash
# 0) 交付前先跑：环境是否齐全（退出码 0 才算可交付）
python env_check.py

# 校验交付完整性
python -c "
import hashlib,pathlib
bad=0
for line in open('PACKAGE_MANIFEST.txt',encoding='utf-8'):
    if not line.strip() or line.startswith('#'): continue
    h,size,path=line.rstrip('\n').split('  ',2)
    p=pathlib.Path(path)
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=h: print('MISS/DIFF',path); bad+=1
print('ok' if not bad else f'{bad} 个文件不一致')"
```

---

### 8.3 交付前必须做的验收

#### (1) 源码模式（改依赖或启动逻辑后必做）

```bash
python -m venv /tmp/clean && /tmp/clean/bin/python -m pip install -r requirements.txt
/tmp/clean/bin/python env_check.py          # 必须退出码 0
/tmp/clean/bin/python server.py             # 起得来、横幅不报 [缺]
```

然后跑一遍 `xlsx 上传`、`PDF 上传`、`导出 docx`——覆盖 `openpyxl` / `PyMuPDF` /
`python-docx` 三条最容易被漏掉的依赖路径。

#### (2) 打包模式（每次发包必做）

**必须在一台没有 Python 的机器上验**，或者用干净 PATH 模拟：

```bash
# 把 dist\PaperMate 拷到独立目录，然后清掉 PATH 里的 Python
env -u PYTHONPATH -u PYTHONHOME PATH="/c/Windows/system32:/c/Windows" \
  PAPERMATE_PORT=8131 PAPERMATE_NO_BROWSER=1 ./PaperMate.exe
```

逐条确认（v1.2.7 已全部实测通过）：

| # | 检查 | 期望 |
|---|---|---|
| 1 | `GET /api/meta` | `version` 正确、`features` 11 项齐全 |
| 2 | `GET /` 与 `/vendor/mathjax/tex-svg.js` | 200，2.2 MB 正常下发 |
| 3 | `POST /api/review/lexical`（喂有意写坏的文本，≥500 词） | `applicable_rules=56`、`auto_checked=30`、`defect_count>0` 且规则 ID 正常 |
| 4 | `POST /api/oneshot/data`（传 csv） | 返回 `id/rows/cols` + `gap` 体检 |
| 5 | `POST /api/export`（docx / tex） | docx 约 37 KB、tex 约 600 B |
| 6 | `POST /api/ingest`（传 pdf） | `markdown` 含原文，`warnings` 有"仅提取文字层" |
| 7 | 首次启动的 `data/` | 自动生成 `.env` + `uploads/` + `_oneshot/` |
| 8 | `PAPERMATE_DATA_DIR` 指向别处 | 数据全部落到指定目录 |
| 9 | **安装后 `<安装目录>\datahome.txt` 存在** | 内容是 `%LOCALAPPDATA%\PaperMate`；启动后 `.env` 和 `uploads/` 生成在那里，**程序目录下没有 `data/`** |
| 10 | 安装 → 启动 → 卸载 | 程序目录删净、`%LOCALAPPDATA%\PaperMate` 保留（含 `.env`） |
| 11 | `skill` 指纹 | `rules.yaml` = `0b9aa8fe`、`detectors.yaml` = `5724c3f3` |

第 3 条是最关键的：它是"`skill/` 是否真的被打进包里并且能执行"的唯一证明。
只看 `/api/meta` 返回 200 不够——`meta` 里的统计是 `engine.py` 读 YAML 得到的，
而真正的检测器是 `skill/.../scripts/score.py`，走 `importlib` 动态加载，路径错了才暴露。

第 9 条是 v1.2.8 新增的：**数据目录静默指错不会报错，只会在用户升级时表现为"稿件全没了"**，
必须显式验。

> 静默安装在 Git Bash 里会因参数转义失败而"退出码 0 但没装上"，
> 请用 PowerShell 的 `Start-Process` 传参（见下），别在 bash 里拼 Windows 路径：
>
> ```powershell
> Start-Process -FilePath "dist_installer\PaperMate-Setup-1.2.8.exe" -Wait -PassThru `
>   -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=`"D:\test\PM`""
> ```

> 验收时若沙箱/公司网络有 HTTP 代理，后台启动的服务访问外网会 502，
> 表现为"下载数据源失败"。加 `NO_PROXY=127.0.0.1,localhost` 后正常——这是环境问题，不是代码问题。

