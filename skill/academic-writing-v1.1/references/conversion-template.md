# 章节 → 规则卡 转换模板

用途：把 booktoskill 产出的 `chapters/ch0X-*.md` 或 `cheatsheet.md` 中的知识点，
转成 `rules/rules.yaml` 里的一条**可判定规则**。

## 五步转换

对每条候选知识点，按序执行：

### 1. 可判定性测试（第一关，一票否决）

- 问：这条知识点能不能变成一个"检查项"？
- 能 → 继续；不能 → **降级为 references 里的背景说明，不写进 rules.yaml**
- 判定标准：能同时写出 signal（触发信号）和 fix（具体改法）

### 2. 归类

- `genre`: ei-conf / ai-conf / sci-journal / ssci / dissertation（可多选）
- `section`: abstract / introduction / related-work / method / experiments / conclusion / title / general / references / rebuttal

### 3. 提炼 signal（触发信号）

描述"稿件出现什么现象时，这条规则被触发"，要具体到可识别：

- 好：`signal: 引言只有现象罗列，无转折指出不足`
- 差：`signal: 引言写得不好`

### 4. 提炼 fix（具体改法）

给出可执行的修复动作，落到句子/结构层面：

- 好：`fix: 补 "However, existing methods still suffer from..."`

### 5. 补元数据

- `source`: 书名 + 版次 + 章节 + 页码（不可省略）
- `example_bad` / `example_good`（强烈建议，便于回归测试）
- `conflict`（如与其他书规则冲突，标注按 genre 判定的条件）

## 输出格式（直接贴进 rules.yaml）

```yaml
- id: WRI-XXX-NNN
  genre: [ei-conf]
  section: introduction
  rule: <一句话规则>
  source: <书名 版次, ch.X>
  signal: <触发信号>
  fix: <具体改法>
  example_bad: "..."     # 可选
  example_good: "..."    # 可选
  conflict: "..."        # 可选
```

## 三条硬性纪律

1. 写不出 signal 的规则直接丢弃
2. 每本书控制在 40–80 条，宁缺毋滥
3. 每条必须有 source，否则无法回溯、无法消解冲突

## 降级清单（哪些知识点不写进 rules.yaml）

| 知识点类型 | 归宿 |
|---|---|
| 背景论述、作者观点 | references/*.md 的背景段落 |
| 术语定义 | glossary.md |
| 步骤流程（非单条判定） | references/*.md 的流程段落 |
| 心理/进度建议 | 不进主 skill |
