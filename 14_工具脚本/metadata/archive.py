#!/usr/bin/env python3
"""统一归档入口 (metadata/archive.py) — 按配置选后端，批量归档 PDF。

用法：
    python metadata/archive.py --paths PDF路径列表          # 批量归档
    python metadata/archive.py --paths xxx.pdf --backend zotero  # 指定后端
    python metadata/archive.py status                      # 查看归档后端状态

流程：
    1. 读 config/metadata.yaml 获取选定的后端
    2. 对每个 PDF，实例化对应后端并调用 archive()
    3. 输出 JSON 结果
"""

import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS, METADATA_BACKEND

DEDUP_DB = PROJECT_ROOT / "config" / "dedup.db"
META_CFG = PROJECT_ROOT / "config" / "metadata.yaml"


def _get_backend(backend_key: str = None):
    """获取后端实例。"""
    from metadata.backends import get_backend

    if not backend_key:
        backend_key = METADATA_BACKEND

    return get_backend(backend_key, PROJECT_ROOT, DEDUP_DB)


def cmd_archive(paths: list, backend_key: str = None, direction: str = "", source: str = ""):
    """归档 PDF 文件。

    Args:
        paths: PDF 路径列表
        backend_key: 后端类型（filesystem/zotero），不指定则从配置读取
        direction: 研究方向
        source: 来源采集源
    """
    if not paths:
        # 从 stdin 读取 JSON 列表
        raw = sys.stdin.read().strip()
        if raw:
            try:
                items = json.loads(raw)
                paths = [item if isinstance(item, str) else item.get("path", item.get("pdf_path", ""))
                         for item in (items if isinstance(items, list) else [items])]
                paths = [p for p in paths if p]
            except json.JSONDecodeError:
                paths = [raw]

    if not paths:
        print("[ERROR] 请指定 PDF 路径（--paths 或 stdin JSON）", file=sys.stderr)
        return 1

    backend = _get_backend(backend_key)
    results = []

    for pdf_path in paths:
        p = Path(pdf_path)
        if not p.exists():
            results.append({"path": pdf_path, "status": "error", "message": "文件不存在"})
            continue

        paper_info = {
            "title": p.stem,
            "filename": p.name,
            "direction": direction or _detect_direction(p),
            "rel_path": str(p.relative_to(DIRS["01_raw"])) if DIRS["01_raw"] in p.parents else "",
            "downloaded_from": source or "manual",
        }

        result = backend.archive(p, paper_info)
        results.append({"path": pdf_path, **result})
        status_icon = "✅" if result["status"] == "ok" else ("⏭️" if result["status"] == "skipped" else "❌")
        print(f"  {status_icon} {p.name}: {result['message']}")

    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    return 0


def cmd_status():
    """查看归档后端状态"""
    print("=" * 60)
    print("  归档后端状态")
    print("=" * 60)

    print(f"\n  当前配置后端: {METADATA_BACKEND}")
    print(f"  配置文件: {META_CFG}")
    print(f"  配置文件存在: {META_CFG.exists()}")
    print(f"\n  dedup.db: {DEDUP_DB}")
    print(f"  dedup.db 存在: {DEDUP_DB.exists()}")

    if DEDUP_DB.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(DEDUP_DB))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM papers")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM papers WHERE zotero_imported=1")
            zotero_count = cursor.fetchone()[0]
            conn.close()
            print(f"  已索引论文: {count}")
            print(f"  已导入 Zotero: {zotero_count}")
        except Exception as e:
            print(f"  读取 dedup.db 失败: {e}")

    print(f"\n  可用后端:")
    try:
        from metadata.backends import get_available_backends
        for key, name, cls in get_available_backends(PROJECT_ROOT):
            available = "✅" if cls.detect(PROJECT_ROOT) else "❌"
            print(f"    {available} {key}: {name}")
    except Exception as e:
        print(f"  加载后端失败: {e}")

    print("=" * 60)


def _detect_direction(pdf_path: Path) -> str:
    """从路径推断研究方向"""
    for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
        if d in str(pdf_path):
            return d
    # 从文件名关键词推断
    fname = pdf_path.stem
    dirs_map = {
        "公共管理学": ["公共", "治理", "政府", "政策", "行政", "绩效"],
        "社会学": ["社会", "阶层", "流动", "分层", "教育", "资本"],
        "老龄化": ["老龄", "养老", "老年", "银发", "退休"],
        "青少年研究": ["青少年", "青年", "未成年人", "学生", "网络行为"],
    }
    for d, kws in dirs_map.items():
        if any(kw in fname for kw in kws):
            return d
    return "交叉研究"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一归档入口")
    sub = parser.add_subparsers(dest="cmd")

    p_archive = sub.add_parser("archive", help="归档 PDF")
    p_archive.add_argument("--paths", nargs="*", help="PDF 路径列表")
    p_archive.add_argument("--backend", help="归档后端（覆盖 config）")
    p_archive.add_argument("--direction", help="研究方向")
    p_archive.add_argument("--source", default="manual", help="来源采集源")

    p_status = sub.add_parser("status", help="查看后端状态")

    args = parser.parse_args()

    if args.cmd == "archive":
        return cmd_archive(args.paths or [], args.backend, args.direction or "", args.source or "")
    elif args.cmd == "status":
        cmd_status()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
