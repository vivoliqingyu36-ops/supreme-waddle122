# 页级大纲 + 证据映射表模板（slide outline + evidence map）

> 用法：按本模板逐页填写，再交给 `src/ppt_outline.py` 校验（`validate` 子命令）。
> 这是**结构模板**，不是答案。所有 `text` 字段只写从论文逐字抄录/改写的可讲短语，
> 数字与单位必须与原文一致；`locator` 必须能回到论文的图/表/公式/章节/页码。
> 长段落改写规则：一个 bullet 只表达一个可讲短语（≤120 字符），不用句号结尾；
> 一个 claim 只表达一个主张（≤160 字符，尽量一句）；超过就拆页或降为 bullet。

## 0. 主线（narrative arc，先写这个）

写清四段主线，并把「主结论」与「支撑性细节」分开：

| 主线位置 | 一句话主张（claim） | 是主结论还是支撑细节 | 证据 refs | locator（页/节/段） |
|---|---|---|---|---|
| 问题 problem | …… | 主 | — | page, section, where |
| 缺口 gap | …… | 主 | — | page, section, where |
| 方法 method | …… | 主 | formula:… / fig:… | page, section, where |
| 关键证据 1 | …… | 支撑 | fig:… / tab:… | page, section, where |
| 关键证据 2 | …… | 支撑 | fig:… / tab:… | page, section, where |
| 结论 conclusion | …… | 主 | fig:… | page, section, where |
| 限制 limitations | …… | 支撑 | — | page, section, where |

判定：结论页必须能回答「问题页」提出的问题；方法页是「缺口页」的答案；
每张证据页只挂一条关键证据；主结论与支撑细节不得混在同一句。

## 1. 页级模板（每页一张）

复制下面的块，每页一份。`role` 取值：`title / problem / gap / method /
evidence / conclusion / limitations / backup / thanks`。

```text
### 页 {index} — {role}

- claim（唯一主张，≤160 字符，尽量一句）：
- bullets（≤6 条，每条 ≤120 字符，短语、无句号）：
  - 
  - 
- evidence（本页绑定的图/表/公式/数据，每条带 locator）：
  - ref: {fig:2 | tab:1 | formula:3 | data:s1}
  - use: {data | context | reference}   # 示意图只能 context/reference，绝不 data
  - label: {逐字编号，如 "Figure 2"}
  - locator: {page, section, where, bbox?}
- data_verbatim（本页出现的数字/单位，逐字 + 条件）：
  - value: {如 "41"}  unit: {如 "%"}  condition: {如 "n=120, 5 seeds"}
  - ref: {从哪条 evidence 抄来}  locator: {page, where}
- notes（讲解备注：过渡/强调/被问时的补充证据；不得逐字重复 claim/bullets）：
- layout（模板占位符映射）：
  - layout_name: {Title Slide | Title and Content | Picture with Caption | ...}
  - placeholder_map: {title→title, body→content, figure→picture, table→content}
  - overflow_plan: {长标题怎么截/换行，多图怎么并列，大表怎么分栏或缩小}
- claim_locator: {本页主张来源 page/section/where}
- uncertainty: []
```

### 逐页角色提示（讲解顺序）

| role | 一页主张是什么 | 不该出现什么 |
|---|---|---|
| title | 论文标题 + 作者/机构 | 摘要结论堆砌 |
| problem | 要解决的问题/研究问题 | 方法细节 |
| gap | 现有方法缺什么、为什么重要 | 新结果 |
| method | 核心做法的一句话 + 示意图/公式 | 全方法章节 |
| evidence | 一条关键结果 + 对应图/表 + 数字单位 | 多结果混页 |
| conclusion | 一条 take-home 结论 | 再列一遍所有结果 |
| limitations | 诚实边界/未声称的内容 | 掩盖缺陷 |
| backup | 被问到才展开的补充结果 | 放在主线之前 |

## 2. 证据映射表（每张图/表/公式/数据一条）

| ref | kind | role | owner | label | locator(page/section/where) | 用在哪些页 | status |
|---|---|---|---|---|---|---|---|
| fig:2 | figure | data | paper | Figure 2 | 4 / Results / Figure 2 | 5,7 | used |
| fig:1 | figure | schematic | paper | Figure 1 | 3 / Methods / Figure 1 | 4 | used |
| tab:1 | table | data | paper | Table 1 | 4 / Results / Table 1 | 5 | used |
| formula:3 | formula | formula | paper | (3) | 3 / Methods / eq (3) | 4 | used |
| fig:0 | figure | data | cited | Figure 1 (cited) | 2 / Intro / citation [12] | — | unused |

字段含义：
- `kind`：figure / table / formula / data。
- `role`：figure 分 `data`（实测结果截图）与 `schematic`/`illustration`（原理示意图）；
  table 一律 `data`；formula 用 `formula` 或 `derivation`。
- `owner`：`paper`（本文结果）/ `cited`（引用他人，可引用但须注明）/ `other`（第三方数据）。
- `status`：`used`（出现在 ≥1 页）/ `unused`（抽取但主线不用，写 `unused_reason`）。

## 3. 模板约束填写（拿到模板后填）

```text
- template_file: {实际 .pptx 模板路径}
- layouts_available: {用 python-pptx 列出 master/layout 的 layout.name 与 placeholder 类型}
- placeholder_roles: {每个 layout 有哪些 placeholder: title/subtitle/body/picture/table/footer}
- fonts: {标题字体/正文字体/字号层级，从主题字体或 slide master 读出}
- colors: {主色/强调色/页脚色}
- footer_rule: {页脚是否必填、放什么：会议名/页码/单位}
- constraints: {title_max_chars, body_max_chars, body_max_bullets, 多图并排上限}
```

长标题处理：优先缩短（保留术语）→ 换行（按短语断行）→ 降字号到模板允许下限；
多图并列：按模板 picture 占位符数量决定 `2-up` 或 `grid`，每图保留 `Figure N` 标号；
大表格：只保留支持本页主张的列/行，其余放 backup 页，并注明「节选，完整见 Table N」。
