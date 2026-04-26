---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use this whenever users want to create a skill from scratch, edit or optimize an existing skill, run evaluations, compare skill quality with variance analysis, or improve skill description triggering accuracy. Be proactive: if the user mentions skill design, SKILL.md drafting, eval loops, benchmark review, or iterative optimization, invoke this skill even when they do not explicitly ask for “skill-creator”.
compatibility:
  tools: [read_file, create_file, apply_patch, run_in_terminal, runSubagent]
---

# Skill Creator

一个用于**创建新技能**与**迭代优化现有技能**的流程化技能。

## 核心目标

你要帮助用户走完完整闭环，而不是只写一版 SKILL.md：

1. 明确技能目标与触发场景
2. 起草或改写 SKILL.md
3. 设计并运行测试用例（with-skill + baseline）
4. 组织人工评审与量化评估
5. 基于反馈迭代改进
6. （可选）优化 description 的触发准确率
7. （可选）打包产出 .skill

---

## 沟通风格要求

- 默认使用清晰、少术语的表达。
- 对“evaluation/benchmark”可直接用；对“JSON/assertion”等术语，若用户经验不明确，给一句简短解释。
- 优先“先做后问”：能推进就直接推进，避免不必要追问。

---

## 阶段 0：识别用户当前所处阶段

先判断用户处于哪一段：

- 还在定义需求
- 已有 SKILL 草稿，等待评测
- 已跑过测试，等待分析与改写
- 仅想优化 description 触发率

若上下文已有信息（工具链、流程、输入输出格式、用户纠正历史），先提取再补问缺口。

---

## 阶段 1：需求访谈与边界确认

在动手写测试前，先确认：

1. 这个技能要解决什么问题？
2. 应该在什么用户话术/上下文触发？
3. 期望输出格式是什么？
4. 成功标准如何定义？
5. 依赖哪些文件、脚本、外部资源？
6. 是否需要测试用例（客观任务建议做；主观创意任务可弱化）？

---

## 阶段 2：编写或改写 SKILL.md

## 必备结构

- YAML frontmatter（至少 `name`、`description`）
- 主体说明（触发后执行策略）

## 写作原则

- 用祈使句描述动作。
- 解释“为什么要这样做”，减少僵硬规则堆叠。
- `description` 要更“主动触发”，明确“何时应使用”。
- SKILL.md 建议 <500 行；超长时拆分到 references/ 并在主文档指路。

## 目录建议

skill-name/
├── SKILL.md
├── scripts/（可执行脚本）
├── references/（大块参考文档）
└── assets/（模板/静态资源）

---

## 阶段 3：创建测试集（先不写断言）

先给用户 2~3 条真实测试 prompt 确认，再落盘到 `evals/evals.json`。

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User task",
      "expected_output": "What good looks like",
      "files": []
    }
  ]
}
```

---

## 阶段 4：运行评测（连续流程，不中断）

> 禁止使用其它“测试技能”替代该流程。

### 4.1 同一轮同时启动所有 runs

每个 test case 同时启动两条：

- with_skill（当前技能版本）
- baseline：
  - 新建技能场景：without_skill
  - 改进旧技能场景：old_skill（先快照旧版）

结果目录：

`<skill-name>-workspace/iteration-N/<eval-name>/[with_skill|without_skill|old_skill]/outputs/`

每个 eval 写 `eval_metadata.json`：

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name",
  "prompt": "task prompt",
  "assertions": []
}
```

### 4.2 运行中并行起草断言

在任务进行时，不等待；立刻补充**可客观验证**断言，并同步更新：

- `evals/evals.json`
- 各 eval 的 `eval_metadata.json`

### 4.3 记录 timing

每个 run 完成通知中的 `total_tokens` 与 `duration_ms` 立即写入 `timing.json`：

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

### 4.4 评分、聚合、生成评审界面

1. 对每个 run 生成 `grading.json`（expectations 字段必须是 `text/passed/evidence`）。
2. 聚合：
   - `python -m scripts.aggregate_benchmark <iteration-path> --skill-name <name>`
3. 分析：识别无区分断言、高方差样例、耗时/Token权衡。
4. 生成评审页（必须使用 `eval-viewer/generate_review.py`，不要手写 HTML）。

> 在 Cowork/无图形环境：使用 `--static <output_path>` 生成静态 HTML。

---

## 阶段 5：读取反馈并迭代

用户完成评审后读取 `feedback.json`，重点改进有明确投诉的测试项。

改写策略：

- 从个案提炼通用原则，避免过拟合样例。
- 删除低价值指令，保持提示精简。
- 识别重复劳动并沉淀到 `scripts/`。

然后进入下一轮 iteration（含 baseline），直到：

- 用户明确满意；或
- 反馈基本为空；或
- 连续迭代无实质收益。

---

## 阶段 6：Description 触发优化（可选）

1. 生成 20 条触发评测 query（8~10 should_trigger + 8~10 should_not_trigger，重点 near-miss）。
2. 让用户在评审页编辑并导出 eval 集。
3. 运行优化循环：

`python -m scripts.run_loop --eval-set <path> --skill-path <path> --model <current-model-id> --max-iterations 5 --verbose`

4. 使用 best_description 回写 frontmatter，并向用户展示前后对比与分数变化。

---

## 环境特化

## Claude Code / 本地 IDE

- 使用 subagent 并行跑 with-skill 与 baseline。
- 始终生成 eval-viewer。

## Claude.ai

- 无 subagent 时串行执行。
- 可跳过 baseline 与 benchmark，重点做人审反馈。
- 若无浏览器，直接在对话里展示结果与文件路径。

## Cowork

- 可并行 subagent。
- 无显示环境时用 `--static`。
- “Submit All Reviews” 会下载 `feedback.json`，需读取该文件继续迭代。

---

## 安全与边界

- 不创建恶意、误导、越权、数据外泄类技能。
- 不写会让用户意图与技能行为明显不一致的内容。
- 坚持“最小惊讶原则”。

---

## 执行检查清单（每轮都维护）

- [ ] 更新 TodoList（含当前迭代阶段）
- [ ] 确认技能目标/触发条件/输出格式
- [ ] 生成或修订 SKILL.md
- [ ] 创建并确认测试 prompts
- [ ] 创建 evals JSON 并运行 eval-viewer/generate_review.py 供人工评审
- [ ] 记录 timing / grading / benchmark
- [ ] 读取 feedback 并给出改进点
- [ ] 进入下一轮或收敛结束
- [ ] （可选）优化 description 触发率
- [ ] （可选）打包 .skill

---

## 交付标准

最终交付应至少包括：

1. 可用的 SKILL.md（结构清晰、触发明确）
2. 测试与评估产物（evals、grading、benchmark、review）
3. 迭代改进记录（用户反馈 -> 改动映射）
4. （可选）优化后的 description 与 .skill 包
