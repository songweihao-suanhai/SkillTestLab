#!/usr/bin/env python3
"""
交互式填写 Tiangong 个人周报，并可自动 Git 提交推送。

默认行为：
1) 按 2.1 -> 2.2 -> 2.3 -> 3.1 -> 3.2 -> 4 -> 5(负责人) 顺序交互
2) 完成硬性校验
3) 写回周报文件
4) 自动提交并推送到 develop（可通过 --no-auto-commit 关闭）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


URL_RE = re.compile(r"^https?://.+")


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


def ask_url(msg: str) -> str:
    while True:
        v = ask(msg, required=False)
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
    names = ["任务一", "任务二", "任务三"]
    out: List[str] = []
    for i in range(3):
        if i < len(rows):
            r = rows[i]
            out.append(
                "| {no} | {a} | {b} | {c} | {d} | {e} | {f} | {g} | {h} |".format(
                    no=names[i],
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
            out.append(f"| {names[i]} |  |  |  |  |  |  |  |  |")
    return out


def make_rows_31(rows: List[Task31Row]) -> List[str]:
    names = ["任务一", "任务二", "任务三"]
    out: List[str] = []
    for i in range(3):
        if i < len(rows):
            r = rows[i]
            risk = r.risk
            if r.rate < 100:
                risk = f"偏差原因：{r.deviation_reason}；风险：{risk}" if risk else f"偏差原因：{r.deviation_reason}"
            out.append(
                "| {no} | {a} | {b} | {c} | {d} | {e} | {f} | {g} | {h} |".format(
                    no=names[i],
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
            out.append(f"| {names[i]} |  |  |  |  |  |  |  |  |")
    return out


def validate_task21(rows: List[Task21Row], section_name: str) -> None:
    for i, r in enumerate(rows, 1):
        if not r.task_item.strip():
            raise ValidationError(f"{section_name} 第{i}行任务事项不能为空。")
        if not (0 <= r.rate <= 100):
            raise ValidationError(f"{section_name} 第{i}行完成率必须在 0..100。")
        if r.rate < 100 and not r.deviation_reason.strip():
            raise ValidationError(f"{section_name} 第{i}行完成率<100，偏差原因必填。")
        for label, url in [("资产链接", r.asset_url), ("成果物链接", r.deliverable_url)]:
            if url and not URL_RE.match(url):
                raise ValidationError(f"{section_name} 第{i}行{label}格式非法。")


def validate_task31(rows: List[Task31Row], section_name: str) -> None:
    for i, r in enumerate(rows, 1):
        if not r.task_item.strip():
            raise ValidationError(f"{section_name} 第{i}行任务事项不能为空。")
        if not (0 <= r.rate <= 100):
            raise ValidationError(f"{section_name} 第{i}行预计完成率必须在 0..100。")
        if r.rate < 100 and not r.deviation_reason.strip():
            raise ValidationError(f"{section_name} 第{i}行预计完成率<100，偏差原因必填。")
        for label, url in [("资产链接", r.asset_url), ("预计成果物链接", r.deliverable_url)]:
            if url and not URL_RE.match(url):
                raise ValidationError(f"{section_name} 第{i}行{label}格式非法。")


def collect_task21(section_name: str) -> List[Task21Row]:
    print(f"\n开始填写 {section_name}")
    n = ask_int("请输入任务数量(0-3)", 0, 3, 1)
    rows: List[Task21Row] = []
    for i in range(n):
        print(f"\n{section_name} - 任务{i+1}")
        task_item = ask("任务事项", required=True)
        summary = ask("本周进度总结", required=False)
        rate = ask_int("完成率(0-100)", 0, 100)
        deviation_reason = ""
        if rate < 100:
            deviation_reason = ask("状态偏差原因(完成率<100必填)", required=True)
        dependency = ask("依赖(可空)")
        risk = ask("风险(可空)")
        asset_url = ask_url("设计与执行资产目录链接(可空, 需http/https)")
        deliverable_url = ask_url("成果物链接(可空, 需http/https)")
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
        rate = ask_int("预计完成率(0-100)", 0, 100)
        deviation_reason = ""
        if rate < 100:
            deviation_reason = ask("偏差原因(预计完成率<100必填)", required=True)
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


def run_git(repo_root: Path, rel_report_path: Path, member_slug: str, week_id: str) -> None:
    def run(cmd: List[str]) -> None:
        print("$", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(repo_root), text=True)
        if r.returncode != 0:
            raise ValidationError(f"Git 执行失败：{' '.join(cmd)}")

    run(["git", "fetch", "origin", "develop"])
    run(["git", "checkout", "develop"])
    run(["git", "add", str(rel_report_path)])

    # 若无变更，不再提交
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_root))
    if diff.returncode == 0:
        print("未检测到可提交改动，跳过提交与推送。")
        return

    run(["git", "commit", "-m", f"kb(weekly_report): update report for {member_slug} {week_id}"])
    run(["git", "pull", "--rebase", "origin", "develop"])
    run(["git", "push", "origin", "develop"])


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

    member = load_member(member_registry, args.member_slug)
    rpt = report_path(repo_root, args.member_slug, week_start)
    if not rpt.exists():
        raise ValidationError(f"周报文件不存在，请先建档：{rpt}")

    print("=" * 72)
    print("fill_weekly_report 自动化流程")
    print(f"成员：{member.member_name_zh} ({member.member_slug})")
    print(f"周次：{week_id} / {week_start} ~ {week_end}")
    print(f"目标文件：{rpt}")
    print(f"自动提交：{'否' if args.no_auto_commit else '是'}")
    print("=" * 72)

    rows_21 = collect_task21("2.1 本周工作总结概述（对内）")
    rows_22 = collect_task21("2.2 本周工作总结概述（对外）")
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
