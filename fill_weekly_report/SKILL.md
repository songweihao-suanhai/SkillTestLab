---
name: fill_weekly_report
description: 基于团队周报规范，采用问答式交互填写并更新个人周报，支持新周报自动建档、上周计划继承、字段与阻塞校验、缓存恢复，以及可选 Git 提交推送。用户只要提到“填写周报/补全周报/更新周报/提交周报到 develop”，或提供 member_slug 与周起始日期要求生成或修改周报，都应触发本技能。
compatibility:
  tools: [read_file, create_file, apply_patch, run_in_terminal]
---

# Skill: fill_weekly_report

## 1. 概述

- 技能名称：`fill_weekly_report`
- 版本：`v1.1.0`
- 默认成员：`songweihao`（宋维豪 / 计算流体组 / 非方向负责人）
- 执行入口：`fill_weekly_report/scripts/fill_weekly_report.py`

本技能用于按团队规范交互式填写周报，支持：自动建档、上周计划继承、字段校验、缓存恢复、可选 Git 提交。

## 2. 触发条件

任一命中即触发：

1. 用户提到“填写/补全/更新周报”。
2. 用户给出 `member_slug` + 周日期，要求生成或修改周报。
3. 用户要求提交周报到 `develop`。

## 3. 输入参数

| 参数 | 类型 | 默认值 | 规则 |
|---|---|---|---|
| `member_slug` | string | songweihao | 必须存在于注册表且 `is_active=true` |
| `week_start` | string | 当前周周一 | 格式 `YYYY-MM-DD` |
| `auto_commit` | boolean | false | 为 `true` 时自动执行 Git 流程 |

## 4. 依赖

- 规范与模板：
  - weekly_report_filling_operation_guide.md
  - personal_weekly_report_template.md
- 数据源：member_registry.json
- 缓存：`.weekly_report_cache.json`

目录映射：

- `scripts/`：可执行脚本（入口：`scripts/fill_weekly_report.py`）
- `references/`：参考文档与依赖说明
- `assets/`：模板/静态示例资源

目标文件路径：

`kb/weekly_report_submission/<YYYY>/<MM>/<week_start>_<week_end>/personal/<member_slug>_weekly_report_<week_start>_<week_end>.md`

## 5. 输出

成功时：

- 周报写回（UTF-8）并通过校验
- 返回成员、周次、更新区块数、Git 执行结果

失败时：

- 返回中文错误 + 失败阶段（注册表/定位/校验/Git）
- 不回滚已成功写回的本地内容

## 6. 执行流程（固定顺序）

1. **缓存恢复**：检测同 `member_slug + week_start` 未完成缓存，支持恢复或重填。
2. **参数归一化**：计算 `week_end` 与 ISO 周 `YYYY-Www`。
3. **成员校验**：读取注册表并校验成员存在且激活。
4. **文件定位**：若不存在则用模板建档，并尝试继承上周 `3.1/3.2 -> 本周 2.1/2.2`。
5. **内容解析**：仅解析可编辑区（2.1/2.2/2.3/3.1/3.2/4/5）。
6. **已填分支**：重填 / 按编号改 / 追加 / 退出。
7. **交互采集**（顺序固定）：`2.1 -> 2.2 -> 2.3 -> 3.1 -> 3.2 -> 4 -> 5(负责人)`。
8. **即时校验 + 阻塞校验**：不通过进入修正循环。
9. **写回文件**：仅替换数据区，禁止改表头/标题/注释/附录。
10. **可选 Git**：`fetch -> checkout/pull -> add -> commit -> push`。
11. **结束清理**：成功删缓存，中断可保存缓存。

## 7. 字段与阻塞校验

字段规则：

- 任务事项必填。
- 完成率/预计完成率必须在 `0..100`。
- `<100` 时偏差原因必填。
- 链接字段非空时必须匹配 `^https?://.+`。

阻塞规则（任一不满足即阻塞）：

- 2.2 至少 1 条有效任务。
- 3.2 至少 1 条有效任务。
- 任意 `<100` 无偏差原因。
- 任意链接非完整 `http://` 或 `https://`。

兼容规则：若 3.1/3.2 无“偏差原因”列，将“偏差原因”并入风险列前缀：`偏差原因：...；风险：...`。

## 8. 写回边界

仅可改：

- 四个任务表数据行
- 2.3 列表
- 第四部分反馈列表
- 第五部分（仅负责人）

严禁改：

- 文件名、章节标题、表头、基本信息区、`>` 注释、附录版本记录

## 9. 数据结构（建议）

`TaskRow`：

- `task_no` `task_item` `summary_or_goal` `rate` `deviation_reason`
- `dependency` `risk` `asset_url` `deliverable_url`
- `expected_deliverable`（仅 3.x）

缓存 `.weekly_report_cache.json`：

- `member_slug` `week_start` `updated_at`
- `sections`（2.1,2.2,2.3,3.1,3.2,4,5）
- `mode`（重填/按行修改/追加）

## 10. 自动化入口

- 默认（交互 + 自动提交）：
  - `python fill_weekly_report/scripts/fill_weekly_report.py --repo-root <repo_root> --member-slug <member_slug> --week-start <YYYY-MM-DD>`
- 仅写回不提交：
  - `python fill_weekly_report/scripts/fill_weekly_report.py --repo-root <repo_root> --member-slug <member_slug> --week-start <YYYY-MM-DD> --no-auto-commit`

行为约束：

1. 先同步 `develop`，再进入交互。
2. 交互结束后再执行 `add/commit/push`。
3. 暂存区无变更时跳过提交并提示。

## 11. 非功能要求

1. 全程中文提示，错误可定位、可执行。
2. 不依赖人工解释即可执行。
3. 异常不破坏已保存内容。
4. 对外区（2.2/3.2）优先保障可汇报性与可汇总性。