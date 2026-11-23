# LaTeX 写作与编译 Skill（writing13）

把科研材料变成**能按指定模板编译通过、可继续编辑、可被他人复现**的 LaTeX 成果。
围绕题面四个问题闭环：**编译得通 → 改得对 → 交得可用 → 复现得了**。

## 目录结构

```
writing13/
├── SKILL.md                      # 技能本体（frontmatter + 全流程 + 决策树 + 异常矩阵）
├── README.md                     # 本文件
├── src/build.py                  # 编译循环 + 日志分类 + 收敛报告（仅标准库）
├── schema/latex_schema.json      # 构建记录 JSON Schema（draft-07）
├── checks/latex_checklist.md     # 四问 → 具体检查 + 验证命令
└── example/                      # 最小可运行示例工程（EXAMPLE）
    ├── main.tex
    └── refs.bib
```

## 调用方式

运行期 Agent 由 DeepSeek Harness 安装本技能到 `/skills/weekly-skill`，输入在
`/input/case.json` 与 `/input/task.md`，工作目录 `/app/work`，产物 `/app/output`。
技能流程见 `SKILL.md`，核心自动化助手：

```bash
python3 src/build.py --workdir <项目目录> --main <主文件.tex> [--engine pdflatex|xelatex|lualatex] \
                     [--bib auto|bibtex|biber|none] [--latexmk] [--max-passes 5] \
                     [--report build_report.json]
```

退出码：`0` 收敛（无错误、引用全部解析）；`1` 未收敛（错误/未定义引用仍在）；`2` 环境或参数错误。
无论成败都会写 `--report` 指定的 JSON（默认 `build_report.json`），内含每条错误的
`file:line:category`、宏包/字体清单、命令列表与收敛判据。

## 方法说明

1. **工程勘察**：定位主文件（含 `\documentclass` 且不被 `\input` 的文件）、子文件、
   导言区宏包、`.bib`、模板 `.cls/.sty`，写 `inventory.md`。
2. **错误三诊**：`build.py` 用 `-file-line-error` 让引擎报 `文件:行号:消息`，解析
   `.log` 得**全部**错误并按 taxonomy 分类（缺类/缺包/缺字体/未定义控制序列/未定义
   引用/未定义文献/坏数学/表格溢出/括号失控/容量超限/急停/级联）。
3. **根因优先修复**：按 `缺文件 → 未定义宏 → 语法 → 表格 → 引用文献 → overfull` 顺序
   修，级联错误（EMERGENCY_STOP 等）最后自动消失；每批修改后重跑一次归因。
4. **收敛判据**：相邻两遍 `.aux/.toc/.lof/.lot/.bbl/.out` 的 md5 全相同，且日志无
   `Rerun to get ...`，且无未定义/重复引用文献 —— 三点同时成立才算 `converged`。
5. **内容校验**：公式标签/引用一一对应；表格用 PDF 文本回读与源材料逐格比对；文献
   key 与 `.bib` 一一对应；模板必填项逐项打勾。
6. **复现记录**：把发行版、引擎版本、宏包名/日期/版本、字体、精确命令、轮次写入
   `build_record.json`（按 `schema/latex_schema.json` 校验），并做一次干净重建验证。

## 适用范围与限制

- 适用：学术论文/会议/期刊/学位论文模板迁移、LaTeX 编译错误修复、公式/表格/交叉
  引用/参考文献写作与排版、双语或结构化稿件、可复现构建记录。
- 引擎：`pdflatex`/`xelatex`/`lualatex` + `bibtex`/`biber` + 可选 `latexmk`。
- 不适用：任务明示不用 LaTeX；只有 PDF 且不要求转写 TeX；无任何排版/编译/引用需求。
- 限制：不联网时无法 `tlmgr` 装缺失宏包/字体（退化为等价替换并记录）；模板类文件
  与字体若平台未预装且材料未提供，无法凭空生成，只能标注 `partial/failed` 并交付
  已完成源码；PDF 的 md5 因每次写入的 `/CreationDate /ModDate /ID` 而不同，复现比对
  需忽略这三项元数据。

## 失败处理

`build.py` 失败（退出码 1/2）时：先读 `build_report.json` 的 `errors[]` 按
`category` 分组；对照 `SKILL.md §8` 异常矩阵逐类处置；每修一批重跑一次；无法解决时
在 `result.json` 的 `limits` 写明「已完成什么 + 卡在哪一步 + 为何」，绝不伪称通过。

## 自查方法

```bash
# 1) 脚本语法与最小示例
python3 -m py_compile src/build.py
python3 src/build.py --workdir example --main main.tex    # 期望退出码 0

# 2) schema 与报告可解析
python3 - <<'PY'
import json
json.load(open('schema/latex_schema.json'))
json.load(open('example/build_report.json'))
print('ok')
PY

# 3) 全包仅 UTF-8 文本、无符号链接、无二进制
find . -type f -exec file {} + | grep -v -E 'UTF-8|ASCII|Python|JSON|text|empty'
find . -type l   # 期望无输出
```

正式用例交付前逐项打勾 `checks/latex_checklist.md`，凡 `[!]` 项写入 `limits`。

## 最小示例（EXAMPLE）

`example/main.tex` + `example/refs.bib` 是一个可独立编译的最小工程：一个 `\section`
标签、一个 `equation` 标签 + `\eqref`、一个三线表（`booktabs`）、一条 `\cite` 与配套
`.bib` 条目。

```bash
cd example
python3 ../src/build.py --workdir . --main main.tex --report build_report.json
# 期望：退出码 0；stdout/报告里 converged=true, error_count=0,
#       broken_reference_count=0, passes 4 个条目(pdflatex→bibtex→pdflatex→pdflatex)
```

示意输出（**为示例，非正式案例结果**）关键字段：

```json
{
  "engine": "pdflatex",
  "distro": "TeX Live 2023/Debian",
  "converged": true,
  "error_count": 0,
  "warning_count": 0,
  "broken_reference_count": 0,
  "packages": [{"name": "amsmath", "date": "...", "version": "..."},
               {"name": "booktabs", "date": "...", "version": "..."}]
}
```

（示例工程目录不随附生成的 `.pdf/.log/.aux`，因为这些是运行期二进制/中间产物；
任何人在装有 TeX Live 的环境里按上面命令即可复现。）
