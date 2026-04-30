---
name: fill-weekly-report
description: Use when the user wants to fill, update, complete, or submit a Tiangong personal weekly report, especially for one-question-at-a-time weekly report entry by member slug and week start date.
---

# Fill Weekly Report

## Overview

Fill Tiangong personal weekly reports by collecting one task at a time in chat. The agent, not the terminal script, owns the conversation: it proposes examples, accepts natural answers such as `同意` / `沿用` / `无` / `100`, previews the final report, then writes or submits it.

Default member: `songweihao`. Default repo: `/home/peter/repositories/tiangong`.

## Trigger

Use when the user asks to:

- 填写周报 / 补全周报 / 更新周报
- 根据上周计划生成本周周报
- 提交周报 / 推送周报到 `develop`

## Operating Rules

- Always ask in Chinese.
- Ask about one task at a time, not one table cell at a time.
- For each task, show a suggested filled example before asking for the user's answer.
- Treat blank input, `沿用`, `同意`, `可以`, `yes`, `y` as accepting the current suggestion.
- Treat `无`, `没有`, `n`, `no` as no extra content when the current question allows it.
- Do not rely on terminal `input()` for user-facing collection. Collect answers in chat, then write the report.
- Before writing, output the generated weekly report content or the changed sections for user confirmation.
- If the initial user request included “提交/推送”, then after confirmation write, commit, rebase, and push. If it only asked to fill/update, write only.

## Workflow

1. Run `git switch develop` and `git pull --rebase origin develop` in the Tiangong repo before reading/writing.
2. Resolve the report path:
   `kb/weekly_report_submission/<YYYY>/<MM>/<week_start>_<week_end>/personal/<member_slug>_weekly_report_<week_start>_<week_end>.md`.
3. Create the report from `templates/weekly_report_submission/personal_weekly_report_template.md` if it is missing.
4. Read last week's report for the same member. Preload last week's:
   - `3.1` into this week's `2.1`
   - `3.2` into this week's `2.2`
5. For each inherited task, ask a single task-level question:
   - task name and suggested summary
   - completion rate
   - deviation reason only if rate `<100`
   - dependency/risk/links only if they differ from the suggestion
6. Ask whether there were temporary new tasks this week. Collect each new task in the same task-level format.
7. Ask for next week's internal tasks. Offer polished example wording from the user's rough task title.
8. Ask whether next week's external tasks should mirror internal tasks. If yes, copy them directly.
9. Ask for experience/retrospective and SuanhaiOS feedback; default both to `无`.
10. Generate a preview of the changed report sections and ask for confirmation.
11. After confirmation, write only editable data blocks.
12. If the original intent was submission, run `git add <report>`, `git commit`, `git pull --rebase origin develop`, and `git push origin develop`.

## Current Template Columns

For v0.4 weekly reports, keep these table shapes exactly:

- `2.1` / `2.2`: `任务编号 | 任务事项 | 本周进度总结 | 完成率(0-100) | 状态偏差原因 | 依赖 | 风险 | 风险等级 | 设计与执行资产目录链接 | 成果物链接`
- `3.1` / `3.2`: `任务编号 | 任务事项 | 下周目标说明 | 预计完成率(0-100) | 依赖 | 风险 | 风险等级 | 设计与执行资产目录链接 | 预计成果物链接`

Risk level must be `低`, `中`, or `高`; default to `低` when the user reports no risk.

## Validation

- Task item is required for every non-empty row.
- Completion rate and expected completion rate must be integers in `0..100`.
- Any rate below `100` requires a deviation reason.
- `2.2` and `3.2` must each contain at least one valid task.
- Non-empty URL fields must start with `http://` or `https://`.

## Write Boundary

Only edit task rows in `2.1`, `2.2`, `3.1`, `3.2`, bullet rows in `2.3`, feedback rows in `4`, and direction-lead rows in `5` when applicable. Do not edit file names, section titles, table headers, basic info, explanatory blockquotes, or appendix history.
