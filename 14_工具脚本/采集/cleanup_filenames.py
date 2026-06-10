#!/usr/bin/env python3
"""采集文件清洗工具 — 修复脏文件名、清理临时文件、重新分配方向

用法:
    python cleanup_filenames.py scan         # 预览：列出需修复的文件
    python cleanup_filenames.py fix          # 实际修复
    python cleanup_filenames.py fix --dry-run # 试运行（不实际重命名）

修复项:
  - 双后缀 .pdf.pdf → .pdf
  - arXiv ID 文件名 → 尝试从 PDF 元数据提取标题
  - 方向错乱 → 重新检测
  - 清理 ~/*.pdf 临时文件
"""
import sys, os, re, shutil
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# ── 项目根 ──────────────────────────────────────────────
_ENV_ROOT = os.environ.get("KNOWLEDGE_ROOT")
if _ENV_ROOT:
    PROJECT_ROOT = Path(_ENV_ROOT).resolve()
else:
    _cwd = Path.cwd().resolve()
    for _parent in [_cwd] + list(_cwd.parents):
        if (_parent / "config" / "structure.yaml").exists():
            PROJECT_ROOT = _parent
            break
    else:
        PROJECT_ROOT = _cwd

sys.path.insert(0, str(PROJECT_ROOT))
try:
    from global_config import DIRS
except ImportError:
    DIRS = {"01_raw": PROJECT_ROOT / "01_论文原文"}

PDF_DIR = DIRS["01_raw"]

# 研究方向判断关键词（需与 base.py AREA_CONFIG 保持一致）
AREA_KWS = {
    "公共管理学": ["公共", "治理", "政府", "政策", "行政", "绩效"],
    "社会学": ["社会", "阶层", "流动", "分层", "教育", "收入", "劳动"],
    "老龄化": ["老龄", "养老", "老年", "银发", "延迟退休"],
    "青少年研究": ["青少年", "青年", "未成年人", "学生", "网络行为"],
}


def detect_area_by_name(name: str) -> str:
    """根据文件名关键词判断研究方向"""
    lower = name.lower()
    for area, kws in AREA_KWS.items():
        for kw in kws:
            if kw in lower:
                return area
    return None


def get_pdf_title_from_file(path: Path) -> str:
    """尝试从 PDF 元数据提取标题（PyMuPDF）"""
    try:
        import fitz
        doc = fitz.open(str(path))
        meta = doc.metadata or {}
        doc.close()
        title = (meta.get("title") or "").strip()
        # 排除纯 arXiv ID / 无意义元数据
        if title and len(title) > 10 and not re.match(r'^\d+\.\d+', title):
            return title
    except Exception:
        pass
    return None


def scan_files() -> list:
    """扫描所有 PDF 文件，列出需修复项"""
    issues = []
    for subdir in sorted(PDF_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.glob("*.pdf")):
            name = f.name
            stem = f.stem
            issues_found = []

            # 1. 双后缀
            if name.lower().endswith(".pdf.pdf"):
                issues_found.append("双后缀")

            # 2. arXiv ID 文件名（纯数字+小数点）
            if re.match(r'^\d+\.\d+', stem) or re.match(r'^\d{4}\.\d+', stem):
                issues_found.append("arXiv_ID文件名")

            # 3. 方向错乱（文件名关键词与所在目录不匹配）
            correct_area = detect_area_by_name(name)
            if correct_area and correct_area != subdir.name:
                issues_found.append(f"方向错乱: 当前在 [{subdir.name}] 应归 [{correct_area}]")

            # 4. 文件名超短/含 ~ 临时标记
            if '~' in name:
                issues_found.append("含临时标记")

            if issues_found:
                issues.append({
                    "path": f,
                    "dir": subdir.name,
                    "current_name": name,
                    "issues": issues_found,
                })
    return issues


def suggest_new_name(f: Path) -> str:
    """建议新文件名——只做格式清理，不从 PDF 元数据猜标题"""
    name = f.name
    stem = f.stem

    # 1. 去掉双后缀
    if name.lower().endswith(".pdf.pdf"):
        name = stem[:-4] + ".pdf" if stem.lower().endswith(".pdf") else stem + ".pdf"
        stem = Path(name).stem

    # 2. arXiv ID 文件名（纯数字+小数点）→ 加 arXiv_ 前缀
    if re.match(r'^\d+\.\d+', stem):
        name = f"arXiv_{stem}.pdf"

    return name


def get_target_dir(current_dir: str, name: str) -> str:
    """检测目标方向"""
    correct = detect_area_by_name(name)
    if correct and correct != current_dir:
        return correct
    return None


def cmd_scan():
    """扫描并显示问题列表"""
    print(f"\n🔍 扫描: {PDF_DIR}")
    print("=" * 60)
    issues = scan_files()
    if not issues:
        print("✅ 未发现问题")
        return

    print(f"发现 {len(issues)} 个文件需修复:\n")
    for i, item in enumerate(issues, 1):
        print(f"  [{i}] {item['dir']}/")
        print(f"      当前: {item['current_name']}")
        print(f"      问题: {', '.join(item['issues'])}")
        new_name = suggest_new_name(item['path'])
        if new_name != item['current_name']:
            print(f"      建议: {new_name}")
        target = get_target_dir(item['dir'], item['current_name'])
        if target:
            print(f"      建议移入: {target}/")
        print()


def cmd_fix(dry_run: bool = False):
    """执行修复"""
    issues = scan_files()
    if not issues:
        print("✅ 无需修复")
        return

    renamed = 0
    moved = 0
    for item in issues:
        f = item["path"]
        new_name = suggest_new_name(f)
        target_dir_name = get_target_dir(item["dir"], item["current_name"])

        # 计算最终路径
        final_dir = PDF_DIR / (target_dir_name or item["dir"])
        final_path = final_dir / new_name

        # 如果文件名不变且目录不变，跳过
        if f.name == final_path.name and f.parent == final_path.parent:
            continue

        if dry_run:
            print(f"  [试运行] 将重命名/移动:")
            print(f"    来源: {f.relative_to(PDF_DIR)}")
            print(f"    目标: {final_path.relative_to(PDF_DIR)}")
            continue

        # 确保目标目录存在
        final_dir.mkdir(parents=True, exist_ok=True)

        # 如果目标已存在同名文件，加序号
        if final_path.exists():
            stem = final_path.stem
            counter = 1
            while final_path.exists():
                final_path = final_dir / f"{stem}_{counter}.pdf"
                counter += 1

        shutil.move(str(f), str(final_path))
        if target_dir_name:
            moved += 1
        if new_name != item["current_name"]:
            renamed += 1

    if not dry_run:
        print(f"\n✅ 修复完成: 重命名 {renamed} 个, 移动 {moved} 个")


def cmd_clear_temp():
    """清理 ~/*.pdf 临时文件"""
    temp_files = list(Path.home().glob("*.pdf"))
    if not temp_files:
        print("  无临时 PDF 文件")
        return
    print(f"  发现 {len(temp_files)} 个临时文件:")
    for f in temp_files:
        size = f.stat().st_size / 1024
        print(f"    删除: {f.name} ({size:.0f}KB)")
        f.unlink()
    print(f"  已清理")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="采集文件清洗工具")
    sub = parser.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="扫描需修复的文件")
    p_fix = sub.add_parser("fix", help="执行修复")
    p_fix.add_argument("--dry-run", action="store_true", help="试运行，不实际修改")
    p_clear = sub.add_parser("clear-temp", help="清理 ~/*.pdf 临时文件")

    args = parser.parse_args()
    if args.cmd == "scan":
        cmd_scan()
    elif args.cmd == "fix":
        cmd_fix(dry_run=args.dry_run)
    elif args.cmd == "clear-temp":
        cmd_clear_temp()
    else:
        parser.print_help()
