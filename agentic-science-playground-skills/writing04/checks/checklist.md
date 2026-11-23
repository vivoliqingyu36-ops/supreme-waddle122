# 参考文献与引用管理 · 验证清单

本清单把题面「四个问题」映射为逐项可执行的检查。运行期在写 `/app/output/result.json`
之前，必须逐项打勾；任何一项不通过都要在 `result.json.issues` 里记录，不能静默跳过。

检查对象：编辑后的稿件、同步文献表、逐条来源映射记录（source_map.json）。

---

## 一、挂得对（引用位置与论断绑定）

| # | 检查 | 通过判据 | 失败处置 |
|---|------|----------|----------|
| 1.1 | 每个引用标记都落在“需要支撑的那句话”的句末（标点前），而不是整段末尾 | 引用标记与论断句在同一句内；`claim_mappings[].location.sentence_index` 与标记位置一致 | 把引用移到具体论断句后；段落综述性句子如需多源，逐句拆分标注 |
| 1.2 | 每个需要来源支撑的论断句都有 `claim_mappings` 记录 | `claim_mappings` 覆盖全部含数字/专名/他人结论/可检验断言的句子 | 补建映射；确属作者判断的句子在 `notes` 标注“作者判断，无需引用” |
| 1.3 | 一句多引、多句一引被显式处理 | 多引：一个标记内多个 key 且每个 key 对应各自分句；多句一引：每句一条映射指向同一 key | 拆分或合并映射，禁止“一个标记糊在段尾” |
| 1.4 | 图表注、表格、附录中的引用有独立定位 | `location.section` 区分 figure/table/appendix 正文 | 图表注内引用单独建映射，不并入正文首句 |
| 1.5 | 无来源论断已标注 | `unsupported=true` 的句子在稿件中用 `【待补引用】` 或注释标记 | 明确写出缺哪个来源，供人工补 |

## 二、编得顺（编号更新与交叉引用一致）

| # | 检查 | 通过判据 | 失败处置 |
|---|------|----------|----------|
| 2.1 | 正文编号连续且按首次出现顺序 | 运行 `python3 src/refs.py validate <稿> <文献表>`，`numeric_out_of_range` 为空 | 重跑 `src/refs.py renumber` |
| 2.2 | 文末列表序号与正文编号一一对应 | 列表第 i 条 == 正文首次出现的第 i 个来源；`numeric_uncited_indices` 为空 | 删除未引用条目或补挂引用；重排列表 |
| 2.3 | 正文每个编号在文献表都有条目（反向） | `keyed_missing_in_list` / `numeric_out_of_range` 为空 | 补文献条目或删除悬空标记 |
| 2.4 | 文献表每条都被正文引用 | `keyed_unused_in_list` / `numeric_uncited_indices` 为空 | 未引用条目：删除、或补正文引用、或标注“待引用” |
| 2.5 | 区间折叠与上标样式统一 | 多引写 `[1,3]`、连续写 `[2-4]`；全稿统一为上标 `[n]`（顺序编码制）或统一非上标 | 全文正则核对 `\[[0-9,\-–— ]+\]` 的样式一致 |
| 2.6 | 插入/删除/调序后重编号幂等 | 对同一稿件重复运行 renumber，两次输出 diff 为空 | 若不稳定，检查 key 是否唯一、是否有空 key |

## 三、收得净（去重与可解释合并）

| # | 检查 | 通过判据 | 失败处置 |
|---|------|----------|----------|
| 3.1 | 已跑去重且保留决策记录 | `source_map.json.dedup_decisions` 非空，或 `src/refs.py dedup` 已执行 | 运行 dedup 并落盘 |
| 3.2 | 每条合并都有解释依据 | 每个 cluster 有 `reason`（DOI 一致 / 题名+第一作者+年份 / 作者+年份+出处） | 无理由的合并一律撤销，改 candidate |
| 3.3 | 预印本与正式版合并为一条，代表记录取正式版 | `ReferenceRecord.version=published` 优先；预印本 URL 保留在 `provenance`/`url` | 重新选择 canonical |
| 3.4 | 中英题名/期刊与会议/不同 DB 导出合并正确 | 命中“作者+年份+出处”的 candidate_merge 全部交人工，不在自动 merge 内 | candidate 写入 `needs_human`，不静默合并 |
| 3.5 | 同名作者不同文献未被误合并 | `dedup_decisions` 中 `different_work`（禁并）条目存在且被尊重 | 恢复被误并的两条；记录禁并依据 |
| 3.6 | 去重后无残留重复 key | 文献表 key 唯一 | 用 `merge_key` 重新聚类，修复 key |

## 四、对得上（真实性与论断—文献匹配）

| # | 检查 | 通过判据 | 失败处置 |
|---|------|----------|----------|
| 4.1 | 每条引用都真实存在 | 有 DOI 的经 `https://doi.org/<doi>` 或 Crossref 解析返回记录；无 DOI 的经数据库检索命中，`verification.status=verified` | 查不到：置 `fabricated`，删除条目或标记待人工，不得保留为“真实” |
| 4.2 | 元数据准确 | 解析返回的题名/作者/年份/出处与条目 `field_match ∈ {exact, partial}` | mismatch：用解析结果纠正条目并记录修改 |
| 4.3 | 正文论断与被引文献主题/结论匹配 | 每条 `claim_mappings[].claim_match ∈ {matches, partial}` | mismatch：换引或改写论断；evidence_quote 无法找到时置 unknown |
| 4.4 | 每条论断有被引文献的原文证据 | `evidence_quote` 非空且 `evidence_location` 可回查 | 找不到原文：降级为 `claim_match=unknown`，标注证据不足 |
| 4.5 | 编造条目与错配被检出并隔离 | `issues` 里 fabricated/metadata_mismatch 条目明确列出 | 报告中单列“疑似编造/错配”清单，不混入成品文献表 |
| 4.6 | DOI 解析失败有替代路径 | 失败条目在 `verification.note` 说明尝试的路径与失败原因 | 用 Crossref 检索（title+author）或 PubMed/CNKI 二次核验 |

---

## 最终出口检查（写 result.json 前）

- [ ] 稿件是可编辑格式（.md/.docx/.tex 之一），且正文标记、列表、来源映射三处编号一致。
- [ ] 文献表与稿件同步导出（`refs_synced`），逐条可回溯到原始文献库快照。
- [ ] `result.json` 含 `case_id` 与 case.json `output_contract` 要求的全部字段；未确认项进 `uncertainty`/`issues`。
- [ ] 幂等性：对同一输入重跑，`result.json` 的确定性字段（编号、去重结果）不漂移。
- [ ] 人工确认项（candidate_merge、mismatch、unsupported、DOI 失败）在 `result.json.human_review` 单独列出。
