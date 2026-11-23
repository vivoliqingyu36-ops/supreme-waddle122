# 核验清单：四问逐项勾选（checks/checklist.md）

在 `export` 之前逐项勾选；任何一项未通过先修复。括号标注：M = 可机械校验（`src/nanopub.py validate`），H = 需回原文人工核对。

## 问 1 — 拆得细（一段结论拆成若干条各自可判断真假的断言，保留条件/限定，处理并列与因果）

- [ ] （M）`validate` 无 `text contains N sentences`、`text is ... chars (>600)` 类 error：没有把整段/多句塞进一个 `text`。
- [ ] （M）`validate` 无 `coordinating conjunction` / `causal chain` 类 warning（或每条 warning 已在 `decomposition.note` 说明保留理由）：复合并列与因果链已拆开。
- [ ] （M）每条断言 `subject.label`、`relation`、`object.label` 非空；`relation` 是 snake_case 受控动词；`relation_type` 在枚举内。
- [ ] （H）复合主体 "A and B cause X" 已按 A/B 是否为独立实体拆成两条，或注明"A and B 是一个复合物"不拆。
- [ ] （H）复合宾语/谓语 "X increases Y and decreases Z" 已拆成 "X increases Y" 与 "X decreases Z"，关系与方向各写各的。
- [ ] （H）因果链 "X causes Y, which leads to Z" 已拆成 "X causes Y" 与 "Y leads_to Z"，各自绑定各自证据。
- [ ] （M）`source_text` 含限定短语但 `conditions[]` 为空 → warning 已处理：条件（物种/细胞系/剂量/时间/对照组/设置）已填入 `conditions[]`。
- [ ] （H）否定主张 `polarity="negated"`；量词 `all/some/none/specific/not_stated` 照原文；未写的不填推测值。
- [ ] （H）抽查 2 条拆解：拆出来的每条仍能单独读出"主体做了什么、作用于什么"，而不是只有半句话。

## 问 2 — 对得上（每条断言绑定最小充分证据片段，且片段原文位置可被指出）

- [ ] （M）`validate` 无 `missing/empty evidence_binding.quote`、`evidence location has no` 类 error。
- [ ] （M）`--text paper.txt` 下无 `quote is not a substring` 类 error：每条 verbatim 引文都能在正文命中。
- [ ] （H）每条 `quote` 是最小充分片段（承载主体+关系+对象的最短跨度），不是整段；`sufficiency.minimality_note` 说明裁剪。
- [ ] （H）每条 `location` 有页码/段落/句子 或 图/表/公式编号 + `pointer`；位置是原文页码/段落 ID，不是自造序号。
- [ ] （H）`relation_to_assertion` 与事实一致：直接陈述=direct；读图/读数据/多句合取=inferred（`sufficiency.reason` 写明推理步骤）；背景=context 且不标 `supported`。
- [ ] （M）`status="supported"` 时 `sufficiency.judgment != "insufficient"`；`unsupported` 时 `judgment != "sufficient"`。
- [ ] （H）图表证据用 `quote_type="figure_description"` + `location.figure` 编号 + 轴/数值/方向描述；看不到数值时写"未报告"，不反推。
- [ ] （H）抽查 3 条：`grep` 引文能在材料文件中命中，且引文真的支持该断言（主体、关系方向一致）。

## 问 3 — 追得回（断言→证据→论文→作者→年份→版本链路完整，他人能回到原文）

- [ ] （M）`validate` 无 `provenance.chain must be exactly`、`provenance.assertion_id`、`provenance.evidence_id`、`provenance.source_id ... not found` 类 error。
- [ ] （M）每条 `provenance.chain == [assertion_id, evidence_id, source_id]`。
- [ ] （M）每个 `source_id` 在 `sources[]` 中；每个 source 有 `title + authors（≥1）+ year（1400–2100 或 null+note）+ version + identifiers（≥1，DOI 优先）`。
- [ ] （H）`year`/`version`/`identifiers` 与实际文献版本一致（published/preprint-v1 等）；多版本论文各建一行并 `note` 互指。
- [ ] （H）DOI/PMID/arXiv/URL 不是编造的；无法确认时显式 `unknown` + `note`，并写进 `uncertainty`。
- [ ] （H）抽查 2 条完整链：断言 → 证据引文 → 位置 → 论文 → 作者 → 年份 → 版本，逐级都能定位到原文。

## 问 4 — 读得懂（导出遵守约定字段与序列化形态，机器可解析，无需人工清洗）

- [ ] （M）`python3 src/nanopub.py export ...` 成功（无 error），产物 `json.load` 一次通过；键排序 + 2 空格缩进 + UTF-8。
- [ ] （M）`result.json` 含 `schema_version="1.0.0"`、`case_id`、`status`、`sources`、`assertions`，以及 `output_contract` 要求的全部字段。
- [ ] （M）所有枚举字段（`relation_type/direction/polarity/quote_type/relation_to_assertion/sufficiency.judgment/certainty.level/status` 等）取值在受控词表内；无自由文本混入枚举字段。
- [ ] （M）`assertion_id`/`evidence_id`/`source_id` 全局唯一。
- [ ] （H）`unreported`（未报告值）、`conflicts`（冲突并列保留）、`uncertainty`（不确定项）、`change_log`（关键步骤）已填且无编造。
- [ ] （H）`status` 与实际情况一致（success/partial/failed）；`status_detail` 在 partial/failed 时写清原因。

## 交付收口（每次交付前）

- [ ] （H）`result.json` 含 `case_id`（抄自 `/input/case.json`）与 `output_contract` 全部字段。
- [ ] （M）`nanopub_schema.json` 是合法 JSON；`nanopub.py --self-test` 通过（exit 0）。
- [ ] （H）无编造 DOI/页码/数值/作者/年份；缺失与冲突显式标注，不冒充事实。
- [ ] （H）重复运行同一输入产出相同断言 id/证据 id/链（脚本确定性）。
