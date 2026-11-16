# 书源与规则索引（book-index）

> 用途：agent 定位"某个问题该查哪本书哪一章"；维护者定位"改某条规则该核对哪本书"。
> 规则数为该来源贡献的条目数（含跨体裁复用），合计 393 条；其中 138 条附 `example_bad` / `example_good`。

## 一、按学科主线

### 工程 / AI（`ei-conf` `ai-conf`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Zobel, *Writing for Computer Science* | 3e (2014) | 53 | ch.3 贡献判定、ch.5 引言与常见病、ch.14 实验 |
| Day & Gastel, *How to Write and Publish a Scientific Paper* | 9e | 63 | ch.7 标题、ch.9 摘要、ch.11 材料方法、ch.12 结果、ch.13 讨论 |
| Glasman-Deal, *Science Research Writing* | 2e | 0（见 section-*.md） | Unit 1–4 句子功能位 |
| Huyen, *Designing Machine Learning Systems* | — | 5 | 数据工程与漂移 |

### 定量实证（`quant`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Imbens & Rubin, *Causal Inference for Statistics, Social, and Biomedical Sciences* | 2015 | 17 | ch.1 潜在结果与估计量、ch.12 非混杂分配、ch.13 倾向得分、ch.14 重叠、ch.15–16 匹配与修剪、ch.21–22 敏感性分析、ch.23–25 工具变量与不依从 |
| Huntington-Klein, *The Effect* | 2e (2026) | 10 | ch.5 识别、ch.6–9 因果图与后门/前门、ch.10 处理效应 |
| Cunningham, *Causal Inference: The Mixtape* | v1.7 | 5 | ch.5 IV、ch.6 RDD、ch.9 DiD、ch.10 合成控制 |
| Angrist & Pischke, *Mostly Harmless Econometrics* | 2009 | 5 | ch.2 选择偏误、ch.3 CIA/OVB、ch.8 聚类 |
| Angrist & Pischke, *Mastering 'Metrics* | 2015 | 6（v1.2.0） | ch.1 §1.1 随机试验的平衡与流失、ch.2 §2.1–2.3 CEF 与 ceteris paribus、ch.3 §3.1–3.2 工具变量与 LATE、ch.4 §4.1 RDD 可视化、ch.5 §5.1–5.2 DiD 时间轨迹 |
| Morgan & Winship, *Counterfactuals and Causal Inference* | 2e (2015) | 4（v1.2.0） | ch.2 §2.7 naive 估计的偏误、§2.8 时变处理、ch.8 §8.1/8.3 非可忽略与异质性、ch.11 §11.3 面板与固定效应局限 |
| Gelman, Hill & Vehtari, *Regression and Other Stories* | 2020 | 5（v1.2.0） | ch.2 §2.4 率的标准化、ch.4 §4.5 显著性的误用、ch.6 §6.3 系数是比较而非效应、ch.10 §10.3 交互项、ch.11 §11.3–11.6 残差诊断与 R² |
| Pearl, *Causal Inference in Statistics: A Primer* | 2019 | 4 | ch.2 DAG 与对撞、ch.3.3 后门准则 |
| Pearl & Mackenzie, *The Book of Why* | 2018 | 2（v1.2.0） | ch.1 因果层级、ch.8 反事实、ch.9 中介（DAG 内容已由 Primer 来源的 QNT-DAG 条目覆盖，不重复计入） |
| Shadish, Cook & Campbell | 2002 | 2 | 四类效度威胁 |

### 预测建模与报告层（`predictive` `reporting`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Kuhn & Johnson, *Applied Predictive Modeling* | 2013 | 24 | ch.2 建模流程 p.19、ch.3 预处理 p.27、ch.4 过拟合与调参 p.61、ch.5 回归性能 p.95、ch.11 分类性能 p.247、ch.16 类别不平衡 p.419、ch.18 变量重要性 p.463、ch.19 特征选择 p.487、ch.20 影响性能的因素 p.521 |
| James et al., *ISLR* | 2e | 辅助 | ch.5–6 重采样与正则化 |
| Miller, *The Chicago Guide to Writing about Numbers* | 2e (2015) | 18 | ch.2 七原则、ch.3 因果与实质显著性、ch.5 数量比较、ch.6 表格、ch.7 图、ch.10 数据与方法 |
| Haque, *Feature Engineering & Selection for Explainable Models* | 2024 | 0（非经典教材，仅备查） | — |

### 质性研究（`qualitative`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Saldaña, *The Coding Manual for Qualitative Researchers* | 1e (2009) | 7 | ch.1 编码与编码本 p.13–27、ch.2 分析性备忘录 p.32、ch.3 第一轮编码 p.45、ch.4 第二轮编码 p.149 |
| Miles, Huberman & Saldaña, *Qualitative Data Analysis* | 3e (2014) | 16 | ch.2 设计、ch.3 伦理、ch.4 分析基础、ch.5 矩阵与网络、ch.7 描述方法、ch.11 结论验证、ch.12 写作 |
| Yin, *Case Study Research and Applications* | 6e | 10 | ch.1 何时用案例、ch.2 设计、ch.4 证据收集与证据链、ch.5 分析、ch.6 报告 |
| Smith, Flowers & Larkin, *Interpretative Phenomenological Analysis* | 2e | 4 | ch.2 理论（双重诠释）、ch.3 规划、ch.5 分析、ch.9 质量评估 |
| Creswell & Creswell, *Research Design* | 6e | 13 | 研究设计与目的陈述 |
| Graff & Birkenstein, *They Say / I Say* | 5e | 11 | ch.3 引文三明治、ch.5 声音标记、ch.6 反方、ch.10 元评论 |
| Booth et al., *The Craft of Research* | 5e | 20 | ch.5–9 论证（claim/reason/warrant）、ch.13–14 引言 |

### 基础科学（`basic-science`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Day & Gastel | 9e | 见上（复用） | ch.11 p.71–75 材料与测量、ch.12 p.77–79 数值与补充材料、ch.13 p.81–84 讨论与局限、ch.16 表 p.101、ch.17 图 p.109、ch.32 SI 单位 p.230 |
| Montgomery, *Design and Analysis of Experiments* | 8e | 6 | ch.1–2 重复/随机化/区组 |

### 临床与医学（`clinical`）
| 来源 | 版本 | 贡献规则 |
|---|---|---|
| CONSORT 2025 | 30 项 | 14 |
| STROBE | 22 项 | 5 |
| PRISMA 2020 | 27 项 | 5 |
| STARD 2015 | 30 项 | 3 |
| EQUATOR Network 目录 | — | 5 |
| ICMJE 建议 | — | 2 |

> 临床线的来源是**公开报告规范**而非书，条目号可直接核验（如 CONSORT 第 9 项分配隐藏、第 13a 项流程图）。

### 博士大论文（`dissertation`）
| 书 | 版次 | 贡献规则 | 主要章节 |
|---|---|---|---|
| Evans, Gruba & Zobel, *How to Write a Better Thesis* | 3e | 15 | ch.2 四段骨架、ch.4 写作顺序、ch.5 引言与 aim、ch.7 贡献、ch.9 讨论、ch.10 结论、ch.12 答辩 |

## 二、30 本书全量对账（book-to-skill 覆盖状态）

判定口径：**A 产出规则**＝至少 1 条可判定规则进入 `rules.yaml`；**B 转非规则产出**＝知识落在 `assets/` 或 `references/` 的模板/句式位；**C 排除**＝不入库并写明原因。重复文件（同一本书的 pdf/epub/分章抽取）按一本计。

| # | 书 | 状态 | 规则/产出 | 备注 |
|---|---|---|---|---|
| 1 | Imbens & Rubin 2015 | A | 17 | 潜在结果与估计量、PSM、IV |
| 2 | Angrist & Pischke, *Mostly Harmless Econometrics* | A | 5 | 选择偏误、聚类 |
| 3 | Angrist & Pischke, *Mastering 'Metrics* | A | 6 | v1.2.0 补齐 |
| 4 | Morgan & Winship 2e | A | 4 | v1.2.0 补齐 |
| 5 | Huntington-Klein, *The Effect* 2e | A | 10 | 识别策略、因果图 |
| 6 | Cunningham, *The Mixtape* | A | 5 | IV/RDD/DiD/SCM |
| 7 | Pearl, *Primer* | A | 4 | DAG、后门 |
| 8 | Pearl & Mackenzie, *The Book of Why* | A | 2 | v1.2.0 补齐（层级/反事实/中介） |
| 9 | Gelman, Hill & Vehtari, *Regression and Other Stories* | A | 5 | v1.2.0 补齐 |
| 10 | Shadish, Cook & Campbell 2002 | A | 2 | 效度威胁 |
| 11 | Kuhn & Johnson, *Applied Predictive Modeling* | A | 24 | 建模流程与性能 |
| 12 | Huyen, *Designing ML Systems* | A | 5 | 数据工程与漂移 |
| 13 | Miles, Huberman & Saldaña | A | 16 | 矩阵、编码、验证 |
| 14 | Saldaña, *Coding Manual* | A | 7 | 两轮编码 |
| 15 | Yin, *Case Study Research* | A | 10 | 证据链、案例边界 |
| 16 | Smith et al., *IPA* | A | 5 | 双重诠释、超级主题 |
| 17 | Creswell & Creswell, *Research Design* | A | 13 | 设计类型与目的陈述 |
| 18 | Booth et al., *The Craft of Research* 5e | A | 20 | 论证与引言 |
| 19 | Graff & Birkenstein, *They Say / I Say* | A | 11 | 引文三明治、反方 |
| 20 | Miller, *Writing about Numbers* | A | 18 | 数字、表、图 |
| 21 | Zobel, *Writing for Computer Science* | A | 53 | 工程/AI 主线 |
| 22 | Gastel & Day, *How to Write and Publish* 9e | A | 63 | 基础科学主线 |
| 23 | Montgomery, *Design and Analysis of Experiments* | A | 6 | 重复/随机化/区组 |
| 24 | Evans, Gruba & Zobel, *How to Write a Better Thesis* | A | 15 | 学位论文骨架 |
| 25 | NASEM, *Reproducibility and Replicability* | A | 部分 | 入 QNT-RPT / QNT-SEN |
| 26 | McGilvray, *Executing Data Quality Projects* | A | 部分 | 入 QNT-RPT-004 |
| 27 | Turabian, *A Manual for Writers* | B | `assets/citation-*` | 芝加哥式引用规范 |
| 28 | Glasman-Deal, *Science Research Writing* | B | `references/section-*.md` | 句子功能位模板 |
| 29 | James et al., *ISLR* 2e | B | 辅助 | 重采样与正则化背景，规则已由 Kuhn 覆盖 |
| 30 | Bolker, *Writing Your Dissertation in 15 Minutes* | C | — | MOBI 无法解析且属写作心理类，无可判定规则 |

> v1.2.0 之前的对账缺口是第 3、4、8、9 四本（贡献 0 条）。本版已按同一套五步法补齐，并同步补上 `example_bad` / `example_good`（全库 138 条，覆盖 quant/predictive/qualitative/reporting 四条在测线）。

## 三、未进入规则库的书（备查，不影响判定）

| 书 | 原因 |
|---|---|
| Turabian, *A Manual for Writers* | 仅用于 assets/citation-quickref.md |
| Bolker, *Writing Your Dissertation in 15 Minutes a Day* | MOBI 无法解析，属进度心理类，不入规则 |
| McGilvray, *Executing Data Quality Projects* | 部分入 DAT 规则 |
| NASEM, *Reproducibility and Replicability* | 部分入 REP 规则 |
| Haque, *Feature Engineering* | 非领域经典教材，仅备查（属第 31 项，未列入 30 本对账） |

## 四、已知缺口（诚实清单）

1. **化学/材料/生物领域表征标准**：ACS Style Guide、IUPAC 命名、晶体学规范均未收录，`basic-science` 只到通用层。
2. **理论数理**：无任何书源，且 section 枚举不兼容，明确不支持。
3. **中文学位论文/中文期刊规范**：已补 GB/T 7714—2015 速查（`assets/citation-gb7714.md`）；句式模板仍基于英文写作书，中文行文风格未适配。
4. **Vancouver（医学）引用格式**：仍未收录；IEEE 与 APA 第 7 版已补（`assets/citation-ieee.md`、`citation-apa.md`）。
5. **质性报告规范**：COREQ/SRQR 只在 QLT 规则中引用条目数，未附完整清单。

补齐建议见 `references/conversion-template.md` 与 CHANGELOG 的"下一步"。
