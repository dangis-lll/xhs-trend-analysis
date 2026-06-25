from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from storage.paths import get_project_root


def quote_task_arg(value: str) -> str:
    return f'"{value}"' if any(ch.isspace() for ch in value) else value


def build_task_run_command(*, python_exe: str, project_root: Path, domain_id: str = "", date_value: str = "today") -> str:
    parts = [
        "cmd",
        "/c",
        f"cd /d {quote_task_arg(str(project_root))}",
        "&&",
        quote_task_arg(python_exe),
        "-m",
        "pipeline.run_scheduled",
        "--date",
        date_value,
    ]
    if domain_id:
        parts.extend(["--domain", domain_id])
    return " ".join(parts)


def build_schtasks_command(
    *,
    task_name: str,
    time_value: str,
    task_run_command: str,
    force: bool = False,
) -> list[str]:
    command = [
        "schtasks",
        "/Create",
        "/SC",
        "DAILY",
        "/TN",
        task_name,
        "/TR",
        task_run_command,
        "/ST",
        time_value,
    ]
    if force:
        command.append("/F")
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成或安装 Windows 任务计划，用于定时调用 pipeline.run_scheduled。")
    parser.add_argument("--task-name", default="XHSTrendAnalysis", help="Windows 任务计划名称")
    parser.add_argument("--time", default="09:30", help="每日运行时间，格式 HH:MM")
    parser.add_argument("--domain", default="", help="只调度指定 domain；默认检查所有开启 schedule 的 domain")
    parser.add_argument("--date", default="today", help="传给 run_scheduled 的日期参数")
    parser.add_argument("--python", default=sys.executable, help="Python 可执行文件路径")
    parser.add_argument("--project-root", type=Path, default=get_project_root(), help="项目根目录")
    parser.add_argument("--force", action="store_true", help="覆盖同名任务")
    parser.add_argument("--install", action="store_true", help="实际调用 schtasks 安装；默认只打印命令")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_run_command = build_task_run_command(
        python_exe=args.python,
        project_root=args.project_root,
        domain_id=args.domain,
        date_value=args.date,
    )
    command = build_schtasks_command(
        task_name=args.task_name,
        time_value=args.time,
        task_run_command=task_run_command,
        force=args.force,
    )
    print("任务实际执行命令：")
    print(task_run_command)
    print("\nschtasks 命令：")
    print(" ".join(quote_task_arg(part) for part in command))
    if not args.install:
        print("\n当前为预览模式。确认无误后添加 --install 才会创建 Windows 任务。")
        return 0
    completed = subprocess.run(command)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

