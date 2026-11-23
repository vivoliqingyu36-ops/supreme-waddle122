# 四问核对清单（checklist）

> 用法：草稿与 `source_map.json` 落盘后逐项判定 `pass` / `fail` / `na`（不适用）。
> 任何 `fail` 必须先修复或写进 result.json 的 `needs_human`/`uncertainty`。
> 每项给出「怎么查」的具体动作，避免主观打分。

## A. 立得住（研究背景）

| # | 检查项 | 怎么查 | 结果 |
|---|---|---|---|
| A1 | 背景点名 ≥2 个具体工作/技术里程碑，且各有引用键 | 数背景段里出现的 citation_key 个数，≥2 | ☐ |
| A2 | 背景落在一个具体的未解决问题上，不是泛泛的重要性 | 找「现有方法在 {场景} 上 {具体约束}」句式；找不到即 fail | ☐ |
| A3 | 给出「为什么现在值得做」的具体理由（新数据/新工具/新算法/评价缺口） | 检查是否有 ≥1 句指向可核对的约束或契机 | ☐ |
| A4 | 无「近年来受到广泛关注」「具有重要意义」类空转句 | grep「广泛关注 / 重要意义 / 越来越 / increasingly important / attracted attention」，应无命中 | ☐ |
| A5 | 每个背景事实句有 source（引用键 / 文件定位 / 作者判断） | 对每个背景 claim 查 source_map.json 的 `source` 字段非空 | ☐ |

## B. 分得清（相关工作）

| # | 检查项 | 怎么查 | 结果 |
|---|---|---|---|
| B1 | 相关工作按 problem_setting 或 method_route 分组，每组一段 | 数小标题/段落是否对应矩阵的分组维度，而非按年份 | ☐ |
| B2 | 每组至少一句「同维度差异句」（A 用 X 换 Y，B 用 W 牺牲 Z） | grep「但 / 然而 / 相较 / 相比之下 / 与此不同」，确认是在同一维度比较 | ☐ |
| B3 | 每处转述只来自该文献的 stated_conclusion/applicability/limitation | 抽查 3 条 prior_work_claim，比对 works_facts.md 对应条目 | ☐ |
| B4 | 来源没写的局限一律写「未报告」，不代写 | 查比较矩阵 limitation 列：无来源的格子写「未报告」而非编造 | ☐ |
| B5 | 无张冠李戴（A 的结论安到 B） | 对每条 prior_work_claim 核对 citation_key 与 work_key 一致 | ☐ |
| B6 | 无逐篇摘要拼接（每篇独立一段复述全文） | 若每段只谈一篇且无比较句，即 fail | ☐ |

## C. 说得实（研究空白）

| # | 检查项 | 怎么查 | 结果 |
|---|---|---|---|
| C1 | 每条空白有 gap_type（shared_limitation/uncovered_scenario/conflicting_conclusion/no_basis） | 查 source_map.json 的 `gaps[].gap_type` 均合法 | ☐ |
| C2 | shared_limitation 有 ≥2 篇依据；conflicting_conclusion 有 ≥2 篇依据；uncovered_scenario 写清「谁覆盖了什么、差什么」 | 数 `basis_works` 长度 / 读 `basis_loc` 描述 | ☐ |
| C3 | 每条空白的依据文献带原文定位 | 查 `basis_loc` 非空且能回到文件 | ☐ |
| C4 | 空白段写了「本文如何填补」，且填补方式来自本文事实 | 查 gap 的 `this_paper_fill` 是否指向本文方法/实验，而非他人工作 | ☐ |
| C5 | no_basis 类空白显式标「作者判断」，不伪装成有文献支持 | grep「作者判断」，no_basis 条目不挂 citation_key | ☐ |
| C6 | 无凭空断言「少有研究 / 鲜有工作」而不给依据 | 这类句子必须有 ≥1 篇依据或标作者判断 | ☐ |

## D. 对得上（贡献 + 引用）

| # | 检查项 | 怎么查 | 结果 |
|---|---|---|---|
| D1 | 每条贡献有本文证据定位（方法/图/表/实验/公式） | 查 contributions[].evidence 非空，且能指回 draft 正文 | ☐ |
| D2 | evidence_status=missing 的贡献已降级为「计划/假设」或删除 | 对比 draft 与 contributions 列表，无悬空强断言 | ☐ |
| D3 | 贡献不夸大适用范围（只声称实验/方法实际支持的） | grep 绝对词「首次 / 完全解决 / 普适」，确认有对应证据或已软化 | ☐ |
| D4 | 草稿中每个 citation_key 在参考库有定义 | 跑脚本，退出码非 2 | ☐ |
| D5 | 引用元数据（作者/年/出处/DOI）与来源一致；DOI 查不到标 false | 抽查 3 条，比对来源文件；无编造 | ☐ |
| D6 | 数字引用按首次出现顺序连续无冲突 | 检查 [1]..[n] 顺序与断号 | ☐ |
| D7 | 库中未引用项、草稿引用但库缺项均已记录 | 查 citation_coverage 两数组 | ☐ |

## E. 结果完整性

| # | 检查项 | 怎么查 | 结果 |
|---|---|---|---|
| E1 | 四部分齐全且顺序承接（背景→相关工作→空白→贡献） | 读 draft.md 标题序列 | ☐ |
| E2 | result.json 含 case_id 与题面 output_contract 全部字段 | 比对 task.md 的 output_contract 字段名 | ☐ |
| E3 | source_map.md/json、comparison_matrix.md、draft.md 均已落盘 | ls /app/output | ☐ |
| E4 | 脚本 `claim_map_check.py` 退出码非 2 | 记录脚本输出 | ☐ |
| E5 | 不确定/冲突/材料缺失/人工确认项均已写入 result.json | 检查 uncertainty/needs_human/material_gaps | ☐ |

## 一票否决（任一 fail 不得交付 success）

1. 正文存在含事实/判断但无来源的 claim。
2. 贡献强断言无任何证据定位且未降级/删除。
3. 引用键在参考库不存在（未处理）。
4. result.json 缺 case_id 或缺 output_contract 字段。

> 复核记录：把本清单的最终判定写入 `result.json.verification`（四问各一个 pass/fail/na），并在 needs_human 中列出仍 fail 的项。
