# 定量实证 Playbook（经济 / 管理 / 金融 / 社会学定量）

来源：Imbens & Rubin (2015)、Huntington-Klein, *The Effect* 2e (2026)、Cunningham, *The Mixtape*、Angrist & Pischke, *Mostly Harmless Econometrics*、Morgan & Winship 2e、Miller, *Writing about Numbers*

适用范围：目标期刊为 SSCI 一区/二区或 SCI 社科交叉刊（如 JFE、SMJ、ASR、AER、JBV、RP 等），研究类型为观测数据或准实验。

---

## 一、这类论文的判定标准

审稿人只问四件事，按顺序：

1. **问的问题是否是个因果问题？** 若只是"两者相关吗"，则不需要识别策略，但也别用因果语言。
2. **识别策略是什么？** 即"你凭什么说这是因果"。没有这一句，后面全废。
3. **识别假设可信吗？** 不是"写出来了"，而是"为什么在这个情境下成立"。
4. **结论的稳健性边界在哪？** 换设定、去样本、加混杂，结论还在不在。

**核心心法**：模型不是贡献，识别的变异才是贡献。审稿人不在乎你用了多花哨的估计量，只在乎"你比较的是谁与谁，为什么这个比较是干净的"。

---

## 二、论文骨架（与通用 IMRaD 的差异）

| 章节 | 定量实证的特有要求 | 常犯错误 |
|---|---|---|
| Introduction | 第一段就要给"因果问题 + 识别思路 + 主要结果" | 用三页篇幅讲宏观背景，第四页才出现研究问题 |
| Theory / Hypotheses | 假设须由理论推出，每条假设对应一个可检验的系数符号 | 假设与回归变量对不上号 |
| Data | 来源、时间窗、筛选规则、清洗步骤、描述统计表 | 只写"数据来自 CSMAR" |
| **Identification**（必备独立小节） | 识别策略、变异来源、假设逐条、DAG | 把识别塞进 Method 末尾两句话 |
| Method / Model | 估计量、函数形式、标准误类型、聚类层级 | 只说"we run OLS" |
| Results | 主效应 → 机制 → 异质性 → 稳健性，四段递进 | 稳健性堆 10 个表但没有一个对应具体质疑 |
| Discussion | 结果的经济意义、与最接近文献的对话、外推边界 | 只重申系数显著 |

**章节篇幅配比（经验值）**：Intro 15%、Theory 20%、Data 12%、Identification 12%、Method 8%、Results 20%、Discussion 13%。识别部分低于 8% 通常意味着论证不足。

---

## 三、写作顺序（反直觉但有效）

1. **先写 Identification 小节**——这一节写不出来，说明研究还没准备好，别急着写引言。
2. **再写主结果表**——表定稿后，Results 的文字只是"读表"。
3. **然后写 Data 与描述统计**——确保样本筛选能对上结果表的 N。
4. **再写 Theory 与 Hypotheses**——此时才知道哪些假设真的有对应检验。
5. **Introduction 最后写**——因为它的三要素（问题/识别/结果）此时才全部确定。
6. **Abstract 最后最后写**——它是全文的压缩，不是创作。

---

## 四、识别策略的写法模板

### 4.1 通用四句式

> 1. **问题**：We ask whether X causes Y.
> 2. **障碍**：A naive comparison of Y across X is confounded by Z, because…
> 3. **策略**：We exploit [variation source] to identify the effect, relying on [assumption].
> 4. **可信性**：This assumption is plausible because [institutional fact / prior evidence / falsification test].

四句缺任何一句，识别段落就不完整。

### 4.2 按设计的专用句式

**DiD**
- 必须句：`The identifying assumption is that, absent the policy, treated and control units would have followed parallel trends.`
- 证据句：`Event-study estimates in Figure 3 show no differential pre-trend (joint p = 0.42).`
- 交错处理必加：`Because adoption is staggered, TWFE may place negative weights on some 2×2 comparisons; we therefore report Callaway–Sant'Anna estimates alongside.`

**IV**
- 必须句：`Identification requires that Z affects Y only through X (exclusion restriction).`
- 第一阶段：`The first stage is strong (F = 34.2, Table 2, column 1).`
- 外推边界：`The 2SLS estimand is a LATE for compliers — units whose treatment responds to Z — and does not identify the ATE.`
- 可证伪推论：`Consistent with exclusion, Z has no effect on placebo outcomes that X cannot affect.`

**RDD**
- 必须句：`Identification relies on the continuity of potential outcomes at the cutoff.`
- 必做检验：密度操纵检验（McCrary）、断点前协变量平衡、带宽敏感性。
- 表述：`Estimates are reported for the CCT optimal bandwidth and for ±50% of it.`

**匹配 / IPW**
- 必须句：`Identification requires unconfoundedness: conditional on pre-treatment covariates, treatment is as good as random.`
- 必报三项：overlap 图、平衡性表（SMD < 0.1）、样本损失。
- 诚实句：`Unconfoundedness is not testable; Section 6 quantifies how strong an unobserved confounder would have to be to overturn the result.`

### 4.3 DAG 的三条纪律

1. 节点须包含**未观测**变量（虚线），否则暗示"我知道所有混杂"。
2. 每条边须能追溯到理论或制度知识，不能凭直觉画。
3. 控制集须能回答"关闭了哪几条后门路径"；答不上来的变量应移出。

---

## 五、结果呈现的规范

### 5.1 三段式读表

每个主表后跟三段，缺一不可：

1. **方向与显著性**：`The coefficient on X is positive and significant at the 1% level.`
2. **经济意义**：`A one-SD increase in X raises Y by 0.08 SD, or 12% of the sample mean.`
3. **与假设的对应**：`This is consistent with H1, which predicts a positive effect through the monitoring channel.`

只有第 1 段，是"数据报告"；三段齐全，才是"论证"。

### 5.2 表格硬规范

- 三线表，无竖线；系数下方括号内标标准误，表注说明聚类层级。
- 星号必须在表注定义；`*** p<0.01, ** p<0.05, * p<0.1`。
- 每列底部固定三行：固定效应（是/否）、聚类层级、观测数。
- 有效数字全文统一（通常系数 3 位、标准误 3 位）。
- 二分类结局同时报绝对效应与相对效应（风险差 + 风险比）。

### 5.3 稳健性检验的写法

不要列"我们还做了 X、Y、Z"，要做成**威胁—检验—结论**三列对照表：

| 对结论的威胁 | 对应检验 | 结论是否改变 |
|---|---|---|
| 处理前趋势不同 | 事件研究图（图 3） | 否 |
| 未观测混杂 | Oster δ 检验 | 需混杂强度达 2.3 倍才推翻 |
| 样本选择 | 限定在存活企业子样本 | 否，系数略增 |
| 测量误差 | 换用替代指标 | 否，显著性下降至 5% |

---

## 六、常见拒稿原因（按频率排序）

1. **没有识别策略**，只有"控制了 X"。—— 这是社科实证被拒的第一原因。
2. **识别假设写出来了但不论证**，等于把问题推给审稿人。
3. **用因果语言描述相关结果**（"促进""导致""带来"）。
4. **稳健性堆砌但不对应威胁**，审稿人读不出你想排除什么。
5. **机制分析用中介回归草草了事**，未讨论中介变量本身的内生性。
6. **样本筛选规则与结果表 N 对不上**，触发数据可信度质疑。
7. **过度外推**：单一情境的 LATE 被写成普遍规律。

---

## 七、与相邻体裁的分界

| 你手上是 | 该用哪个 playbook |
|---|---|
| 观测/准实验数据，问因果 | **本 playbook**（quant） |
| 纯预测任务，问"能不能预测准" | genre-predictive-modeling（PRD/RPR） |
| 访谈/田野/案例，问"如何与为何" | genre-qualitative（QLT） |
| 实验室/材料表征，问"机制是什么" | genre-basic-science（SCI） |
| 临床试验，问"疗效与安全性" | reporting-guidelines（CLN） |

若一篇论文同时做因果与预测，须分别按两条线的规则各过一遍，并在文中明确区分"解释性模型"与"预测性模型"的目标。
