# citation-manager — 参考文献与引用管理 Skill

围绕「挂得对、编得顺、收得净、对得上」四个问题的最小可运行引用整理流水线。
本包提供 SKILL.md（运行期指导）、一个 stdlib-only 的 Python 脚本、一个结构化 schema、
一个验收清单。可用于顺序编码制（GB/T 7714—2015）、著者—出版年制（APA 7）与脚注制。

## 目录结构

```
writing04/
├── SKILL.md                        # 运行期唯一指导（安装到 /skills/weekly-skill）
├── README.md                       # 本文件
├── src/refs.py                     # 核心脚本（仅标准库，Python >= 3.8）
├── schema/citation_schema.json     # ReferenceRecord + ClaimSourceMapping 字段定义
├── checks/checklist.md             # 四问逐项验收清单
└── templates/result.json.template  # result.json 信封模板
```

## 依赖与版本

- Python 3.8+，无第三方依赖（只用 `re/json/argparse/unicodedata/difflib/urllib.parse/html`）。
- 运行期工具由平台提供：pdf-text-tool / ocr-tool / office-renderer（按需）。
- 验证：`python3 src/refs.py self-test` 应输出 `self-test OK: all checks passed`，退出码 0。

## 调用方式

脚本六个子命令，均可独立运行、输出 JSON 便于复核：

```bash
python3 src/refs.py normalize <文献库> [--fmt auto|bibtex|ris|jsonl|tsv] [--out refs.jsonl]
python3 src/refs.py dedup <refs.jsonl> [--out dedup.json]
python3 src/refs.py renumber <稿.txt> <refs.jsonl> [--order k1,k2] [--superscript] [--out-manuscript ..] [--out-refs ..]
python3 src/refs.py validate <稿.txt> <refs.jsonl> [--out report.json]
python3 src/refs.py format <refs.jsonl> [--style gbt7714|apa7] [--out refs.txt]
python3 src/refs.py self-test
```

Agent 侧完整流程见 SKILL.md 第 4 节（九步），要点：先 normalize → 建 claim map → dedup →
DOI/数据库核验 → renumber（把正文标记写成 `[CITE:key]` 中间形式）→ validate → 写产物与 result.json。

## 方法说明

### 1. 可解释去重键（收得净）
`make_dedup_key` 生成五段独立键：`doi_norm / title_norm / first_author_norm / year / venue_norm`。
`pair_match` 按优先级判定：
1. DOI 相同 → same_work(0.99)；DOI 都不同 → different_work(0.98)。
2. 题名+第一作者+年份一致 → same_work(0.95)。
3. 第一作者+年份+出处一致但题名不同 → candidate_merge(0.70–0.80)，**交人工不自动合并**（覆盖中英题名、预印本 vs 正式版、期刊 vs 会议版）。
4. 同名作者同年份、题名相似度 <0.55 且出处不同/缺失 → different_work（禁并，防误合并）。

每个判定都输出 `reason`（命中哪些字段）与 `confidence`，合并代表记录取“有 DOI、正式版、字段最全”。

### 2. 编号连锁更新（编得顺）
正文用 `[CITE:key]` 中间键标记，`renumber_keyed` 按首次出现顺序分配 1..N，多引合并为 `[n,m]`，
连续号折叠 `[2-4]`，可选 `^[n]` 上标；`order_references` 同步重排文末列表；`validate_citations`
双向校验：正文引了列表没有（缺失）、列表有正文没引（未引用）、数字越界，全部显式报告。
重复引用同一来源不计为错误。

### 3. 真实性核验（对得上）
有 DOI → 解析 `https://doi.org/<doi>` 或 Crossref API；无 DOI/失败 → 按题名+作者+年份数据库检索。
只有多路都查不到才判 `fabricated`；单路失败标 `unresolved`。每条论断要求 `evidence_quote`
来自被引文献原文，拿不到就标 `claim_match=unknown`，不凭标题猜测。

## 适用范围与限制

- 适用：.md/.txt/.tex/.docx/有文本层 PDF 稿件；BibTeX/RIS/EndNote/CNKI 导出/JSONL/TSV/纯文本文献库；中文、英文、中英混排。
- 限制：
  - BibTeX/RIS 解析是“容忍式”，复杂嵌套宏（如 `\cite` 内联、非标准字段）可能丢字段；缺字段会标 `missing_field` 而非报错。
  - `format` 只渲染纯文本骨架；GB/T 中文标点与 APA 斜体（刊名/卷号）必须在编辑器最终排版复核。
  - 去重为 O(n²) 成对判定，数千条文献库可用，超大库建议先按 DOI/作者年份分桶。
  - 不做 OCR 本身（调用平台 ocr-tool）；不做科学结论改写（只做引用管理）。
  - 跨语言题名等价无法纯字符串判定，故统一走“作者+年份+出处”次级键并交人工，绝不静默合并。

## 失败处理

- 脚本子命令返回非零即失败；`validate` 在 `ok=false` 时返回 2，其余异常会打印 traceback 并返回 1。
- 异常矩阵（字段缺失 / DOI 失败 / 歧义 / 编号冲突 / 格式不支持 / 文件损坏 / 加密 PDF / 无文本层）见 SKILL.md 第 8 节。
- 任何失败先落盘 `/app/work` 的中间产物，`result.json.status` 写 `partial`/`failed` 并说明边界，不伪造成功。

## 自查方法

1. `python3 src/refs.py self-test`（回归）。
2. 运行期最后一步逐项过 `checks/checklist.md`（四问各 6 项 + 出口检查）。
3. 硬闸门：validate `ok=true`；成品文献表无 `fabricated`；result.json 含 `case_id` 与 `output_contract` 全部字段。

## 最小示例（EXAMPLE —— 示意输出，非正式案例结果）

输入 `lib.bib`（EXAMPLE）：

```bibtex
@article{sm2020,
  author = {Smith, John and Doe, Jane},
  title = {A study of deep learning},
  journal = {Nature},
  year = {2020},
  volume = {12}, number = {3}, pages = {100--120},
  doi = {10.1000/xyz.1}
}
@article{sm2020b,
  author = {John Smith and Jane Doe},
  title = {A Study of Deep Learning},
  journal = {Nature},
  year = {2020},
  volume = {12}, number = {3}, pages = {100-120},
  doi = {10.1000/XYZ.1}
}
@article{sm2020q,
  author = {Smith, John},
  title = {Quantum error correction},
  journal = {Science},
  year = {2020}
}
```

输入稿件 `ms.txt`（EXAMPLE，键名中间形式）：

```
结论甲[CITE:sm2020]。方法乙[CITE:sm2020q]，且[CITE:sm2020,sm2020b]成立。
```

调用（EXAMPLE）：

```bash
python3 src/refs.py normalize lib.bib --out refs.jsonl
python3 src/refs.py dedup refs.jsonl --out dedup.json
# dedup.json（示意）：sm2020 与 sm2020b 合并为一簇；sm2020q 与它们判为 different_work（禁并）
# 去重后把正文里的 sm2020b 全部改写为簇代表键 sm2020，得到 ms_canon.txt：
#   结论甲[CITE:sm2020]。方法乙[CITE:sm2020q]，且[CITE:sm2020]成立。
python3 src/refs.py renumber ms_canon.txt refs.jsonl --out-manuscript ms_out.txt --out-refs refs_ordered.jsonl
python3 src/refs.py validate ms_out.txt refs_ordered.jsonl # ok=true
python3 src/refs.py format refs_ordered.jsonl --style gbt7714 --out refs_synced.txt
```

示意输出 `ms_out.txt`（EXAMPLE）：

```
结论甲[1]。方法乙[2]，且[1]成立。
```

示意输出 `refs_synced.txt`（EXAMPLE，GB/T 7714—2015，斜体/标点需最终排版复核）：

```
[1] SMITH J, DOE J. A study of deep learning[J]. Nature, 2020, 12(3): 100-120. DOI:10.1000/xyz.1.
[2] SMITH J. Quantum error correction[J]. Science, 2020.
```

以上输入/输出均为示意（EXAMPLE），不是任何正式测试案例的答案。
