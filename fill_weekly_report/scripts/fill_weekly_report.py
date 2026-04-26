#!/usr/bin/env python3
"""交互式填写 Tiangong 个人周报，并可自动 Git 提交推送。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


URL_RE = re.compile(r"^https?://.+")
MAX_TASK_ROWS = 3
TASK_NAMES = ("任务一", "任务二", "任务三")


@dataclass
class Member:
    member_slug: str
    member_name_zh: str
    team_category: str
    direction: str
    is_direction_lead: str
    is_active: bool


@dataclass
class Task21Row:
    task_item: str
    summary: str
    rate: int
    deviation_reason: str
    dependency: str
    risk: str
    asset_url: str
    deliverable_url: str


@dataclass
class Task31Row:
    task_item: str
    goal: str
    rate: int
    deviation_reason: str
    dependency: str
    risk: str
    expected_deliverable: str
    asset_url: str
    deliverable_url: str


class ValidationError(Exception):
    pass


def run_cmd(repo_root: Path, cmd: List[str], print_cmd: bool = False) -> subprocess.CompletedProcess:
    if print_cmd:
        print("$", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(repo_root), text=True)
    if r.returncode != 0:
        raise ValidationError(f"Git 执行失败：{' '.join(cmd)}")
    return r


def today_week_monday(today: dt.date | None = None) -> dt.date:
    d = today or dt.date.today()
    return d - dt.timedelta(days=d.weekday())


def week_str(d: dt.date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def parse_date(v: str) -> dt.date:
    return dt.datetime.strptime(v, "%Y-%m-%d").date()


def underscore(d: dt.date) -> str:
    return d.strftime("%Y_%m_%d")


def ask(msg: str, required: bool = False, default: str = "") -> str:
    while True:
        prompt = msg
        if default:
            prompt += f" [默认: {default}]"
        prompt += "："
        v = input(prompt).strip()
        if not v and default:
            return default
        if required and not v:
            print("字段必填，请重新输入。")
            continue
        return v


def ask_int(msg: str, min_v: int = 0, max_v: int = 100, default: int | None = None) -> int:
    while True:
        p = msg
        if default is not None:
            p += f" [默认: {default}]"
        p += "："
        raw = input(p).strip()
        if not raw and default is not None:
            return default
        try:
            iv = int(raw)
        except ValueError:
            print("请输入整数。")
            continue
        if iv < min_v or iv > max_v:
            print(f"请输入 {min_v} 到 {max_v} 之间的整数。")
            continue
        return iv


def ask_url(msg: str, default: str = "") -> str:
    while True:
        v = ask(msg, required=False, default=default)
        if not v or URL_RE.match(v):
            return v
        print("链接必须是完整 URL（http:// 或 https://）。")


def sanitize(v: str) -> str:
    return v.replace("|", "／").strip()


def load_member(member_registry: Path, member_slug: str) -> Member:
    data = json.loads(member_registry.read_text(encoding="utf-8"))
    for m in data.get("members", []):
        if m.get("member_slug") == member_slug:
            member = Member(
                member_slug=m["member_slug"],
                member_name_zh=m.get("member_name_zh", ""),
                team_category=m.get("team_category", ""),
                direction=m.get("direction", ""),
                is_direction_lead=m.get("is_direction_lead", "否"),
                is_active=bool(m.get("is_active", False)),
            )
            if not member.is_active:
                raise ValidationError("成员未激活，无法填写周报。")
            return member
    raise ValidationError("成员不存在，请检查 member_slug。")


def report_path(repo_root: Path, member_slug: str, week_start: dt.date) -> Path:
    week_end = week_start + dt.timedelta(days=6)
    folder = repo_root / "kb" / "weekly_report_submission" / f"{week_start.year:04d}" / f"{week_start.month:02d}" / f"{underscore(week_start)}_{underscore(week_end)}" / "personal"
    return folder / f"{member_slug}_weekly_report_{underscore(week_start)}_{underscore(week_end)}.md"


def previous_week_report_path(repo_root: Path, member_slug: str, week_start: dt.date) -> Path:
    return report_path(repo_root, member_slug, week_start - dt.timedelta(days=7))


def render_report_template(template_text: str, member: Member, week_start: dt.date) -> str:
    week_end = week_start + dt.timedelta(days=6)
    week_id = week_str(week_start)
    return (
        template_text.replace("<week_id>", week_id)
        .replace("<week_start>", str(week_start))
        .replace("<week_end>", str(week_end))
        .replace("<member_name>", member.member_name_zh)
        .replace("<team_category>", member.team_category)
        .replace("<direction>", member.direction)
        .replace("<是/否>", member.is_direction_lead)
    )


def ensure_report_file(repo_root: Path, member: Member, week_start: dt.date) -> Tuple[Path, bool]:
    rpt = report_path(repo_root, member.member_slug, week_start)
    if rpt.exists():
        return rpt, False

    template_path = repo_root / "templates" / "weekly_report_submission" / "personal_weekly_report_template.md"
    if not template_path.exists():
        raise ValidationError(f"周报模板不存在，无法自动建档：{template_path}")

    template_text = template_path.read_text(encoding="utf-8")
    rendered = render_report_template(template_text, member, week_start)
    rpt.parent.mkdir(parents=True, exist_ok=True)
    rpt.write_text(rendered, encoding="utf-8")
    return rpt, True


def parse_table_cells(line: str) -> List[str]:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return []
    return [x.strip() for x in s.strip("|").split("|")]


def parse_section_rows(lines: List[str], section_title: str) -> List[List[str]]:
    sec_idx = find_line_index(lines, 0, section_title)
    header_idx = find_line_index(lines, sec_idx, "| 任务编号 |")
    row_idx = header_idx + 2
    rows: List[List[str]] = []
    while row_idx < len(lines) and lines[row_idx].startswith("| 任务"):
        cells = parse_table_cells(lines[row_idx])
        if cells:
            rows.append(cells)
        row_idx += 1
    return rows


def bootstrap_from_previous_report(repo_root: Path, member_slug: str, week_start: dt.date) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    prev = previous_week_report_path(repo_root, member_slug, week_start)
    if not prev.exists():
        return [], []

    lines = prev.read_text(encoding="utf-8").splitlines()
    rows_31 = parse_section_rows(lines, "### 3.1 下周工作计划概述（对内）")
    rows_32 = parse_section_rows(lines, "### 3.2 下周工作计划概述（对外）")

    # 3.x 列结构：任务编号, 任务事项, 下周目标说明, 预计完成率, 依赖, 风险, 预计成果物, 资产链接, 预计成果物链接
    prefill_21: List[Dict[str, str]] = []
    prefill_22: List[Dict[str, str]] = []

    for cells in rows_31:
        if len(cells) >= 2 and cells[1].strip():
            prefill_21.append(
                {
                    "task_item": cells[1].strip(),
                    "previous_goal": cells[2].strip() if len(cells) > 2 else "",
                    "previous_dependency": cells[4].strip() if len(cells) > 4 else "",
                    "previous_risk": cells[5].strip() if len(cells) > 5 else "",
                    "previous_asset_url": cells[7].strip() if len(cells) > 7 else "",
                    "previous_deliverable_url": cells[8].strip() if len(cells) > 8 else "",
                }
            )

    for cells in rows_32:
        if len(cells) >= 2 and cells[1].strip():
            prefill_22.append(
                {
                    "task_item": cells[1].strip(),
                    "previous_goal": cells[2].strip() if len(cells) > 2 else "",
                    "previous_dependency": cells[4].strip() if len(cells) > 4 else "",
                    "previous_risk": cells[5].strip() if len(cells) > 5 else "",
                    "previous_asset_url": cells[7].strip() if len(cells) > 7 else "",
                    "previous_deliverable_url": cells[8].strip() if len(cells) > 8 else "",
                }
            )

    return prefill_21[:MAX_TASK_ROWS], prefill_22[:MAX_TASK_ROWS]


def find_line_index(lines: List[str], start: int, prefix: str) -> int:
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise ValidationError(f"未找到目标行：{prefix}")


def replace_table_rows(lines: List[str], section_title: str, row_lines: List[str]) -> List[str]:
    sec_idx = find_line_index(lines, 0, section_title)
    header_idx = find_line_index(lines, sec_idx, "| 任务编号 |")
    sep_idx = header_idx + 1
    if sep_idx >= len(lines) or not lines[sep_idx].startswith("|---"):
        raise ValidationError(f"{section_title} 表头分隔行异常。")
    row_start = sep_idx + 1
    row_end = row_start
    while row_end < len(lines) and lines[row_end].startswith("| 任务"):
        row_end += 1
    if row_end - row_start <= 0:
        raise ValidationError(f"{section_title} 未找到任务数据行。")
    new_lines = lines[:row_start] + row_lines + lines[row_end:]
    return new_lines


def replace_bullets(
    lines: List[str],
    section_title: str,
    bullet_startswith: str,
    item_label: str,
    values: List[str],
    fallback_empty: str,
) -> List[str]:
    sec_idx = find_line_index(lines, 0, section_title)
    first_bullet = -1
    for i in range(sec_idx, len(lines)):
        if lines[i].startswith(bullet_startswith):
            first_bullet = i
            break
    if first_bullet < 0:
        raise ValidationError(f"{section_title} 未找到列表项。")

    j = first_bullet
    while j < len(lines) and lines[j].startswith("- "):
        j += 1

    if values:
        out = [f"- {item_label} {idx}：{sanitize(v)}" for idx, v in enumerate(values, 1)]
    else:
        out = [fallback_empty]

    return lines[:first_bullet] + out + lines[j:]


def make_rows_21(rows: List[Task21Row]) -> List[str]:
    out: List[str] = []
    for i in range(MAX_TASK_ROWS):
        if i < len(rows):
            r = rows[i]
            out.append(
                "| {no} | {a} | {b} | {c} | {d} | {e} | {f} | {g} | {h} |".format(
                    no=TASK_NAMES[i],
                    a=sanitize(r.task_item),
                    b=sanitize(r.summary),
                    c=r.rate,
                    d=sanitize(r.deviation_reason),
                    e=sanitize(r.dependency),
                    f=sanitize(r.risk),
                    g=sanitize(r.asset_url),
                    h=sanitize(r.deliverable_url),
                )
            )
        else:
            out.append(f"| {TASK_NAMES[i]} |  |  |  |  |  |  |  |  |")
    return out


def make_rows_31(rows: List[Task31Row]) -> List[str]:
    out: List[str] = []
    for i in range(MAX_TASK_ROWS):
        if i < len(rows):
            r = rows[i]
            risk = r.risk
            if r.rate < 100:
                risk = f"偏差原因：{r.deviation_reason}；风险：{risk}" if risk else f"偏差原因：{r.deviation_reason}"
            out.append(
                "| {no} | {a} | {b} | {c} | {d} | {e} | {f} | {g} | {h} |".format(
                    no=TASK_NAMES[i],
                    a=sanitize(r.task_item),
                    b=sanitize(r.goal),
                    c=r.rate,
                    d=sanitize(r.dependency),
                    e=sanitize(risk),
                    f=sanitize(r.expected_deliverable),
                    g=sanitize(r.asset_url),
                    h=sanitize(r.deliverable_url),
                )
            )
        else:
            out.append(f"| {TASK_NAMES[i]} |  |  |  |  |  |  |  |  |")
    return out


def validate_common_rows(
    rows: List[object],
    section_name: str,
    rate_label: str,
    deliverable_label: str,
) -> None:
    for i, r in enumerate(rows, 1):
        task_item = str(getattr(r, "task_item", "")).strip()
        rate = int(getattr(r, "rate", -1))
        deviation_reason = str(getattr(r, "deviation_reason", "")).strip()
        asset_url = str(getattr(r, "asset_url", "")).strip()
        deliverable_url = str(getattr(r, "deliverable_url", "")).strip()

        if not task_item:
            raise ValidationError(f"{section_name} 第{i}行任务事项不能为空。")
        if not (0 <= rate <= 100):
            raise ValidationError(f"{section_name} 第{i}行{rate_label}必须在 0..100。")
        if rate < 100 and not deviation_reason:
            raise ValidationError(f"{section_name} 第{i}行{rate_label}<100，偏差原因必填。")
        for label, url in [("资产链接", asset_url), (deliverable_label, deliverable_url)]:
            if url and not URL_RE.match(url):
                raise ValidationError(f"{section_name} 第{i}行{label}格式非法。")


def validate_task21(rows: List[Task21Row], section_name: str) -> None:
    validate_common_rows(rows, section_name, "完成率", "成果物链接")


def validate_task31(rows: List[Task31Row], section_name: str) -> None:
    validate_common_rows(rows, section_name, "预计完成率", "预计成果物链接")


def ask_rate_and_reason(rate_prompt: str, reason_prompt: str) -> Tuple[int, str]:
    rate = ask_int(rate_prompt, 0, 100)
    if rate < 100:
        return rate, ask(reason_prompt, required=True)
    return rate, ""


def collect_task21(section_name: str, prefills: List[Dict[str, str]] | None = None) -> List[Task21Row]:
    print(f"\n开始填写 {section_name}")
    use_prefill = False
    prefills = prefills or []
    if prefills:
        print(f"检测到上周计划可继承 {len(prefills)} 条。")
        yn = ask("是否将上周下周计划自动贴到本周计划并逐条更新进度？(Y/n)", default="Y")
        use_prefill = yn.strip().lower() in {"", "y", "yes"}

    n = len(prefills) if use_prefill else ask_int("请输入任务数量(0-3)", 0, 3, 1)
    rows: List[Task21Row] = []
    for i in range(n):
        print(f"\n{section_name} - 任务{i+1}")
        if use_prefill:
            p = prefills[i]
            print(f"继承任务事项：{p.get('task_item', '')}")
            if p.get("previous_goal"):
                print(f"上周计划目标参考：{p.get('previous_goal', '')}")
            task_item = ask("任务事项", required=True, default=p.get("task_item", ""))
            summary = ask("本周进度总结", required=False, default="延续上周计划执行，已按实际进展更新。")
            dependency_default = p.get("previous_dependency", "")
            risk_default = p.get("previous_risk", "")
            asset_default = p.get("previous_asset_url", "")
            deliverable_default = p.get("previous_deliverable_url", "")
        else:
            task_item = ask("任务事项", required=True)
            summary = ask("本周进度总结", required=False)
            dependency_default = ""
            risk_default = ""
            asset_default = ""
            deliverable_default = ""

        rate, deviation_reason = ask_rate_and_reason(
            "完成率(0-100)",
            "状态偏差原因(完成率<100必填)",
        )
        dependency = ask("依赖(可空)", default=dependency_default)
        risk = ask("风险(可空)", default=risk_default)
        asset_url = ask_url("设计与执行资产目录链接(可空, 需http/https)", default=asset_default)
        deliverable_url = ask_url("成果物链接(可空, 需http/https)", default=deliverable_default)
        rows.append(
            Task21Row(task_item, summary, rate, deviation_reason, dependency, risk, asset_url, deliverable_url)
        )
    return rows


def collect_task31(section_name: str) -> List[Task31Row]:
    print(f"\n开始填写 {section_name}")
    n = ask_int("请输入任务数量(0-3)", 0, 3, 1)
    rows: List[Task31Row] = []
    for i in range(n):
        print(f"\n{section_name} - 任务{i+1}")
        task_item = ask("任务事项", required=True)
        goal = ask("下周目标说明", required=False)
        rate, deviation_reason = ask_rate_and_reason(
            "预计完成率(0-100)",
            "偏差原因(预计完成率<100必填)",
        )
        dependency = ask("依赖(可空)")
        risk = ask("风险(可空)")
        expected_deliverable = ask("预计成果物(可空)")
        asset_url = ask_url("设计与执行资产目录链接(可空, 需http/https)")
        deliverable_url = ask_url("预计成果物链接(可空, 需http/https)")
        rows.append(
            Task31Row(
                task_item,
                goal,
                rate,
                deviation_reason,
                dependency,
                risk,
                expected_deliverable,
                asset_url,
                deliverable_url,
            )
        )
    return rows


def collect_list(section_name: str, hint: str) -> List[str]:
    print(f"\n开始填写 {section_name}（空行结束）")
    print(hint)
    out: List[str] = []
    while True:
        v = input("- ").strip()
        if not v:
            break
        out.append(v)
    return out


def sync_latest_develop(repo_root: Path) -> None:
    run_cmd(repo_root, ["git", "fetch", "origin", "develop"], print_cmd=True)
    run_cmd(repo_root, ["git", "checkout", "develop"], print_cmd=True)
    run_cmd(repo_root, ["git", "pull", "--rebase", "origin", "develop"], print_cmd=True)


def run_git(repo_root: Path, rel_report_path: Path, member_slug: str, week_id: str) -> None:
    run_cmd(repo_root, ["git", "checkout", "develop"], print_cmd=True)
    run_cmd(repo_root, ["git", "add", str(rel_report_path)], print_cmd=True)

    # 若无变更，不再提交
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_root))
    if diff.returncode == 0:
        print("未检测到可提交改动，跳过提交与推送。")
        return

    run_cmd(repo_root, ["git", "commit", "-m", f"kb(weekly_report): update report for {member_slug} {week_id}"], print_cmd=True)
    run_cmd(repo_root, ["git", "push", "origin", "develop"], print_cmd=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="交互式填写 Tiangong 个人周报")
    parser.add_argument("--repo-root", default="/home/peter/repositories/tiangong", help="tiangong 仓库根目录")
    parser.add_argument("--member-slug", default="songweihao", help="成员 slug")
    parser.add_argument("--week-start", default="", help="周一日期，格式 YYYY-MM-DD；默认取当前周周一")
    parser.add_argument("--no-auto-commit", action="store_true", help="仅写回，不提交推送")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    week_start = parse_date(args.week_start) if args.week_start else today_week_monday()
    week_end = week_start + dt.timedelta(days=6)
    week_id = week_str(week_start)

    member_registry = repo_root / "templates" / "weekly_report_submission" / "member_registry.json"
    if not member_registry.exists():
        raise ValidationError(f"未找到成员注册表：{member_registry}")

    print("\n步骤：先同步最新 develop 分支")
    sync_latest_develop(repo_root)

    member = load_member(member_registry, args.member_slug)
    rpt, created_new = ensure_report_file(repo_root, member, week_start)

    prefill_21: List[Dict[str, str]] = []
    prefill_22: List[Dict[str, str]] = []
    if created_new:
        prefill_21, prefill_22 = bootstrap_from_previous_report(repo_root, args.member_slug, week_start)

    print("\nfill_weekly_report 自动化流程")
    print(f"成员：{member.member_name_zh} ({member.member_slug})")
    print(f"周次：{week_id} / {week_start} ~ {week_end}")
    print(f"目标文件：{rpt}")
    print(f"建档状态：{'新建' if created_new else '已存在'}")
    print(f"自动提交：{'否' if args.no_auto_commit else '是'}")

    rows_21 = collect_task21("2.1 本周工作总结概述（对内）", prefills=prefill_21)
    rows_22 = collect_task21("2.2 本周工作总结概述（对外）", prefills=prefill_22)
    exp = collect_list("2.3 本周经验总结与复盘", "请输入每条经验；直接回车结束。")
    rows_31 = collect_task31("3.1 下周工作计划概述（对内）")
    rows_32 = collect_task31("3.2 下周工作计划概述（对外）")
    feedback = collect_list("四、对 SuanhaiOS 系统使用的反馈", "请输入每条反馈；无反馈可直接回车。")

    lead_judgement: List[str] = []
    lead_issue: List[str] = []
    lead_focus: List[str] = []
    if member.is_direction_lead == "是":
        lead_judgement = collect_list("5.1 本周方向整体判断", "请输入每条判断；回车结束。")
        lead_issue = collect_list("5.2 本周发现的方向级问题与需上报事项", "请输入每条问题/事项；回车结束。")
        lead_focus = collect_list("5.3 下周方向级推进重点", "请输入每条重点；回车结束。")

    validate_task21(rows_21, "2.1")
    validate_task21(rows_22, "2.2")
    validate_task31(rows_31, "3.1")
    validate_task31(rows_32, "3.2")

    if not any(x.task_item.strip() for x in rows_22):
        raise ValidationError("硬性校验失败：2.2 至少 1 行有效任务。")
    if not any(x.task_item.strip() for x in rows_32):
        raise ValidationError("硬性校验失败：3.2 至少 1 行有效任务。")

    lines = rpt.read_text(encoding="utf-8").splitlines()
    lines = replace_table_rows(lines, "### 2.1 本周工作总结概述（对内）", make_rows_21(rows_21))
    lines = replace_table_rows(lines, "### 2.2 本周工作总结概述（对外）", make_rows_21(rows_22))
    lines = replace_bullets(
        lines,
        "### 2.3 本周经验总结与复盘",
        "- 经验 / 复盘 ",
        "经验 / 复盘",
        exp,
        "- 经验 / 复盘 1：",
    )
    lines = replace_table_rows(lines, "### 3.1 下周工作计划概述（对内）", make_rows_31(rows_31))
    lines = replace_table_rows(lines, "### 3.2 下周工作计划概述（对外）", make_rows_31(rows_32))
    lines = replace_bullets(
        lines,
        "## 四、对 SuanhaiOS 系统使用的反馈",
        "- 反馈 ",
        "反馈",
        feedback,
        "- 反馈 1：本周暂时无反馈。",
    )

    if member.is_direction_lead == "是":
        lines = replace_bullets(
            lines,
            "### 5.1 本周方向整体判断",
            "- 判断 ",
            "判断",
            lead_judgement,
            "- 判断 1：",
        )
        lines = replace_bullets(
            lines,
            "### 5.2 本周发现的方向级问题与需上报事项",
            "- 问题 / 事项 ",
            "问题 / 事项",
            lead_issue,
            "- 问题 / 事项 1：",
        )
        lines = replace_bullets(
            lines,
            "### 5.3 下周方向级推进重点",
            "- 重点 ",
            "重点",
            lead_focus,
            "- 重点 1：",
        )

    rpt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n已写回：{rpt}")

    if not args.no_auto_commit:
        rel = rpt.relative_to(repo_root)
        run_git(repo_root, rel, args.member_slug, week_id)
        print("已自动提交并推送到 develop。")
    else:
        print("已完成写回，未执行提交推送。")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as e:
        print(f"错误：{e}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\n已中断。")
        raise SystemExit(130)
