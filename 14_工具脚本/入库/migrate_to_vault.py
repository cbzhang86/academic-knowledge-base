#!/usr/bin/env python3
"""
精读报告全量迁移脚本 — 从 04_精读报告/ 迁移到 ObsidianVault/01_论文精读/
功能：
1. 复制 .md 文件到 vault 目录
2. 自动添加 Zotero 兼容的 YAML Frontmatter
3. 嵌入 Dataview 兼容字段
4. 报告转换进度
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Windows GBK 兼容
if sys.stdout.encoding and sys.stdout.encoding.upper() in ("GBK", "GB2312", "CP936"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 配置
KNOWLEDGE_BASE = Path("D:/公共管理科研")
SRC_DIR = KNOWLEDGE_BASE / "04_精读报告"
VAULT_DIR = KNOWLEDGE_BASE / "ObsidianVault" / "01_论文精读"
METHOD_DIR = KNOWLEDGE_BASE / "03_方法论与理论框架"
MATERIAL_DIR = KNOWLEDGE_BASE / "06_学术写作素材库"
CLASSIC_DIR = KNOWLEDGE_BASE / "08_经典文献引用池"

# 方向名映射（目录名→显示名）
AREA_MAP = {
    "公共管理学": "公共管理学",
    "社会学": "社会学",
    "老龄化": "老龄化研究",
    "青少年研究": "青少年研究",
}


def detect_area(filepath: Path) -> str:
    """从文件路径推断研究方向"""
    for area in AREA_MAP:
        if area in filepath.parts:
            return AREA_MAP[area]
    return "未分类"


def extract_metadata(content: str) -> dict:
    """从精读报告中提取元数据"""
    meta = {}

    # 标题
    m = re.search(r'[\|\|]\s*标题\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["title"] = m.group(1).strip()

    # 作者
    m = re.search(r'[\|\|]\s*作者（含机构）\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["author"] = m.group(1).strip()

    # 期刊
    m = re.search(r'[\|\|]\s*期刊\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["journal"] = m.group(1).strip()

    # 年份
    m = re.search(r'[\|\|]\s*年份/卷/期/页码\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["year"] = m.group(1).strip()[:4]

    # DOI
    m = re.search(r'[\|\|]\s*DOI\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["doi"] = m.group(1).strip()

    # 关键词
    m = re.search(r'[\|\|]\s*关键词\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["keywords"] = m.group(1).strip()

    # 方法类型
    m = re.search(r'方法类型\s*\|\s*(.+?)\s*\|', content)
    if m:
        meta["method"] = m.group(1).strip()

    # CSSCI
    m = re.search(r'[\|\|]\s*CSSCI\s*[\|\|]\s*(.+?)\s*[\|\|]', content)
    if m:
        meta["cssci"] = m.group(1).strip()

    # 质量评分总分
    m = re.search(r'\*\*总分\*\*\s*\|\s*\*?(\d+\.?\d*)\s*/\s*5', content)
    if m:
        meta["score"] = m.group(1).strip()

    # 理论框架
    m = re.search(r'###\s*理论框架\s*\n+(.+?)(?=\n###|\n##|\Z)', content, re.DOTALL)
    if m:
        meta["theory"] = m.group(1).strip()[:100]

    # 核心发现（前100字）
    m = re.search(r'###\s*核心发现\s*\n+(.+?)(?=\n###|\n##|\Z)', content, re.DOTALL)
    if m:
        meta["findings"] = m.group(1).strip()[:100]

    return meta


def make_frontmatter(meta: dict, area: str) -> str:
    """生成 Zotero 兼容的 YAML Frontmatter"""
    lines = ["---"]
    lines.append(f'title: "{meta.get("title", "")}"')
    lines.append("tags:")
    lines.append("  - literature-note")
    lines.append("  - reading-note")
    lines.append(f'  - {area}')
    lines.append(f'created: "{datetime.now().strftime("%Y-%m-%d")}"')

    if meta.get("author"):
        lines.append(f'author: "{meta["author"]}"')
    if meta.get("year"):
        lines.append(f'year: {meta["year"][:4]}')
    if meta.get("journal"):
        lines.append(f'journal: "{meta["journal"]}"')
    if meta.get("doi"):
        lines.append(f'doi: "{meta["doi"]}"')
    if meta.get("cssci"):
        lines.append(f'cssci: {"true" if "是" in meta["cssci"] else "false"}')
    if meta.get("score"):
        lines.append(f'score: {meta["score"]}')
    if meta.get("keywords"):
        lines.append(f'keywords: "{meta["keywords"]}"')

    lines.append(f'theme: "{meta.get("title", "")[:40]}"')
    lines.append(f'study_area: ""')
    lines.append(f'data_source: ""')
    lines.append(f'methodology: "{meta.get("method", "")}"')
    lines.append(f'core_variable: ""')
    lines.append(f'key_finding: "{meta.get("findings", "")[:50]}"')
    lines.append(f'relevance: ""')
    lines.append("---")

    return "\n".join(lines)


def convert_report(src: Path, dst: Path) -> dict:
    """转换一篇精读报告"""
    result = {"src": str(src), "dst": str(dst), "status": "ok", "error": ""}

    try:
        content = src.read_text("utf-8", errors="ignore")
        area = detect_area(src)
        meta = extract_metadata(content)

        # 构建新内容：Frontmatter + 原内容
        frontmatter = make_frontmatter(meta, area)

        # 去掉原文件中可能已存在的 Frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2]

        new_content = frontmatter + "\n\n" + content.strip()

        # 写入目标文件
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(new_content, "utf-8")

        result["title"] = meta.get("title", src.stem)[:50]
        result["area"] = area

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def main():
    stats = defaultdict(int)

    print(f"{'='*70}")
    print(f"  精读报告迁移工具")
    print(f"{'='*70}\n")

    print(f"  源目录: {SRC_DIR}")
    print(f"  目标目录: {VAULT_DIR}\n")

    # 收集所有精读报告
    all_reports = []
    for area_dir in sorted(SRC_DIR.iterdir()):
        if not area_dir.is_dir():
            continue
        for md_file in sorted(area_dir.glob("*_精读报告.md")):
            all_reports.append(md_file)

    print(f"  找到 {len(all_reports)} 篇精读报告\n")

    # 逐篇转换
    for i, src in enumerate(all_reports, 1):
        # 计算目标路径（去掉编号前缀）
        area = detect_area(src)
        dst_name = src.name
        # 去掉编号前缀（如 "01_" → ""）
        dst_name = re.sub(r'^\d+_', '', dst_name)

        dst = VAULT_DIR / area / dst_name

        result = convert_report(src, dst)
        stats[result["status"]] += 1

        status_icon = "✅" if result["status"] == "ok" else "❌"
        print(f"  [{i:3d}/{len(all_reports)}] {status_icon} [{result.get('area', area)}] {result.get('title', src.name)[:50]}")
        if result["error"]:
            print(f"        Error: {result['error']}")

    # 统计
    print(f"\n{'='*70}")
    print(f"  迁移完成!")
    print(f"  ✅ 成功: {stats['ok']} 篇")
    if stats.get("error"):
        print(f"  ❌ 失败: {stats['error']} 篇")
    print(f"  目标位置: {VAULT_DIR}")

    # 各方向统计
    print(f"\n  各方向分布:")
    for area_dir in sorted(VAULT_DIR.iterdir()):
        if not area_dir.is_dir():
            continue
        count = len(list(area_dir.glob("*.md")))
        if count > 0:
            print(f"    {area_dir.name}: {count} 篇")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
