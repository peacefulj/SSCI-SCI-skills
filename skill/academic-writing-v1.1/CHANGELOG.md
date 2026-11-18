# CHANGELOG

## v1.3.1（2026-11-18）检测器作用域校准

依据 40 篇真实论文重标注（63 条 must 命中：真缺陷 17 / 无缺陷 12 / 规则不适用 21 / 待定 13）校准检测器，只动 `rules/detectors.yaml`，规则库不变：

- 新增 `not_when`（命中即判 na）：`QNT-IDF-001/002`（横断面/关联设计自述、方法学教程）、`SCI-ETH-001`（纯酶学/微生物/重组蛋白）、`CLN-PRI-001/003`（报告质量元研究、指南制定/声明、Delphi）、`QLT-DSN-003/DSP-003/ETH-001/TRU-001/CAS-001`（论述性方法论文）。带 `not_when` 的检测器 15 → 25。
- 放宽 patterns：`SCI-MET-004` 认 `±`/`SD`/`triplicate`/`SigmaPlot`/`GraphPad` 等；`QLT-DSP-003` 认括号内参与者代号（`[GP 1]`、`(MNS, FG6)`）与参与者特征表行首代号（`HP6 GP …`）；`CLN-ETH-002` 认 `availability of data`、`data are available`、`on reasonable request`。
- 结果：40 篇语料 must 命中 63 → 43；真缺陷 17/17 全保留，误报（无缺陷+不适用）33 → 14；`tests/manifest.yaml`（39 份样稿）与 `manifest_real.yaml`（12 篇）逐份 defect 数改前改后完全一致。
- 剩余误报交由 PaperMate「结合审查」的大模型全文复核处理。

## v1.3.0（2026-11-12）

### 选题环节：移植研墨平台「选题雷达」

本版补齐 skill 一直缺失的**选题能力**（此前 SKILL.md 只有一句"选题 → 产出研究问题 + gap 论证"），移植自研墨平台 v1.10.0 工作台的「选题雷达（OpenAlex 全球发文趋势 + AI 三维评估）」。

新增文件：

| 文件 | 类型 | 内容 |
|---|---|---|
| `references/topic-selection.md` | 文档 | 选题三步法：定范式/层级 → 跑趋势 → AI 三维评估；趋势三档判读、gap 论证标准、输出物清单 |
| `references/topic-scoring-dimensions.md` | 文档 | 评分维度矩阵：6 范式 `evalFocus` × 5 层级 `innovation` 标尺，三维固定、标准随范式/层级变 |
| `assets/topic-prompts.md` | 文档 | AI 选题评估提示词模板：通用骨架 + 6 范式片段 + 5 层级片段 + 完整拼装示例（移动支付与农户创业） |
| `assets/target-venues.yaml` | 数据 | 目标期刊/会议清单：6 范式各一份，含中英文名与 CCF/SCI/SSCI 分区标注，作"下拉"数据源 |
| `scripts/topic_radar.py` | 脚本 | OpenAlex 趋势拉取（标准库 urllib）+ 文本柱状图 + 增长率三档判读 + 小样本防护 |

设计决策（与用户确认）：
- **形态**：规则/数据资产 + 可选脚本；LLM 评估由 agent 按提示词模板完成（不内嵌 API key，符合 skill 纯资产架构）
- **评分维度**：三维固定（新颖性/可行性/数据·材料可得性），评价标准随范式（evalFocus）与层级（innovation）切换——忠实还原研墨
- **期刊下拉**：做成清单数据文件而非 HTML 控件（skill 是给 agent 用的）

验证：`topic_radar.py` 实测可跑通 OpenAlex（"digital finance" 拉出 2021→2025 逐年量，正确排除未完成的 2026 年），小样本主题自动加"增长率仅供参考"提示。

### 文档同步

- `SKILL.md`：新增"选题环节（选题雷达）"小节，第二步阶段表、第三步执行表补选题入口
- `使用教程.md`：新增"场景 0 选题雷达"，目录结构补 3 个新文件

---

## v1.2.0（2026-11-11）

### 补齐 4 本欠梳理书目（+17 条规则）

上一版对账发现 30 本里 4 本贡献 0 条。本版按同一套五步法（可判定性测试 → 归类 → signal → fix → 元数据）逐本梳理：

| 书 | 新增 | 条目 |
|---|---|---|
| Angrist & Pischke, *Mastering 'Metrics* (2015) | 6 | QNT-MM-001..006 — 随机试验平衡/流失、控制变量选择、平均 vs 个体、单调性与依从类型、RDD 可视化、DiD 时间轨迹 |
| Morgan & Winship 2e | 4 | QNT-CFT-001..004 — naive 估计偏误、时变处理、固定效应局限、异质性效应 |
| Gelman, Hill & Vehtari, *Regression and Other Stories* (2020) | 5 | QNT-REG-001..005 — 系数是比较而非效应、显著性≠重要性、残差诊断、交互项解读、率的标准化 |
| Pearl & Mackenzie, *The Book of Why* (2018) | 2 | QNT-WHY-001..002 — 反事实陈述须声明模型、机制声称须中介分析 |

合计 376 → **393 条**。为什么只给 Book of Why 记 2 条：其 DAG/对撞/后门内容已由 `QNT-DAG-001..005`（Pearl, *Primer* 来源）覆盖，重复计入会虚增规则数。

### 规则配 example_bad / example_good（0 → 138 条）

上一版最实的缺口是示例字段为空，规则只能靠抽象 signal 判断。本版给 **quant 56 / qualitative 41 / predictive 25 / reporting 16** 四条在测线的全部规则各配一正一反例句（与用户界定的"只做定量实证 + 质性研究"范围一致，clinical 与 basic-science 暂留空）。示例写在 `_dev/fragments/frag_ex_*.yaml`，由 `_dev/_merge_v120.py` 注入。

### 检测器修了三类真问题

1. **历史转义 bug**：`(?-i:\\bXXX\\b)` 在文件里被写成 `(?-i:////bXXX////b)`，30 处短缩写检测器（DiD/IV/LATE/PSM/SMD/SD/CV/F1/ROC/RCT/OR/RR/HR/NNT）**从未真正生效**。修复后这些规则第一次可按缩写命中。
2. **QLT-WRT-002 非法正则** `（“){3,}`：在 `score.py` 的 `except re.error` 里被静默跳过，改为合法模式。
3. **新检测器精度校准**：`December22` 里的 "r2"、DiD 交互项被当作调节效应、把控制变量清单里的 "unemployment rate" 当率值比较——分别用词边界、`not_when` 与转人工核对修掉；`QNT-MM-004`（单调性）、`QNT-CFT-004`（异质性）、`QNT-REG-005`（率的标准化）判定依赖语境，不设检测器。

检测器 86 → **95 个**（must 39 / should 34 / nice 22）。

### 复验结果

- 构造样稿 39 份：**全部落在预期区间**（好 0–1 / 中 3–7 / 坏 7 以上）。
- 真实论文 12 篇：平均 **4.9 处**命中、**1.5 处硬伤**（v1.1.3 为 4.4 / 1.5）。新增命中共 6 处，逐条核对均为真缺陷：4 篇用单位/双向固定效应但未讨论时变混杂，2 篇以 R²/OLS 作拟合主证据而无残差诊断。

### 文档

- `references/book-index.md`：新增"30 本书全量对账"表（25 A 产出规则 / 3 B 转非规则产出 / 2 C 排除），book-to-skill 覆盖状态可一眼核对。
- `SKILL.md`：版本、条数、真实论文基准同步；能力边界写明示例字段可直接引用。

## v1.1.3（2026-11-11）

### 真实语料扩至 12 篇

定量 6 篇（PLoS ONE，CC BY）+ 质性 6 篇（ERIC 全文）。全部开放获取、已通过同行评议，`tests/manifest_real.yaml` 可复跑。

结果：平均 4.4 处命中、**1.5 处硬伤**（定量 1.0 / 质性 2.0），12 篇全部落在 [0,8]，无系统性误伤。

### 新增严重度分层

检测器加 `severity: must|should|nice`（39/25/22），`score.py` 分组统计与打印。原因：原先把"未做负面案例分析"与"无识别策略"同样计为缺陷，真实论文动辄 7–10 处命中，报告失去区分度。

### 正文与参考文献分离

新增 `body_only()`：在正文后半段最后一次出现的 References/参考文献标题处截断。修掉两类误报——参考文献题名里的 "case study" 触发案例研究规则、题名里的 "as cited in" 触发转引规则。引用类检测器标 `scope: references` 走全文。

### 规则体裁错配修正

`QNT-SEN-003`（预设/探索性标注）在 6/6 篇量化论文上触发——该规则源自临床/实验规范，经济学观测研究普遍不预注册。降为 `nice`。

### 检测器表述扩充

- QNT-IDF-001 补 `use … as an instrument`
- QNT-IDF-002 补 6 类论证句式（"serves as a valid instrument since"、"parallel trends were established"、"related to X but unrelated to Y" 等）
- QLT-COD-002 降级（Braun & Clarke 反式主题分析不要求编码本）

### 修复

`score.py` 批量表格的"硬伤"列误用循环外变量，每行显示同一数值。

### 回归

39 份构造样稿：全部仍在预期区间。

---

## v1.1.2（2026-11-11）

### 用真实发表论文全文做校验（回应"能否找到文章校验"）

此前只用 3 篇 arXiv **摘要**做误报复检，样本层级不足。本轮取**开放获取全文**：

- 定量实证：PLoS ONE 18(7): e0288901（time-varying DiD，CC BY 4.0，~2,470 词）
- 质性研究：ERIC ED681590 全文 PDF（codebook thematic analysis，28 页，~11,300 词）

均为已通过同行评议的正式发表论文。

**结果**：定量线命中 3 处、质性线命中 2 处，逐条核对原文后**全部是论文真实缺陷**（未报标准误与聚类、子群未校正多重比较、未标预设/探索、未报伦理审批、无负面案例），**未出现误伤**。

### 修掉 7 个检测器误报

| 规则 | 问题 | 修正 |
|---|---|---|
| QNT-IDF-001 | 只认 "identification strategy" | 补 identifying assumption / quasi-natural experiment |
| QNT-IDF-002 | 假设论证句距限制 40 字符过短 | 放宽至 240 字符且跨行 |
| QNT-PSM-002 | 不认 "common value test"（共同支撑的中式英译） | 补 common value |
| QNT-EST-005 | 不认百分比幅度 | 补 "boost growth by 4.0%" 类句式 |
| QLT-DSN-003 | 不认 snowball sampling（合法非概率抽样） | 补 snowball/convenience/quota |
| QLT-DSP-001 | 对所有质性研究要求矩阵 | 改为仅案例研究/跨案例时要求 |
| QLT-SAT-002 | 过宽（见 transcript 即通过）→ 后又过窄 | 收紧为需 lasted/averaging/each interview 上下文 |

### 分层标注可信度

SKILL.md 新增"关于校验强度"小节：定量实证与质性研究为**已做真实全文校验**的主线；工程/AI 规则成熟但缺检测器；基础科学与临床为**未校验的次要线**，不宣称同等可靠。

### 回归

39 份构造样稿：**全部仍在预期区间**。

---

## v1.1.1（2026-11-11）

### 新增引用格式层（四套并存）

补齐 v1.1.0 遗留的最大缺口——引用格式原先只有 Turabian/Chicago，工程与中文投稿无法用。

| 文件 | 依据 | 适用 |
|---|---|---|
| `assets/citation-ieee.md` | IEEE Reference Guide | 工程、计算机、电子、机械、土木；IEEE 会议/期刊 |
| `assets/citation-apa.md` | APA Publication Manual 7th ed. | 心理、教育、管理、社会学；SSCI |
| `assets/citation-gb7714.md` | GB/T 7714—2015 | 中文期刊、中文学位论文、国内会议 |
| `assets/citation-quickref.md` | Turabian/Chicago（原有，改为路由入口） | 人文、历史、部分社科 |

关键差异已逐条写明：APA 第 7 版**取消出版地**、DOI 须写成 `https://doi.org/`；IEEE 的 DOI 反而**不加** https 前缀、作者"缩写在前"、编号按出现顺序；GB/T 7714 必须带**文献类型标识**（`[M]`/`[J]`/`[D]`/`[EB/OL]`）且电子文献**必须给引用日期**。

### 新增 CIT 规则族（16 条）

CIT-STY-001/002（体系一致性、由期刊指南决定）、CIT-IEEE-001~004、CIT-APA-001~004、CIT-GBT-001~004、CIT-CHK-001/002。
规则总数 **360 → 376**。

### 检测器

新增 4 个（CIT-GBT-001 文献类型标识、CIT-GBT-004 引用日期、CIT-IEEE-004 DOI 写法、CIT-CHK-002 转引），并支持 `track: null` 表示**全局检测器**（对所有 track 生效）。检测器总数 **82 → 86**。

### score.py 改进

- 支持全局检测器（`track: null`）
- 文本量偏小（约 <500 词，疑似仅摘要）时输出**明确提醒**：require 类命中多为缺章节所致，不代表真实缺陷
- 避免把"摘要"当"全文"判为大量缺陷

### 真实语料与中文引用验证（新增 `tests/real/`）

- 3 篇真实 arXiv 摘要（Decision Transformer、PaI 综述、DeepMimic，逐字提取）：**禁用类检测器 0 处误报**。
- 中文引用格式双向测试：`gbt7714_ok.md` 的 CIT 检测器 0 命中；`gbt7714_bad.md` 准确命中 CIT-GBT-001（缺类型标识）与 CIT-GBT-004（缺引用日期）。

### 回归

39 份验收样稿仍**全部落在预期区间**，无回归。

---

## v1.1.0（2026-11-11）

### 新增学科主线（4 条）

- **`quant` 定量实证线**：39 条规则（QNT-*），来源 Imbens & Rubin (2015)、Huntington-Klein *The Effect* 2e、Cunningham *The Mixtape*、Angrist & Pischke、Pearl、Shadish。
  覆盖估计量定义、识别策略、DAG 与控制集、倾向得分/匹配、工具变量、DiD/RDD/合成控制、敏感性分析、报告规范。
  新增 playbook：`references/genre-quant-empirical.md`（含识别策略四句式模板与三类设计的专用句式）。
- **`predictive` 预测建模线 + `reporting` 报告层**：25 + 16 条规则，来源 Kuhn & Johnson *Applied Predictive Modeling*、ISLR、Miller *Writing about Numbers* 2e。
  覆盖数据切分与泄漏、重采样与嵌套调参、过拟合、性能指标、变量重要性、特征选择、类别不平衡、三线表与图规范、效应量报告。
- **`qualitative` 质性研究线**：41 条规则，来源 Saldaña 编码手册、Miles & Huberman *QDA* 3e、Yin *Case Study* 6e、Smith et al. *IPA* 2e。
  覆盖设计传统、编码与编码本、数据展示矩阵、可信度四标准、饱和判据、案例证据链、IPA 双重诠释、COREQ/SRQR。
  新增 playbook：`references/genre-qualitative.md`。
- **`basic-science` 基础科学线**：24 条规则，来源 Day & Gastel 9e、Montgomery DOE。
  覆盖标题/摘要/引言/材料方法/结果/讨论、图表、SI 单位、伦理与作者资格。
  **明确边界**：不含 ACS/IUPAC 等领域表征标准。
- **`clinical` 临床报告规范线**：32 条规则，依据 EQUATOR 公开规范（CONSORT 2025 30 项、STROBE 22 项、PRISMA 2020 27 项、STARD 2015 30 项、ICMJE）。
  新增 `references/reporting-guidelines.md`（设计→规范选型表 + 最易漏项清单 + 投稿动作清单）。

### 规则库

- 183 → **360 条**，无重复 id，全部含 `rule`/`source`/`signal`/`fix`。
- `section` 取值归一：`methods`(4) 合并进 `method`，消除 v1.0 遗留的 `method`/`methods` 并存问题。
- 新增字段 `track`（quant/predictive/qualitative/basic-science/clinical/reporting），与 `genre` 正交：`genre` 管体裁，`track` 管学科线。

### 工程层

- 新增 `rules/detectors.yaml`：**82 个词面检测器**，把可自动判定的规则映射为正则，支持 `require` / `forbid` / `require_when` / `forbid_when` 四种语义，以及 `not_when` 作用域排除。
- 新增 `scripts/score.py`：单文件打分 + 批量验收（manifest 驱动），输出命中规则 id、自动检查数、**需人工核对数**（诚实报告覆盖率）。
- 重写 `scripts/check_structure.py`：支持 10 种 `--genre` 路由（含中英文章节标题识别），新增 quantitative / qualitative / basic-science / clinical 四处专项检查。
- 新增 `references/book-index.md`：书源→track→规则数→章节的索引，含"已知缺口"诚实清单。

### 验收

- 39 份样稿（四条主线各 9 份 + 基础科学 3 份），好/中/坏各档命中数**全部落在预期区间**。
- 校准过程修复 6 类真实缺陷：短缩写忽略大小写误命中（`DiD`→"did"）、CONSORT 作用域错误、模式过窄、Markdown 标题干扰、检测器覆盖不足、好档自身不完整。
- 详见 `tests/REPORT.md`。

### 明确不支持

- **纯理论数理（definition–theorem–proof）论文**：section 枚举基于 IMRaD，硬套会产生系统性误判。已在 SKILL.md 中声明不支持，避免误导用户。

### 遗留缺口（诚实清单）

1. 基础科学缺领域表征标准（ACS/IUPAC/CIF）。
2. 引用格式只有 Turabian/Chicago，缺 IEEE / APA / Vancouver / GB/T 7714。
3. 中文期刊与中文学位论文规范未适配。
4. 好档为构造样稿，建议用真实论文替换后重跑。
5. 自动覆盖率 22.8%，其余需人工核对。

---

## v1.0.0（2026-11-09）

初版：183 条规则，四条体裁链路（EI/AI 会议、SCI 期刊、SSCI 期刊、博士大论文）+ 证据与数据审查链路。
