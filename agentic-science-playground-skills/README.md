# Agentic Science Playground — Skill Packages

本仓库包含 6 个可被 Agent 调用的科研 Skill（每个目录一份完整作品），用于 Bohrium「The Playground / Agentic Science」产品赛题。每个目录都是**自足的可上传包**：`SKILL.md`（本体，含 YAML frontmatter）、`README.md`（用法/方法/限制/示例）、可复用脚本、JSON schema、检查清单与模板。

## 目录 → 题目映射

| 目录 | 题目 | Challenge ID |
|---|---|---|
| `reading01/` | 阅读01｜文献文档解析 | product-arena-08-3027d350 |
| `writing04/` | 写作04｜参考文献与引用管理 | product-arena-03-429cc14d |
| `writing08/` | 写作08｜引言与相关工作写作 | product-arena-04-4b82ad21 |
| `writing13/` | 写作13｜LaTeX 写作与编译 | product-arena-07-865de7e4 |
| `reading15/` | 阅读15｜文献知识图谱构建 | product-arena-10-760d1a0b |
| `ppt/` | 论文转学术 PPT | ppt-c7b80f0d |

## 每个目录的通用结构

```
<目录>/
├── SKILL.md          # Skill 本体（合法 YAML frontmatter + 可执行操作流程 + 异常矩阵 + 自查清单）
├── README.md         # 调用方式、方法、范围/限制、失败处理、最小示例（示例均标注 EXAMPLE）
├── src/ 或 scripts/  # 纯标准库 Python 脚本（真实可运行，非占位符）
├── schema/           # JSON Schema（结果/证据结构定义）
├── checks/           # 核对清单（题目四问逐项映射）
└── templates/ 或 example/  # 模板 / 最小示例工程
```

## 说明

- 所有文件为 UTF-8 纯文本；脚本均为 Python 标准库实现（无第三方依赖）。
- 每个 Skill 均面向**未见过的隐藏案例**编写，结论回到原文证据，缺失/不确定/冲突显式标注，不包含预制答案或编造数据。
- 本仓库仅作作品公开展示；正式提交通过 Playground CLI 完成。
