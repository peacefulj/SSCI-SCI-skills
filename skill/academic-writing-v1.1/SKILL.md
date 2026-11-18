---
name: "academic-writing"
version: "1.3.0"
description: "学术论文写作决策、结构与审查助手。支持五条学科主线：工程/AI（会议与期刊）、定量实证（经济/管理/金融/社会学）、预测建模与数据科学、质性研究（案例/现象学/扎根理论）、基础科学与临床（含 EQUATOR 报告规范）。识别学科与体裁后加载对应规范并执行投稿前审查。含选题雷达（OpenAlex 发文趋势 + AI 三维评估）。不适用于纯理论数理（定理-证明型）论文。"
---

# Academic Writing（学术论文写作技能包）

v1.3.0（2026-11-12）。在 v1.0.0 的四体裁链路之上，新增**四条学科主线**、**报告规范层**、**引用格式层**与**选题雷达**（OpenAlex 趋势 + AI 三维评估）；规则库 393 条（138 条带示例），检测器 95 个。

## 能力范围（先看这一节，避免误用）

| 学科主线 | track | 支持度 | 规则数 |
|---|---|---|---|
| 工程 / AI（EI、AI 会议；工程类 SCI） | `ei-conf` `ai-conf` | ✅ 完整 | 113 |
| 定量实证（经济/管理/金融/社会学定量） | `quant` | ✅ 完整 | 56 + 共用 |
| 预测建模 / 数据科学 | `predictive` | ✅ 完整 | 25 + 16（报告层） |
| 质性研究（案例/现象学/扎根理论/民族志） | `qualitative` | ✅ 完整 | 41 |
| 基础科学实验（化学/生物/材料/物理） | `basic-science` | ⚪ 次要线，未做真实全文校验 | 24 |
| 临床与医学 | `clinical` | ⚪ 次要线，未做真实全文校验 | 32 |
| 博士大论文 | `dissertation` | ✅ 完整 | 15 + 共用 |
| **纯理论数理（数学/理论物理/理论经济）** | — | ❌ **不支持** | — |

### 关于校验强度（不同线的可信度不同）

- **定量实证 / 质性研究**：已用 **12 篇真实发表论文全文**（PLoS ONE 六篇定量、ERIC 六篇质性）做过校验，平均 4.9 处命中、1.5 处硬伤；高频命中项（缺参与者编号、未报访谈时长、未报共同支撑、固定效应局限未讨论）经逐条核对均为论文真实缺陷。这是本技能可信度最高的两条线。
- **工程/AI**：规则成熟但 `score.py` 下缺少检测器，目前主要靠人工按 `signal` 核对。
- **基础科学 / 临床**：规则已建但**未做真实全文校验**，作为次要线保留，不宣称同等可靠。

### 关于不支持的领域（重要）

**纯理论数理类论文（definition–theorem–proof 结构）不在本技能支持范围内。** 原因：全库 `section` 枚举基于 IMRaD（摘要/引言/方法/实验/结果/讨论），理论文章没有"实验"与"结果"章节，硬套会产生系统性误判（例如追问题证明文"你的消融实验呢"）。

遇到此类稿件应当**明确告知用户不支持**，不要勉强套用规则。若确有需求，需另建一套 `theory` section 词表与规则族，属独立工作量。

### 关于基础科学的边界

`basic-science` 覆盖 **IMRaD 通用层 + 统计报告 + 出版规范**（Day & Gastel 9e、Montgomery DOE）。**不覆盖**领域表征标准：ACS Style Guide、IUPAC 命名、晶体学 CIF、行业特定惯例等。遇到具体表征参数问题，须提示用户核对目标期刊作者指南，不要凭空给出领域标准。

## 工作流程（五步）

1. **识别 track** —— 判断学科主线（上表）
2. **识别体裁** —— 会议 / 期刊 / 大论文 / 报告
3. **识别阶段** —— 选题 / 设计 / 初稿 / 修改 / 投稿 / 返修
4. **加载规范 + 执行动作**
5. **脚本自检 + 输出风险清单**

## 第一步：识别 track 与体裁

先按学科定 track，再按体裁定 genre。二者组合决定加载哪套 playbook。

| 用户描述线索 | track | 加载 |
|---|---|---|
| 会议投稿、rebuttal、双盲、页码限制 | `ei-conf` / `ai-conf` | references/genre-ei-conference.md |
| 期刊 IMRaD、cover letter、多轮返修 | `sci-journal` | references/genre-sci-journal.md |
| 观测数据、识别策略、内生性、DID/IV/RDD | `quant` | references/genre-quant-empirical.md |
| 预测、建模、训练集测试集、AUC、过拟合 | `predictive` | references/genre-quant-empirical.md 第五节 + evidence-and-data.md |
| 访谈、编码、主题、饱和、案例、田野 | `qualitative` | references/genre-qualitative.md |
| 材料、表征、XRD、样品、实验条件 | `basic-science` | references/genre-sci-journal.md |
| 临床试验、CONSORT、注册、受试者 | `clinical` | references/reporting-guidelines.md |
| 大论文、章节、盲审、答辩 | `dissertation` | references/genre-dissertation.md |

**跨线情形**：混合方法研究须 `quant` 与 `qualitative` 各过一遍，并在方法章说明两股数据如何整合；因果与预测并存时须区分"解释性模型"与"预测性模型"的目标。

## 第二步：识别阶段

| 阶段 | 用户典型描述 | 动作 |
|---|---|---|
| 选题 | "做什么方向""值不值得做" | 走选题雷达三步：定范式/层级 → 跑 OpenAlex 趋势 → AI 三维评估（详见下方"选题环节"） |
| 设计 | "这样设计行不行" | 按 track 校验识别策略/抽样/实验设计 |
| 初稿 | "帮我写引言""写结果" | 按 playbook 逐段生成引导 |
| 修改 | "帮我看看""改得怎么样" | 按 rules.yaml 逐条审查 |
| 投稿 | "要准备什么" | 产出投稿包清单（含报告规范清单） |
| 返修 | "怎么回审稿意见" | 产出 rebuttal 结构 |

## 第三步：执行

| 要做的事 | 读哪个文件 |
|---|---|
| 选题环节（选题雷达） | `references/topic-selection.md` |
| 选题评分维度（6 范式 × 5 层级） | `references/topic-scoring-dimensions.md` |
| AI 选题评估提示词模板 | `assets/topic-prompts.md` |
| 目标期刊/会议清单（下拉数据源） | `assets/target-venues.yaml` |
| 定量实证全流程 | `references/genre-quant-empirical.md` |
| 质性研究全流程 | `references/genre-qualitative.md` |
| 临床报告规范选型与自查 | `references/reporting-guidelines.md` |
| 数据质量/效度/因果/可复现 | `references/evidence-and-data.md` |
| 逐句写作（引言/方法/结果/讨论） | `references/section-*.md` |
| 引用格式（四套） | 见下方"引用格式路由" |
| 书源与规则对应关系 | `references/book-index.md` |
| 新增规则怎么写 | `references/conversion-template.md` |
| 完整使用教程（安装/场景/脚本/二次开发） | `使用教程.md` |

规则筛选方式：`rules/rules.yaml` 每条含 `genre`（体裁）与 `track`（学科线），按两者交集取规则。

## 选题环节（选题雷达，v1.3.0 新增）

用户在"做什么方向 / 值不值得做"阶段时，走三步，详见 `references/topic-selection.md`：

1. **定范式与层级** —— 确认 track（定量实证/工程技术/医学/质性/基础科学/理论）+ 层级（本科/硕士/博士/期刊/一般研究）
2. **跑 OpenAlex 全球发文趋势** —— `python scripts/topic_radar.py "检索词"`（中文主题须转英文），按三档判读：>20% 升温 / −20%~20% 平稳 / <−20% 回落
3. **AI 三维评估** —— 按 `assets/topic-prompts.md` 拼装提示词，输出 3 候选题 + 三维打分（新颖性/可行性/数据·材料可得性）+ 数据文献清单 + 风险

**评分维度随范式与层级变化**：三维维度名固定，但每维的评价关切随 6 范式（`evalFocus`）与 5 层级（`innovation` 标尺）动态切换，标准在 `references/topic-scoring-dimensions.md`。

**目标期刊/会议**：`assets/target-venues.yaml` 提供 6 范式各一份清单（含中英文与分区标注），agent 据此引导用户下拉选择；用户可自定义。

## 第四步：自检（两个脚本，用途不同）

### 结构检查（快速、单文件）

```bash
python scripts/check_structure.py manuscript.txt --genre quant
```

支持 `--genre`: `ei-conf | ai-conf | sci-journal | ssci | dissertation | quant | predictive | qualitative | basic-science | clinical`
输出：必需章节缺失项 + 该 track 的关键词面项（识别策略/编码方法/报告规范/伦理等）。

### 批量打分（按规则逐条判定）

```bash
python scripts/score.py manuscript.txt --track quant
python scripts/score.py --suite tests/samples --manifest tests/manifest.yaml
```

输出：命中缺陷数、命中规则 id、自动检查条数、需人工核对条数。

**能力边界（必须如实告知用户）**：全库 393 条规则中，**95 条**登记了词面检测器可自动判定（分 must/should/nice 三级），其余为"需人工核对"。规则条目自带 `example_bad` / `example_good` 的可直接作为改写范例引用。脚本输出会明确报出 `manual_only` 数量，不得把脚本结果表述为"已通过全部规则审查"。

## 缺陷分级（输出必须分层，不得一律称"缺陷"）

`score.py` 把命中分为三级，报告时必须分开说：

| 级别 | 含义 | 报告口径 |
|---|---|---|
| `must` 硬伤 | 方法有效性、数据诚信、伦理、引用基线；不改会被拒或无法复核 | "硬伤 N 处" |
| `should` 建议 | 规范性与可读性；不改会被要求大修 | "建议 N 处" |
| `nice` 可选 | 优良实践，领域内多数论文未做到（如负面案例、预注册标注） | "可选 N 处" |

**真实论文基准**：12 篇已发表论文平均 4.9 处命中、**1.5 处硬伤**（v1.2.0 复核值）。若你的输出对一篇正常论文报出 5 处以上硬伤，先怀疑自己判读有误。

## 正文与参考文献分离（重要）

`score.py` 自动在正文后半段最后一次出现的 References / 参考文献标题处截断，避免文献题名污染判定（否则参考文献里的 "case study" 会让一篇非案例研究被要求"给证据链"）。引用格式类检测器标 `scope: references`，仍在全文上运行。

## 第五步：输出风险清单

按严重度分三层：

1. **硬伤**（会被直接拒稿）：无识别策略、无报告规范、伦理缺失、因果语言误用、数据泄漏
2. **结构性缺陷**（会被要求大修）：假设未论证、无反例、无稳健性、无饱和判据
3. **呈现问题**（影响可读性）：表格不规范、数字无参照、引文无编号

## 引用格式路由（四套，按学科与投稿语言选一套）

| 你的情况 | 用哪个文件 |
|---|---|
| 工程（计算机/电子/机械/土木），投 IEEE 会议或期刊 | `assets/citation-ieee.md` |
| 心理/教育/管理/社会学，投 SSCI 或 APA 系期刊 | `assets/citation-apa.md` |
| 中文期刊、中文学位论文、国内会议 | `assets/citation-gb7714.md` |
| 人文、历史、部分社科（脚注制） | `assets/citation-quickref.md` |

**一套稿件只用一套体系**。正文用 `[1]` 编号而文末按字母序排列，是最常见的中英混排错误（CIT-STY-001）。
规则库中 CIT 族共 16 条，覆盖体系一致性、IEEE 编号顺序与作者格式、APA 第 7 版变化（去出版地、DOI 加 https）、GB/T 7714 文献类型标识与引用日期。

## 硬性约束

- 规则必须可判定；给具体改法，不说"注意逻辑清晰"这类空话
- 每条建议须能追溯到 `rules.yaml` 的 `source`
- 学术诚信：只做引导与审查，不改写原文代投
- **不虚构**：书源未覆盖的领域标准（ACS/IUPAC 等）须提示用户外查，不得凭记忆给出
- **不越界**：理论数理类论文明确声明不支持
