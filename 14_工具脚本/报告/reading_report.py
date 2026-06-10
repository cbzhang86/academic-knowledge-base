#!/usr/bin/env python3
"""
三级报告系统 (reading_report.py)
功能：生成粗读报告、精读报告索引、跨篇分析报告

三级结构:
  Level 1 - 粗读报告: PDF元数据 + 一句话判断（保留/淘汰）
  Level 2 - 精读报告: 完整模板字段（analysis_template.md）
  Level 3 - 跨篇沉淀: 多篇对比 + 研究空白识别

用法:
    python report/reading_report.py level1 --pdf ...
    python report/reading_report.py level2 --report ...
    python report/reading_report.py level3 --area 公共管理学
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
KNOWLEDGE_BASE = Path("D:/公共管理科研")
PDF_DIR = KNOWLEDGE_BASE / "01_论文原文"
REPORT_DIR = KNOWLEDGE_BASE / "04_精读报告"
RAW_READ_DIR = KNOWLEDGE_BASE / "05_知识库索引" / "元数据库"
LOG_DIR = KNOWLEDGE_BASE / "logs"
TEMPLATE_PATH = KNOWLEDGE_BASE / "analysis_template.md"

RESEARCH_AREAS = ["公共管理学", "社会学", "老龄化", "青少年研究"]


# ============================================================
# Level 1: 粗读报告生成
# ============================================================
def generate_level1(pdf_path: Path, area: str = "") -> dict:
    """生成粗读条目"""
    import hashlib

    # 计算MD5
    h = hashlib.md5()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)

    # 文件名解析
    fname = pdf_path.stem
    year = ""
    if re.match(r'^\d{4}', fname):
        year = fname[:4]

    entry = {
        "title": fname,
        "year": year,
        "pdf_size_kb": pdf_path.stat().st_size // 1024,
        "md5": h.hexdigest(),
        "area": area,
        "verdict": "待审",  # 保留/淘汰/待审
        "review_date": "",
        "notes": "",
        "priority": "",    # P0/P1/P2
    }
    return entry


def batch_level1(area: str, output: str = ""):
    """批量生成某方向的粗读条目"""
    pdf_dir = PDF_DIR / area
    if not pdf_dir.exists():
        print(f"[ERROR] PDF directory not found: {pdf_dir}")
        return

    entries = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        entry = generate_level1(pdf, area)
        entries.append(entry)
        print(f"[{area}] {pdf.name} -> {entry['md5'][:8]}...")

    # 保存到元数据库
    RAW_READ_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d")
    output_file = output or str(RAW_READ_DIR / f"{area}_粗读记录_{timestamp}.md")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# {area} 粗读记录 ({timestamp})\n\n")
        f.write(f"| # | 标题 | 年份 | 大小 | MD5 | 判定 | 优先级 | 备注 |\n")
        f.write(f"|---|------|:----:|:---:|:---:|:----:|:-----:|------|\n")
        for i, e in enumerate(entries, 1):
            f.write(f"| {i} | {e['title'][:40]} | {e['year']} | {e['pdf_size_kb']}K | {e['md5'][:8]} | {e['verdict']} | {e['priority']} | {e['notes']} |\n")

    print(f"\n[OK] 粗读记录已保存: {output_file}")
    return entries


# ============================================================
# Level 2: 精读报告索引
# ============================================================
def generate_index(area: str) -> str:
    """生成某方向的精读报告索引"""
    report_dir = REPORT_DIR / area
    if not report_dir.exists():
        return f"[ERROR] Report directory not found: {report_dir}"

    # 读取所有精读报告
    reports = []
    for md_file in sorted(report_dir.glob("*.md")):
        if md_file.name == "00_精读索引.md" or md_file.name.endswith(".summary.md"):
            continue
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        reports.append({
            "file": md_file.name,
            "content": content,
        })

    # 提取关键字段
    table_rows = []
    for i, r in enumerate(reports, 1):
        title = extract_field(r["content"], r"\| 标题 \|(.+)")
        authors = extract_field(r["content"], r"\| 作者.*?\|(.+)")
        journal = extract_field(r["content"], r"\| 期刊 \|(.+)")

        # 提取质量评分
        score_match = re.search(r"\|\s*\*\*总分\*\*\s*\|\s*\*?([\d.]+)\s*/\s*5", r["content"])
        score = score_match.group(1) if score_match else ""

        table_rows.append((i, r["file"], title, authors, journal, score))

    # 生成索引 markdown
    lines = [
        f"# {area} 精读索引\n",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"> 报告总数: {len(reports)}\n",
        "\n| 序号 | 报告文件 | 标题 | 作者 | 期刊 | 评分 |",
        "|:----:|---------|------|------|------|:----:|",
    ]
    for i, fname, title, authors, journal, score in table_rows:
        t = title[:35] if len(title) > 35 else title
        a = authors[:12] if len(authors) > 12 else authors
        j = journal[:20] if len(journal) > 20 else journal
        lines.append(f"| {i} | {fname} | {t} | {a} | {j} | {score} |")

    index_content = "\n".join(lines)

    # 保存
    index_path = report_dir / "00_精读索引.md"
    index_path.write_text(index_content, encoding="utf-8")
    print(f"[OK] 精读索引已更新: {index_path}")
    return index_content


def extract_field(content: str, pattern: str) -> str:
    """从Markdown表格中提取字段"""
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return ""


# ============================================================
# Level 3: 跨篇分析
# ============================================================
def cross_paper_analysis(area: str, min_reports: int = 5):
    """跨篇沉淀分析：识别模式、空白、可复用框架"""
    report_dir = REPORT_DIR / area
    if not report_dir.exists():
        print(f"[ERROR] Report directory not found: {report_dir}")
        return

    # 收集报告
    reports = []
    for md_file in sorted(report_dir.glob("*.md")):
        if md_file.name == "00_精读索引.md" or md_file.name.endswith(".summary.md"):
            continue
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        reports.append({
            "file": md_file.name,
            "content": content,
        })

    if len(reports) < min_reports:
        print(f"[INFO] 仅 {len(reports)} 篇报告，至少需要 {min_reports} 篇才能进行有意义的跨篇分析")
        return

    # 提取研究方法分布
    methods = defaultdict(int)
    theories = defaultdict(int)
    topics = defaultdict(int)

    for r in reports:
        c = r["content"]

        # 方法
        m = extract_field(c, r"\| 具体方法 \|(.+)")
        if m:
            for method in re.split(r'[,，、]', m):
                methods[method.strip()] += 1

        # 理论
        theory_section = re.search(r"### 理论框架\s*\n(.*?)(?=\n###|\Z)", c, re.DOTALL)
        if theory_section:
            for line in theory_section.group(1).strip().split('\n')[:3]:
                line = line.strip().strip('-* ')
                if line and len(line) > 2:
                    theories[line] += 1

    # 生成分析报告
    timestamp = datetime.now().strftime("%Y%m%d")
    output_path = KNOWLEDGE_BASE / "output" / f"{area}_跨篇分析_{timestamp}.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {area} 跨篇分析报告\n\n")
        f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> 分析报告总数: {len(reports)}\n\n")

        f.write("## 研究方法分布\n\n")
        f.write("| 方法 | 频次 |\n|------|:----:|\n")
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            f.write(f"| {method} | {count} |\n")

        f.write("\n## 理论框架分布\n\n")
        f.write("| 理论/框架 | 频次 |\n|-----------|:----:|\n")
        for theory, count in sorted(theories.items(), key=lambda x: -x[1])[:15]:
            f.write(f"| {theory} | {count} |\n")

        f.write("\n## 研究空白建议\n\n")
        f.write("基于当前文献覆盖，以下方向可能存在研究空白：\n\n")
        # 自动识别覆盖不足的方法
        low_methods = [m for m, c in methods.items() if c == 1]
        if low_methods:
            f.write(f"- 方法多样性不足：以下方法仅出现1次 ({', '.join(low_methods[:5])})\n")
        f.write("- 跨方法三角验证的论文较少\n")
        f.write("- 纵向追踪研究/面板数据方法有待加强\n")

    print(f"[OK] 跨篇分析报告: {output_path}")
    return output_path


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="三级报告系统")
    sub = parser.add_subparsers(dest="command")

    # Level 1
    l1 = sub.add_parser("level1", help="生成粗读报告")
    l1.add_argument("--area", required=True, help="研究方向")
    l1.add_argument("--pdf", help="单篇PDF路径（可选，默认批量）")
    l1.add_argument("--output", help="输出文件")

    # Level 2
    l2 = sub.add_parser("level2", help="生成精读索引")
    l2.add_argument("--area", required=True, help="研究方向")

    # Level 3
    l3 = sub.add_parser("level3", help="跨篇分析")
    l3.add_argument("--area", required=True, help="研究方向")
    l3.add_argument("--min", type=int, default=5, help="最少报告数")

    args = parser.parse_args()

    if args.command == "level1":
        if args.pdf:
            entry = generate_level1(Path(args.pdf), args.area)
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            batch_level1(args.area, args.output or "")

    elif args.command == "level2":
        generate_index(args.area)

    elif args.command == "level3":
        cross_paper_analysis(args.area, args.min)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()