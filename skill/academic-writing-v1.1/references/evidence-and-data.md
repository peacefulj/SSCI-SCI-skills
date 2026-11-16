# 证据与数据审查清单（Evidence & Data）

用途：回答"数据能不能用、结论站不站得住"。AI/工程博士最关心的两类问题——（1）自己的私域数据 + 多模型实验是否可信；（2）方法是否站得住。
每条按「signal 查什么 → fix/action 怎么做 → source」组织。source 标书名 + 章 + 可见页码，可回溯。

## 投稿前数据自检 Top 10

| # | 自检问题 | 不合格的表现（signal） | 对应节 |
|---|---|---|---|
| 1 | 训练/验证/测试集是否明确划分、无泄漏？ | 只有一个数据集、或划分方式未写、或在测试集上调参 | §1 §6 |
| 2 | 数据质量六维度是否报过数（缺失率、唯一性、时效、一致性）？ | 只有样本量，无缺失率/重复/字段口径说明 | §1 |
| 3 | 是否做了随机化/分组/重复，种子写没写？ | 无对照组、无种子、无重复次数、模型间无法公平比较 | §2 |
| 4 | 结论是否对 confounder/collider/selection bias 做过排查？ | 观测数据直接断言因果，未提任何混杂 | §3 |
| 5 | 多指标/多模型比较是否修正了多重比较？ | 比了 20 个模型却用一个 p<0.05 挑"显著" | §4 |
| 6 | 是否只在训练数据上验证、未做交叉验证/留出集？ | 报告的训练精度=测试精度，明显过拟合 | §4 |
| 7 | 回归/关联是否被误写成因果？ | 用"X 导致 Y"表述一个相关性结果 | §4 |
| 8 | 数据/代码/环境/随机种子是否可复现？ | 无代码、无版本、无种子、无超参、无数据访问说明 | §5 |
| 9 | 是否排查了 train/serve skew 与数据/概念漂移？ | 论文只说"离线效果"，未说明部署后输入分布是否变 | §6 |
| 10 | 标签质量与来源是否交代？ | 用弱标注/规则标注却当金标准报性能，标注者一致性未报 | §6 |

---

## 1. 数据质量（McGilvray）

核心思想：数据质量是"数据能否支撑结论"的地基。McGilvray 给出可度量的维度，实验/数据章节必须报出关键维度的测量值，而不是"我们用了 N 条数据"就完事。

- **signal**：实验数据章节只写样本量/来源，没有任何质量指标的测量值。
  **fix**：至少补报 四个基础维度：completeness（缺失/fill rate）、validity（值是否符合规则）、accuracy（与权威参照是否一致）、uniqueness（有无重复）。每个给 count + percentage。
  **source**：McGilvray, Executing Data Quality Projects 2e, ch.3 (Data Quality Dimensions, p.42), ch.4 (Steps 3.3–3.7, p.133–148)

- **signal**：字段缺失但不懂哪些是必填/可空，无法判断缺失是否合理。
  **fix**：明确每个字段是 required/optional/conditional 并写清条件；必填字段 fill rate 必须 100%，否则解释缺失原因与清洗策略。
  **source**：McGilvray 2e, ch.4 Step 3.3 (Completeness/fill rate, p.133)

- **signal**：重复记录（同一实体多次出现）未去重就统计。
  **fix**：报 uniqueness 检查——按业务键（如 user_id、设备号）查重，说明去重规则（确定性/概率匹配）与去重后规模。
  **source**：McGilvray 2e, ch.4 Step 3.5 (Uniqueness and Deduplication, p.140)

- **signal**：多来源数据（多设备、多表、多时间段）合并后未检查一致性，字段口径可能不同。
  **fix**：报 consistency 检查——同一字段在不同源/不同表中取值是否等价，口径差异说明，合并后一致性百分比。
  **source**：McGilvray 2e, ch.4 Step 3.6 (Consistency and Synchronization, p.146)

- **signal**：数据采集/切片时间未说明，结论可能建立在过期数据上。
  **fix**：报 timeliness——说明数据覆盖的时间窗、更新频率、切片截止时间，判断是否"current and ready for use"。
  **source**：McGilvray 2e, ch.4 Step 3.7 (Timeliness, p.148)

- **signal**：报告了"准确率"但没有说明跟谁比（无权威参照）。
  **fix**：accuracy 必须对"agreed-upon authoritative source"核对；若无私域金标准，如实写"以规则/人工抽检为参照"并给抽检规模。
  **source**：McGilvray 2e, ch.4 Step 3.4 (Accuracy, p.135)

---

## 2. 实验设计（Montgomery）

核心思想：可信的实验结论来自 三个基本设计原则——replication（重复）、randomization（随机化）、blocking（区组），外加足够的 power（功效/样本量）。多模型/私域数据实验同样适用。

- **signal**：只跑一次实验、无重复，或重复但结果方差/置信区间未报。
  **fix**：报 replication（至少多次独立运行），并报均值的变异（标准差/置信区间/多种子箱线），不报单点数值。
  **source**：Montgomery, Design and Analysis of Experiments 8e, ch.1 (randomization & replication principles)

- **signal**：对比多个模型/方法，但数据划分、超参、环境未随机化或未控制，无法公平比较。
  **fix**：固定随机化方案（同一数据划分、同一随机种子、相同预训练/特征），只让被比较的那个因子变化；说明 randomization 做了什么。
  **source**：Montgomery 8e, ch.1 (fundamental principles)

- **signal**：数据里存在明显批次/来源/时间差异，却直接混着比。
  **fix**：用 blocking 控制已知混杂源——把设备、采集批次、时间段作为区组变量，报告区组后的比较。
  **source**：Montgomery 8e, ch.4 (Randomized Complete Block Design, p.139)

- **signal**：多个因子（如模型结构 × 数据增强 × 训练策略）只一个一个单独调。
  **fix**：多因子用 factorial design，报告因子主效应与交互；若资源受限至少说清哪些因子被固定、哪些被扫描。
  **source**：Montgomery 8e, ch.5 (The Advantage of Factorials, p.186)

- **signal**：报告"无显著差异"却从未算过所需样本量/功效。
  **fix**：报 power 分析或至少报效应量 + 置信区间，说明在当前样本量下能检测到多小的差异；样本不足时把"无差异"改写为"未检测到差异"。
  **source**：Montgomery 8e, ch.2.4.3 (Choice of Sample Size, p.44), ch.3.7 (Determining Sample Size, p.105)

- **signal**：全部结论只在单一数据集/单一规模上，无随规模/参数变化的趋势。
  **fix**：在数据规模或关键参数上多点取值，画趋势曲线，说明结论在什么范围内成立。
  **source**：Montgomery 8e, ch.2 (paired comparison / sample size); 参照 Zobel ch.14

---

## 3. 效度与因果（Shadish + Pearl + Angrist）

核心思想：因果结论要过四关——statistical conclusion validity（统计推断对不对）、internal validity（因果联系成不成立）、construct validity（测得的是不是想测的构念）、external validity（能不能推广）。观测数据或建模类论文，还要用 DAG 排查 confounder/collider/mediator 与 selection bias。

- **signal**：论文没区分"相关性结论"与"因果结论"，也没自评四类效度威胁。
  **fix**：先说清结论属于哪类因果强度；量化/实证论文至少要逐条排查 internal validity 与 construct validity 威胁并写控制措施。
  **source**：Shadish, Cook & Campbell, Experimental and Quasi-Experimental Designs for Generalized Causal Inference (2002), ch.2 (validity types), ch.3 (threats)

- **signal**：internal validity 威胁（history/maturation/selection/regression 等）完全没讨论，尤其存在自选择或时间趋势的数据。
  **fix**：列出主要内部效度威胁（至少覆盖 selection、history/maturation、attrition），逐一说明用随机化/对照/同期测量等手段如何排除。
  **source**：Shadish et al. 2002, ch.2; 原型见 Campbell & Stanley 八类威胁

- **signal**：观测数据（无随机化）直接断言"X 导致了 Y"，未画因果图、未列 confounder。
  **fix**：画 DAG，标出 confounder（X 与 Y 的公共原因）、collider（勿条件于它）、mediator（勿过度调整）；用 back-door criterion 确定调整集。
  **source**：Pearl, Causal Inference in Statistics: A Primer (2019), ch.2 (chains/forks/colliders), ch.3.3 (Backdoor Criterion, p.61)

- **signal**：条件于某个变量后反而出现了"悖论"关联（如 Simpson 悖论）或选择性纳入造成伪相关。
  **fix**：检查是否条件于了 collider（或其后代）；移除对 collider 的调整，改为调整真正的 confounder。
  **source**：Pearl, A Primer, ch.2.3 (Colliders, p.40–41)

- **signal**：实验组/对照组非随机形成（用户自选、按阈值入选），存在 selection bias。
  **fix**：承认并量化 selection bias 方向与符号；用识别策略（IV、DiD、RD、natural experiment）或至少 selection-on-observables（CIA）+ 稳健性说明因果识别到何种程度。
  **source**：Angrist & Pischke, Mostly Harmless Econometrics, ch.2 (Selection Bias, p.12–15), ch.3 (CIA), ch.4–6 (IV/DiD/RD)

- **signal**：把"模型/特征与结果的关联"当成"该特征是原因"（如"使用了 X 特征所以性能好"）。
  **fix**：区分"预测性关联"与"干预性因果"；对特征只做预测性能声明，因果声明单独用干预/反事实语言并配识别策略。
  **source**：Angrist & Pischke, ch.3.2 (Omitted Variables Bias, p.44); Pearl ch.1 (association ≠ causation)

---

## 4. 统计陷阱（Gelman）

核心思想：p 值、显著性、拟合度都会在多模型/多比较场景下被"玩坏"。核心纪律：预先注册分析、控制 researcher degrees of freedom、用留出/交叉验证校准过拟合。

- **signal**：对多组比较（多指标、多模型、多数据集）未做任何多重比较修正，就挑出"显著"的那个。
  **fix**：统一报告所有比较的 p 值与置信区间，做多重比较修正（Bonferroni/FDR），或把分析转为效应量 + 置信区间为主、显著性为辅。
  **source**：Gelman et al., Regression and Other Stories, ch.11.8 (p-hacking & forking paths; multiple comparisons)

- **signal**：p-hacking/forking paths 迹象——分析路径明显跟着数据走，或报"研究者自由度"（随时改划分/改指标/改清洗来凑显著）。
  **fix**：预注册分析计划（指标、划分、清洗、模型数先定死）；报告多少条"研究者自由度"被尝试过；或做 multiverse/敏感性分析展示结果对这些选择的稳健性。
  **source**：Gelman et al., Regression and Other Stories, ch.11.8 (researcher degrees of freedom)

- **signal**：训练精度≈测试精度且都异常高，或模型在训练数据上反复调参后才报告同一数据上的表现。
  **fix**：用真正留出的测试集或交叉验证评估，报告 out-of-sample 误差；用 AIC/LOO-CV 等校正过拟合。
  **source**：Gelman et al., Regression and Other Stories, ch.11 (overfitting, cross-validation)

- **signal**：用回归系数/相关性直接写"X 导致了 Y"。
  **fix**：把相关/回归表述改为"关联""预测"，因果声明另配识别策略或干预设计；必要时加"correlation does not imply causation"限定。
  **source**：Gelman et al., Regression and Other Stories, ch.19 (Using correlation and assumptions to infer causation)

- **signal**：加了交互项/非线性变换却不报、不做诊断，或模型越复杂 R² 越高就当作更好。
  **fix**：报模型诊断（残差图、变换说明）；比较复杂模型时用交叉验证/信息准则而非拟合度；说明为什么选这个变换与交互。
  **source**：Gelman et al., Regression and Other Stories, ch.11–12 (model checking & transformations)

---

## 5. 可复现性（NAS）

核心思想：区分 两个不同概念——reproducibility（同一数据+同一代码得到一致结果，= 计算可复现）与 replicability（新数据重做得到一致结论）。论文可复现的最低门槛是数据、代码、环境、随机种子、provenance 全交代。

- **signal**：只给结论，无代码/数据访问、无版本号、无随机种子、无超参、无环境说明。
  **fix**：公开代码与数据（或说明不可公开原因），固定依赖版本、随机种子、超参、硬件环境，使他人能用同一输入重跑出同一结果。
  **source**：NASEM, Reproducibility and Replicability in Science (2019), ch.3 (Definitions, p.42), ch.4 (Reproducibility, p.55–70)

- **signal**：processing/pipeline 的中间步骤不可追溯，无法知道每张表、每个数字怎么来。
  **fix**：建立 provenance——记录每步输入/输出/脚本/参数，做到"任一数字都能回溯到原始数据与生成代码"。
  **source**：NASEM 2019, ch.4 (Inadequate Recordkeeping / Nontransparent Reporting, p.67–69)

- **signal**：混淆"我跑通了"（可复现）与"别人重新做也得到同样结论"（可复制），把单一结果当稳健结论。
  **fix**：明确声明本文属于可复现还是已复制；鼓励在独立数据/他人重跑后补充 replicability 说明，没做就写清这是单次结果。
  **source**：NASEM 2019, ch.3 (p.42), ch.5 (Replicability, p.71)

- **signal**：只用单一随机种子报一个数，可能碰巧落在好的那次。
  **fix**：多个随机种子重复运行，报均值与方差/置信区间，结论建立在分布上而非单次运行上。
  **source**：NASEM 2019, ch.4 (precision of measurement / computational reproducibility, p.46)

---

## 6. ML 数据工程（Chip Huyen）

核心思想：ML 论文的"数据可信"还要过泄漏、skew、漂移、标签质量、特征一致性五关。私域数据 + 多模型实验尤其容易在看不见的地方翻车。

- **signal**：评价指标好得反常，或时间相关数据用了随机划分。
  **fix**：排查 data leakage——时间相关数据按时间划分（前段训练、后段测试）；在划分之后再做缩放/归一化/选择特征；检查标签是否"漏"进特征。
  **source**：Huyen, Designing ML Systems, ch.5 (Data Leakage, p.135–140)

- **signal**：训练与服务/上线后的输入分布或特征计算方式不一致（train/serve skew）。
  **fix**：说明训练与推理的特征定义、预处理、采样是否一致；报告部署后的输入分布监控，处理不一致处。
  **source**：Huyen, Designing ML Systems, ch.8 (distribution shifts & monitoring)

- **signal**：未讨论数据漂移/概念漂移——离线好 ≠ 上线好。
  **fix**：区分 covariate shift（P(X) 变）、label shift（P(Y) 变）、concept drift（P(Y|X) 变），说明各自是否可能发生及缓解（重训、监控、回退）。
  **source**：Huyen, Designing ML Systems, ch.8 (Data Distribution Shifts, p.238)

- **signal**：用弱标签/规则标签/自动标签当金标准训练与评估，却不报标注质量。
  **fix**：报告标签来源（手工/自然/弱监督）、标注者数量与一致性（如 IAA）、错误标注如何处理；评估时用人工抽检的干净子集核对。
  **source**：Huyen, Designing ML Systems, ch.4 (Labeling: hand labels / natural labels / lack of labels, p.88–94)

- **signal**：特征在训练与评估/部署间口径漂移，或"加一个特征就涨点"不解释其可复用性。
  **fix**：统一特征定义与抽取管线（feature store/统一预处理），报告特征一致性；对"涨点特征"做特征泛化性评估。
  **source**：Huyen, Designing ML Systems, ch.5 (Engineering Good Features / Feature Generalization, p.141–144)

---

## 与规则库（rules.yaml）的对应

本清单是"背景 + 流程"层，配套的可判定规则已落入 rules.yaml，按前缀分组：

| 本节 | 规则前缀 | 规则数 | 主要触发点（signal 示例） |
|---|---|---|---|
| §1 数据质量 | WRI-DAT | 6 | 只见样本量、无缺失率/重复率/字段口径 |
| §2 实验设计 | WRI-VLD（experiment-design） | 5 | 无重复/无种子/"无显著差异"无 power |
| §3 效度与因果 | WRI-VLD（validity-threat）+ WRI-CCL | 7+6 | 观测数据断言因果却不提 confounder / 未排查内部效度 |
| §4 统计陷阱 | （并入 WRI-VLD/CCL 与既有 WRI-EXP-*） | — | 多比较不修正、过拟合、回归当因果 |
| §5 可复现性 | WRI-REP | 4 | 无代码/无种子/无 provenance |
| §6 ML 数据工程 | WRI-MLD | 5 | 泄漏/漂移/标签质量/特征 skew 未排查 |

用法：审查时先扫"Top 10"快速定位风险，再按命中条目跳回本节细查 signal→fix，最后落到对应 rules.yaml 规则出结构化意见。
genre 规则：数据质量/实验/可复现/ML 规则适用于 [ei-conf, ai-conf, sci-journal]；效度与因果规则适用于 [sci-journal, ssci, dissertation]（量化/实证通用）。