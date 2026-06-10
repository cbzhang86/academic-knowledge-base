#!/usr/bin/env python3
"""一键同步到 Obsidian Vault — 项目目录 → ObsidianVault

用法：
    python tools/sync.py                       # 整库同步（默认）
    python tools/sync.py --with-frontmatter    # 同步并增强元数据（替代 migrate_to_vault）
    python tools/sync.py --area 公共管理学     # 仅同步指定方向
"""

import sys, os, shutil, argparse, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

VAULT = DIRS["obsidian_vault"]
AREAS = ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]


def sync(src_rel, dst_rel=None):
    """同步文件或目录"""
    src = PROJECT_ROOT / src_rel
    dst = VAULT / (dst_rel or src_rel)
    if not src.exists():
        print(f"  ⚠️ 源不存在: {src_rel}")
        return False
    try:
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(dst.parent, exist_ok=True)
            shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"  ❌ {src_rel}: {e}")
        return False


def extract_metadata(content: str) -> dict:
    """从精读报告中提取元数据"""
    meta = {}
    m = re.search(r'\|\|\s*标题\s*\|\|\s*(.+?)\s*\|', content)
    if m: meta["title"] = m.group(1).strip()
    m = re.search(r'\|\|\s*作者（含机构）\s*\|\|\s*(.+?)\s*\|', content)
    if m: meta["author"] = m.group(1).strip()
    m = re.search(r'\|\|\s*期刊\s*\|\|\s*(.+?)\s*\|', content)
    if m: meta["journal"] = m.group(1).strip()
    m = re.search(r'\|\|\s*DOI\s*\|\|\s*(.+?)\s*\|', content)
    if m: meta["doi"] = m.group(1).strip()
    m = re.search(r'\|\|\s*CSSCI\s*\|\|\s*(.+?)\s*\|', content)
    if m: meta["cssci"] = m.group(1).strip()
    m = re.search(r'\*\*总分\*\*\s*\|\s*\*?(\d+\.?\d*)\s*/\s*5', content)
    if m: meta["score"] = m.group(1).strip()
    return meta


def enhance_frontmatter(src_md: Path, dst_md: Path):
    """读取精读报告，生成增强型 Frontmatter 写入目标"""
    try:
        content = src_md.read_text("utf-8", errors="ignore")
        meta = extract_metadata(content)

        # 构建新 Frontmatter
        area = ""
        for a in AREAS:
            if a in str(src_md):
                area = a
                break

        fm_lines = ["---"]
        fm_lines.append(f'title: "{meta.get("title", src_md.stem)}"')
        fm_lines.append(f'author: "{meta.get("author", "")}"')
        fm_lines.append(f'journal: "{meta.get("journal", "")}"')
        fm_lines.append(f'doi: "{meta.get("doi", "")}"')
        fm_lines.append(f'cssci: {"true" if "是" in meta.get("cssci", "") else "false"}')
        fm_lines.append(f'score: "{meta.get("score", "0")}"')
        fm_lines.append(f'area: "{area}"')
        fm_lines.append(f'created: "{datetime.now().strftime("%Y-%m-%d")}"')
        fm_lines.append("tags:")
        fm_lines.append("  - literature-note")
        fm_lines.append(f"  - {area}")
        fm_lines.append("---")

        # 去掉原文件的旧 Frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2]

        dst_md.parent.mkdir(parents=True, exist_ok=True)
        dst_md.write_text(fm_lines + "\n\n" + content.strip(), "utf-8")
        return True
    except Exception as e:
        print(f"  ⚠️ 增强 Frontmatter 失败: {src_md.name}: {e}")
        return False


def sync_reports(with_frontmatter: bool = False, area_filter: str = None):
    """同步精读报告"""
    areas = [area_filter] if area_filter else AREAS
    count = 0
    print("[01_论文精读]")
    for area in areas:
        src_dir = DIRS["02_reports"] / area
        if not src_dir.exists():
            continue
        dst_dir = VAULT / "01_论文精读" / area

        if with_frontmatter:
            # 逐个文件处理（增强 Frontmatter）
            src_dir.mkdir(parents=True, exist_ok=True)  # keep source intact
            enhanced = 0
            for f in src_dir.glob("*_精读报告.md"):
                dst_file = dst_dir / f.name
                if enhance_frontmatter(f, dst_file):
                    enhanced += 1
            print(f"  ✅ {area} ({enhanced} 篇，增强 Frontmatter)")
            count += 1
        else:
            # 批量复制（默认）
            if sync(f"02_精读报告/{area}", f"01_论文精读/{area}"):
                print(f"  ✅ {area}")
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="同步到 Obsidian Vault")
    parser.add_argument("--with-frontmatter", action="store_true", help="增强 Frontmatter（替代 migrate_to_vault）")
    parser.add_argument("--area", help="仅同步指定方向")
    args = parser.parse_args()

    print("=== 同步到 Obsidian Vault ===")
    print()

    count = 0

    # 1. 精读报告
    count += sync_reports(args.with_frontmatter, args.area)

    if not args.area:
        # 2. 写作素材
        print("\n[03_写作素材]")
        if sync("03_学术写作素材库", "03_写作素材"):
            print("  ✅ 全部素材")
            count += 1

        # 3. 研究方法
        print("\n[04_研究方法]")
        if sync("04_研究方法", "04_研究方法"):
            print("  ✅ 全部方法笔记")
            count += 1

        # 4. 报告
        print("\n[05_报告]")
        for sub in ["日报", "周报", "月报"]:
            if sync(f"05_报告/{sub}", f"05_报告/{sub}"):
                count += 1
                print(f"  ✅ {sub}")

        # 5. 研究输出
        print("\n[10_研究输出]")
        for sub in ["原料包", "ars_output", "定稿"]:
            p = f"10_研究输出/{sub}"
            if (PROJECT_ROOT / p).exists() and (PROJECT_ROOT / p).is_dir():
                if sync(p, p):
                    count += 1
                    print(f"  ✅ {sub}")

        # 6. 工具文档
        print("\n[14_工具脚本]")
        for f in ["进度看板.md", "检索日志.md"]:
            if sync(f"14_工具脚本/{f}", f"14_工具脚本/{f}"):
                print(f"  ✅ {f}")
                count += 1

        # 7. CLAUDE.md + README.md
        print("\n[根目录文档]")
        for f in ["CLAUDE.md", "README.md"]:
            if sync(f, f):
                print(f"  ✅ {f}")
                count += 1

        # 8. 研究启动器脚本
        print("\n[脚本同步]")
        if sync("14_工具脚本/报告/research_starter.py", "14_工具脚本/报告/research_starter.py"):
            print("  ✅ research_starter.py")
            count += 1

    print(f"\n=== 同步完成: {count} 项 ===")


if __name__ == "__main__":
    main()
