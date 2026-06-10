#!/usr/bin/env python3
"""
错误自积累系统 (error_accumulator.py)
功能：自动记录和积累工作流中的错误，支持后续分析和修复

用法:
    # 记录一条错误
    python utils/error_accumulator.py log --type "采集" --source "ncpssd" --msg "登录失效"

    # 查看高频错误
    python utils/error_accumulator.py stats --top 10

    # 导出错误报告
    python utils/error_accumulator.py export --format markdown
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from typing import List, Dict

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

# ============================================================
# 配置
# ============================================================
LOG_DIR = PROJECT_ROOT / "logs"
ERROR_LOG = LOG_DIR / "errors.jsonl"

ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# 核心功能
# ============================================================
def log_error(error_type: str, source: str, message: str, context: str = "",
              frequency: int = 1, frequency_period: str = "total"):
    """记录一条错误日志"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": error_type,
        "source": source,
        "message": message,
        "context": context,
        "frequency": frequency,
        "period": frequency_period,
    }

    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[LOGGED] {error_type} | {source} | {message[:60]}")
    return entry


def read_errors() -> List[Dict]:
    """读取所有错误日志"""
    errors = []
    if not ERROR_LOG.exists():
        return errors

    with open(ERROR_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    errors.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return errors


def get_error_stats(top: int = 10) -> Dict:
    """统计错误分布"""
    errors = read_errors()
    if not errors:
        return {"total": 0, "by_type": {}, "by_source": {}, "trend": {}}

    # 按类型统计
    type_counts = Counter(e["type"] for e in errors)
    source_counts = Counter(e["source"] for e in errors)

    # 按天统计趋势
    daily = defaultdict(int)
    for e in errors:
        day = e["timestamp"][:10]
        daily[day] += 1

    return {
        "total": len(errors),
        "by_type": dict(type_counts.most_common(top)),
        "by_source": dict(source_counts.most_common(top)),
        "trend": dict(sorted(daily.items())),
    }


def export_markdown() -> str:
    """导出错误报告为Markdown"""
    errors = read_errors()
    stats = get_error_stats()

    lines = [
        "# 错误积累报告",
        f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 总错误数: {stats['total']}",
        "\n## 按类型分布\n",
        "| 类型 | 次数 |",
        "|------|-----:|",
    ]

    for type_name, count in stats["by_type"].items():
        lines.append(f"| {type_name} | {count} |")

    lines.extend([
        "\n## 按来源分布\n",
        "| 来源 | 次数 |",
        "|------|-----:|",
    ])

    for source, count in stats["by_source"].items():
        lines.append(f"| {source} | {count} |")

    lines.extend([
        "\n## 每日趋势\n",
        "| 日期 | 次数 |",
        "|------|-----:|",
    ])

    for day, count in stats["trend"].items():
        lines.append(f"| {day} | {count} |")

    lines.extend([
        "\n## 最近错误\n",
    ])

    for e in errors[-10:]:
        lines.append(f"\n### {e['timestamp']}")
        lines.append(f"- **类型**: {e['type']}")
        lines.append(f"- **来源**: {e['source']}")
        lines.append(f"- **消息**: {e['message']}")
        if e.get('context'):
            lines.append(f"- **上下文**: {e['context']}")

    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Error Accumulator")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # log
    log_parser = subparsers.add_parser("log", help="Log an error")
    log_parser.add_argument("--type", required=True, help="Error type")
    log_parser.add_argument("--source", required=True, help="Error source")
    log_parser.add_argument("--msg", required=True, help="Error message")
    log_parser.add_argument("--context", default="", help="Additional context")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show error statistics")
    stats_parser.add_argument("--top", type=int, default=10, help="Top N")

    # export
    export_parser = subparsers.add_parser("export", help="Export error report")
    export_parser.add_argument("--format", default="markdown", help="Output format")
    export_parser.add_argument("--output", help="Output file path")

    args = parser.parse_args()

    if args.command == "log":
        log_error(args.type, args.source, args.msg, args.context)

    elif args.command == "stats":
        stats = get_error_stats(top=args.top)
        print(f"\nTotal Errors: {stats['total']}")
        print("\nBy Type:")
        for t, c in stats['by_type'].items():
            print(f"  {t}: {c}")
        print("\nBy Source:")
        for s, c in stats['by_source'].items():
            print(f"  {s}: {c}")
        print("\nDaily Trend:")
        for d, c in stats['trend'].items():
            print(f"  {d}: {c}")

    elif args.command == "export":
        md = export_markdown()
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"[OK] Exported to: {args.output}")
        else:
            print(md)

    else:
        # 默认：显示统计
        stats = get_error_stats()
        print(f"Error Accumulator - Total: {stats['total']}")
        if stats['total'] > 0:
            print(f"Use 'python error_accumulator.py stats' for details")
            print(f"Use 'python error_accumulator.py export' for full report")
        else:
            print("No errors recorded yet.")


if __name__ == "__main__":
    main()
