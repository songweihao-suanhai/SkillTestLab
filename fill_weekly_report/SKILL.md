# Skill: fill_weekly_report

## 1. 基本信息

- **技能名称**：fill_weekly_report
- **版本**：v1.1.0
- **默认用户上下文**：
  - `member_slug`: songweihao
  - 成员信息：宋维豪 / 计算流体组 / 非方向负责人（来自注册表）

## 2. 技能描述

基于团队周报规范，采用“系统逐问、用户逐答”的问答式交互填写并更新个人周报文件；支持新周报自动建档、上周计划继承、硬性校验、可选 Git 提交推送、异常提示与缓存恢复。

当前仓库已提供可执行入口：

- `SkillTestLab/fill_weekly_report/fill_weekly_report.py`

该入口会按固定顺序与用户交互采集内容，写回目标周报文件，并在默认配置下自动提交推送到 `develop`。

本技能直接遵循以下文件：

- weekly_report_filling_operation_guide.md
- personal_weekly_report_template.md
- member_registry.json

## 3. 触发条件

满足任一条件即触发：

1. 用户请求“填写周报/补全周报/更新本周周报”。
2. 用户提供 `member_slug` 与周日期，要求生成或修改个人周报内容。
3. 用户要求提交周报到 `develop` 分支。

## 4. 输入参数

| 参数 | 类型 | 必填 | 默认值 | 规则 |
|---|---|---|---|---|
| `member_slug` | string | 否 | songweihao | 必须存在于注册表且 `is_active=true` |
| `week_start` | string | 否 | 当前日期所在周周一 | 格式 `YYYY-MM-DD` |
| `auto_commit` | boolean | 否 | false | `true` 时校验通过后直接执行 Git 流程 |

## 5. 依赖与能力

### 5.1 文档与模板

- weekly_report_filling_operation_guide.md
- personal_weekly_report_template.md

### 5.2 数据源

- member_registry.json

### 5.3 文件定位规则

目标文件相对路径模式：

`kb/weekly_report_submission/<YYYY>/<MM>/<week_start_underscore>_<week_end_underscore>/personal/<member_slug>_weekly_report_<week_start_underscore>_<week_end_underscore>.md`

示例文件名：

`songweihao_weekly_report_2026_04_20_2026_04_26.md`

### 5.4 系统能力

- Markdown 表格解析与重写（仅数据行）
- JSON 读取
- Git 命令执行
- UTF-8 文件写入
- 本地缓存文件 `.weekly_report_cache.json`

## 6. 输出定义

### 6.1 成功输出

- 周报文件已写回（UTF-8）
- 校验通过
- 返回摘要：
  - 成员信息
  - 目标周次（含 ISO 周）
  - 更新区块数量
  - 是否执行 Git、提交信息、推送结果

### 6.2 失败输出

- 明确中文错误信息
- 指出失败阶段（注册表读取/文件定位/字段校验/Git）
- 不回滚已成功写入的本地文件

## 7. 详细执行步骤（严格顺序）

### Step 0. 启动与缓存恢复

1. 读取 `.weekly_report_cache.json`（若存在）。
2. 若检测到同 `member_slug + week_start` 的未完成缓存，提示：
	- 1 恢复上次输入
	- 2 忽略缓存并重新开始

### Step 1. 参数归一化

1. 解析 `member_slug`（默认 songweihao）。
2. 解析 `week_start`：缺省时按系统当前日期取所在周周一。
3. 计算 `week_end = week_start + 6 days`。
4. 计算 ISO 周格式 `YYYY-Www`（用于提交信息）。

### Step 2. 成员校验

1. 从 `member_registry.json` 读取 `members`。
2. 按 `member_slug` 查找成员：
	- 未找到：终止并提示“成员不存在，请检查 member_slug”。
	- `is_active != true`：终止并提示“成员未激活，无法填写周报”。

### Step 3. 文件定位与存在性检查

1. 按路径规则拼接个人周报文件路径。
2. 若文件不存在：自动使用 `personal_weekly_report_template.md` 建档并填充基础信息。
3. 新建周报时，尝试读取“上一周个人周报”中的 `3.1/3.2` 任务，作为当前周报 `2.1/2.2` 的候选继承任务。

### Step 4. 读取并解析现有内容

1. 读取目标 Markdown。
2. 锁定并保护以下内容（禁止改动）：
	- 基本信息区
	- 所有章节标题
	- 所有表头
	- 所有以 `>` 开头的说明注释
	- 附录版本记录
3. 解析区块：
	- 2.1、2.2、3.1、3.2 表格数据行
	- 2.3 列表
	- 第四部分反馈列表
	- 第五部分方向负责人列表（仅负责人有效）

### Step 5. 已填内容处理分支

若四个任务表存在有效已填行（任务事项非空），先展示摘要并提供：

1. 全部重新填写（清空原任务行）
2. 按任务编号修改特定行
3. 追加新任务（保留现有行）
4. 退出

### Step 6. 区块交互填写（固定顺序）

交互形式要求：

- 系统必须逐字段发问（不要求用户复制整段模板后修改）。
- 用户每回答一项，系统即时做字段级校验并继续下一问。
- 新周报场景下，若检测到可继承任务，系统先询问“是否继承”，再逐条询问本周实际进展。

#### 6a) 2.1 本周对内

先问任务数量 `n`。逐行采集：

- 任务事项（必填）
- 本周进度总结
- 完成率（0-100）
- 状态偏差原因（若完成率 < 100，强制必填）
- 依赖（可空）
- 风险（可空）
- 设计与执行资产目录链接（可空，若填需 URL）
- 成果物链接（可空，若填需 URL）

#### 6b) 2.2 本周对外

开头提示：请确保事项描述适合对外汇报，突出成果与阶段性交付。字段与 2.1 相同。

#### 6c) 2.3 经验复盘

可选，逐条输入，空行结束。

#### 6d) 3.1 下周对内

先问任务数量 `n`。逐行采集：

- 任务事项（必填）
- 下周目标说明
- 预计完成率（0-100）
- 偏差原因（若预计完成率 < 100，强制必填）
- 依赖（可空）
- 风险（可空）
- 预计成果物（可空）
- 设计与执行资产目录链接（可空，若填需 URL）
- 预计成果物链接（可空，若填需 URL）

#### 6e) 3.2 下周对外

开头提示：请确保事项描述适合对外汇报，突出阶段目标与预计交付。字段与 3.1 相同。

#### 6f) 第四部分系统反馈

可选，逐条输入，空行结束。

#### 6g) 第五部分方向负责人

仅当 `is_direction_lead == "是"` 执行：

- 5.1 本周方向判断（逐条）
- 5.2 问题与上报事项（逐条）
- 5.3 下周方向重点（逐条）

### Step 7. 字段规则即时校验

1. 任务事项必填，建议“动作+对象+结果倾向”。
2. 完成率/预计完成率范围必须在 `0..100`。
3. `<100` 时偏差原因不可空。
4. 链接字段若非空，必须匹配 `^https?://.+`。

### Step 8. 硬性阻塞校验（收集完成后）

必须全部通过，否则返回错误清单并进入修正循环：

1. 2.2 至少 1 行有效任务（任务事项非空）。
2. 3.2 至少 1 行有效任务（任务事项非空）。
3. 任意任务行若完成率/预计完成率 <100，对应偏差原因非空。
4. 所有已填写链接字段均为完整 `http://` 或 `https://` URL。

### Step 9. 写回规则

仅替换：

- 四个任务表的数据行
- 2.3 列表
- 第四部分反馈列表
- 第五部分内容（若负责人填写）

严禁修改：

- 文件名
- 章节标题
- 表头
- 基本信息区
- 所有 `>` 说明注释
- 附录版本记录

使用 UTF-8 覆盖写回原文件。

模板兼容说明：若 3.1/3.2 表头不含“偏差原因”列，仍必须采集偏差原因；写回时将其合并写入该行风险列前缀（偏差原因：...；风险：...），以满足“<100 必有偏差原因”的硬约束，同时不改表头。

### Step 10. Git 提交与推送（可选）

触发条件：`auto_commit=true` 或用户确认“是”。

执行顺序固定（先拉取再交互，交互后提交）：

1. 启动阶段先执行：
	- `git fetch origin develop`
	- 切到本地 `develop`（不存在则从 `origin/develop` 创建）
	- `git pull origin develop --rebase`
2. 交互阶段新增/修改周报文件。
3. 交互结束后执行：
	- `git add <周报相对路径>`
4. 判断提交类型：
	- 该文件无历史：`add`
	- 该文件已有历史：`update`
5. 生成提交信息：
	- `kb(weekly_report): <add|update> report for <member_slug> <YYYY-Www>`
6. `git commit -m "..."`
7. `git push origin develop`

任何 Git 步骤失败：仅报错，不回滚已写回文件。

### Step 11. 结束与缓存清理

1. 成功后删除对应缓存条目。
2. 用户中断时询问是否保存到 `.weekly_report_cache.json`。

## 8. 数据结构约定（建议）

### 8.1 任务行模型 `TaskRow`

- `task_no`
- `task_item`
- `summary_or_goal`
- `rate`
- `deviation_reason`
- `dependency`
- `risk`
- `asset_url`
- `deliverable_url`
- `expected_deliverable`（仅 3.x）

### 8.2 缓存模型 `.weekly_report_cache.json`

- `member_slug`
- `week_start`
- `updated_at`
- `sections`（2.1,2.2,2.3,3.1,3.2,4,5）
- `mode`（重填/按行修改/追加）

## 9. 验证规则（可直接实现）

- `is_valid_url(v) := v=="" || match(^https?://.+, v)`
- `is_nonempty(v) := trim(v)!=""`
- `is_rate(v) := integer(v) && 0<=v<=100`
- `needs_reason(rate, reason) := (rate<100) => is_nonempty(reason)`
- `has_effective_task(rows) := exists r where is_nonempty(r.task_item)`

阻塞条件：

- `!has_effective_task(2.2) 或 !has_effective_task(3.2)`
- 任一 `!is_rate`
- 任一 `!needs_reason`
- 任一 `!is_valid_url`

## 10. 输出示例

### 10.1 交互片段（节选）

系统：检测到 2.2 已有 2 条任务。请选择：1重填 / 2按编号修改 / 3追加 / 4退出  
用户：2  
系统：请输入要修改的任务编号（如“任务二”）：  
用户：任务二  
系统：请输入“完成率(0-100)”：  
用户：80  
系统：完成率小于 100，请填写“状态偏差原因”（必填）：  
用户：上游接口字段本周二次变更，联调延后  
系统：请输入成果物链接（可空，需 http/https）：  
用户：https://example.com/report/pr-123

### 10.2 成功结果（节选）

- 已更新：2.1 3 行、2.2 2 行、3.1 2 行、3.2 2 行、2.3 2 条
- 校验：通过
- 文件：songweihao_weekly_report_2026_04_20_2026_04_26.md
- Git：已提交并推送到 develop
- Commit：kb(weekly_report): update report for songweihao 2026-W17

## 12. 自动化执行入口（新增）

### 12.1 默认执行（交互+自动提交）

```bash
python SkillTestLab/fill_weekly_report/fill_weekly_report.py \
	--repo-root /home/peter/repositories/tiangong \
	--member-slug songweihao \
	--week-start 2026-04-20
```

### 12.2 仅写回不提交

```bash
python SkillTestLab/fill_weekly_report/fill_weekly_report.py \
	--repo-root /home/peter/repositories/tiangong \
	--member-slug songweihao \
	--week-start 2026-04-20 \
	--no-auto-commit
```

### 12.3 行为约束

1. 执行技能时必须先同步最新 `develop`：`fetch -> checkout develop -> pull --rebase`。
2. 固定交互顺序：`2.1 -> 2.2 -> 2.3 -> 3.1 -> 3.2 -> 4 -> 5(负责人)`。
3. 交互过程中完成周报文件新增/修改，交互结束后执行 `add -> commit -> push`。
4. 若暂存区无改动，跳过提交与推送并给出提示。
5. 新周报生成时，默认尝试将上周 `3.1` 映射到本周 `2.1`、上周 `3.2` 映射到本周 `2.2`，并通过问答更新实际完成率与进度。

## 11. 非功能要求

1. 全程中文提示，错误信息可执行、可定位。
2. 不依赖人工解释即可执行。
3. 任意异常不破坏已保存的有效内容。
4. 对外区（2.2,3.2）优先保障可汇报性与可汇总性。