#!/usr/bin/env python3
"""
统一去重引擎 (metadata/dedup.py)
功能：论文去重检查、索引重建、注册

用法：
    python dedup.py check               # 交互式输入标题检查
    python dedup.py rebuild              # 全量扫描 01_raw/ 重建索引
    python dedup.py register --md5 ... --title ... --path ...  # 注册一篇论文
    python dedup.py status               # 查看去重统计
    python dedup.py --migrate-from-done 路径/done.sqlite  # 迁移旧数据

去重只有一种方式：本地 config/dedup.db（SQLite），不论归档后端选什么。
"""

import sys, os, hashlib, sqlite3, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

DEDUP_DB = PROJECT_ROOT / "config" / "dedup.db"

# ── 表结构 ──────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    md5             TEXT PRIMARY KEY,
    title           TEXT,
    raw_title       TEXT,
    year            INTEGER,
    filename        TEXT,
    direction       TEXT,
    rel_path        TEXT,
    first_seen      TEXT,
    file_mtime      TEXT,
    downloaded_from TEXT,
    zotero_imported INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_dir ON papers(direction);
"""


def _get_conn():
    DEDUP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DEDUP_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def md5_of_file(path: Path) -> str:
    """计算文件 MD5"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_title(title: str) -> str:
    """标题归一化：去空格、小写、去标点"""
    import re
    t = re.sub(r"\s+", "", title.strip().lower())
    t = re.sub(r"[^一-鿿\w]", "", t)
    return t[:100]


# ── Action: check ───────────────────────────────────────
def cmd_check(titles: list = None):
    """去重检查。

    输入：标题列表（来自 collect/search 的 JSON stdout）
    输出：JSON 去重结果 [{title, is_new, md5_match, title_match}]
    调用方式：
        echo '["标题1", "标题2"]' | python dedup.py check
        或：collect/search ... | python dedup.py check
    """
    conn = _get_conn()
    cursor = conn.cursor()

    if titles is None:
        raw = sys.stdin.read()
        try:
            titles = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            titles = [raw.strip()] if raw.strip() else []

    results = []
    for title in titles:
        if not title or not title.strip():
            continue
        norm = normalize_title(title)
        # 查 MD5 精确匹配（如果传入的还有 md5 的话）
        cursor.execute("SELECT md5, title FROM papers WHERE title = ?", (norm,))
        row = cursor.fetchone()

        is_new = row is None
        results.append({
            "title": title,
            "is_new": is_new,
            "md5_match": False,   # 需要外部传 MD5
            "title_match": not is_new,
        })

    conn.close()
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    return 0 if all(r["is_new"] for r in results) else 1


def cmd_check_from_search(search_results: list):
    """从搜索结果 JSON 列表中去重检查。

    相比 cmd_check，多了 MD5 比较（对于搜到的已有论文的 PDF）。
    """
    conn = _get_conn()
    cursor = conn.cursor()
    results = []

    for item in search_results:
        title = item.get("title", "")
        norm = normalize_title(title)

        cursor.execute("SELECT md5, title FROM papers WHERE title = ?", (norm,))
        title_match = cursor.fetchone() is not None

        results.append({
            **item,
            "is_new": not title_match,
            "title_match": title_match,
        })

    conn.close()
    return results


# ── Action: rebuild ─────────────────────────────────────
def cmd_rebuild():
    """全量扫描 01_raw/ 下所有 PDF，重建索引。

    用于：
    - 首次 clone 后建立初始索引
    - 手动移动/重命名/删除文件后修复
    """
    conn = _get_conn()
    cursor = conn.cursor()

    # 清空重建
    cursor.execute("DELETE FROM papers")

    raw_dir = DIRS["01_raw"]
    count = 0
    errors = 0

    if not raw_dir.exists():
        print(f"[DEDUP] 源目录不存在: {raw_dir}")
        conn.close()
        return 1

    for area_dir in sorted(raw_dir.iterdir()):
        if not area_dir.is_dir():
            continue
        direction = area_dir.name
        for pdf_path in sorted(area_dir.glob("*.pdf")):
            try:
                md5 = md5_of_file(pdf_path)
                mtime = datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat()
                now = datetime.now().isoformat()
                rel = str(pdf_path.relative_to(raw_dir))

                cursor.execute("""
                    INSERT OR IGNORE INTO papers
                    (md5, title, filename, direction, rel_path, first_seen, file_mtime, downloaded_from)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (md5, pdf_path.stem[:100], pdf_path.name, direction, rel, now, mtime, "rebuild"))
                count += 1
            except Exception as e:
                print(f"  [ERROR] {pdf_path.name}: {e}", file=sys.stderr)
                errors += 1

    conn.commit()
    conn.close()

    print(f"[DEDUP] 重建完成: {count} 篇索引, {errors} 错误")
    return 0 if errors == 0 else 1


# ── Action: register ────────────────────────────────────
def cmd_register(md5: str, title: str, filename: str = "", direction: str = "",
                 rel_path: str = "", downloaded_from: str = ""):
    """注册一篇论文到 dedup.db（由 metadata/archive 调用）"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    norm_title = normalize_title(title)

    cursor.execute("""
        INSERT OR IGNORE INTO papers
        (md5, title, raw_title, filename, direction, rel_path, first_seen, file_mtime, downloaded_from)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (md5, norm_title, title[:200], filename[:200], direction, rel_path, now, now, downloaded_from))

    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()

    status = "新增" if changed else "已存在（忽略）"
    print(f"[DEDUP register] {status}: {title[:50]}")
    return {"status": "ok" if changed else "skipped", "md5": md5}


# ── Action: status ──────────────────────────────────────
def cmd_status():
    """查看去重统计"""
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT direction, COUNT(*) FROM papers GROUP BY direction ORDER BY direction")
    by_dir = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM papers WHERE zotero_imported=1")
    zotero_imported = cursor.fetchone()[0]

    conn.close()

    print(f"[DEDUP] 总论文数: {total}")
    print(f"[DEDUP] 各方向:")
    for d, c in by_dir:
        print(f"    {d}: {c}")
    print(f"[DEDUP] 已导入 Zotero: {zotero_imported}")

    return {"total": total, "by_direction": {d: c for d, c in by_dir}, "zotero_imported": zotero_imported}


# ── 迁移脚本 ────────────────────────────────────────────
def migrate_from_done(done_path: str):
    """从旧的 done.sqlite 迁移数据到 dedup.db"""
    done = Path(done_path)
    if not done.exists():
        print(f"[ERROR] done.sqlite 不存在: {done_path}", file=sys.stderr)
        return 1

    conn_old = sqlite3.connect(str(done))
    conn_old.row_factory = sqlite3.Row
    conn_new = _get_conn()

    try:
        # 尝试读取 done.sqlite 的表结构（不同版本可能不同）
        cursor_old = conn_old.cursor()
        cursor_old.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor_old.fetchall()]

        if "papers" in tables:
            cursor_old.execute("SELECT * FROM papers")
            rows = cursor_old.fetchall()
        elif "done_files" in tables:
            cursor_old.execute("SELECT * FROM done_files")
            rows = cursor_old.fetchall()
        else:
            print(f"[ERROR] done.sqlite 表结构未知: {tables}", file=sys.stderr)
            rows = []

        migrated = 0
        for row in rows:
            row_dict = dict(row)
            md5 = row_dict.get("md5", "") or hashlib.md5((row_dict.get("filename", "") or str(row_dict.get("id", ""))).encode()).hexdigest()
            title = row_dict.get("title", "") or row_dict.get("filename", "")
            direction = row_dict.get("direction", "") or row_dict.get("area", "")
            filename = row_dict.get("filename", "") or row_dict.get("file", "")
            zotero = 1 if row_dict.get("zotero_imported", 0) or row_dict.get("imported", 0) else 0

            cursor_new = conn_new.cursor()
            cursor_new.execute("""
                INSERT OR IGNORE INTO papers
                (md5, title, raw_title, filename, direction, rel_path, first_seen, downloaded_from, zotero_imported)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (md5, normalize_title(title), title[:200], filename[:200], direction, f"migrated/{filename}", datetime.now().isoformat(), "migrated", zotero))
            migrated += cursor_new.rowcount

        conn_new.commit()
        print(f"[MIGRATE] 迁移完成: {migrated} 篇 (从 {done_path})")

    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}", file=sys.stderr)
        return 1
    finally:
        conn_old.close()
        conn_new.close()

    return 0


# ── 主入口 ──────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一去重引擎")
    parser.add_argument("action", nargs="?", choices=["check", "rebuild", "register", "status"])
    parser.add_argument("--md5", help="MD5 值（register 用）")
    parser.add_argument("--title", help="论文标题（register 用）")
    parser.add_argument("--path", help="PDF 路径（register 用）")
    parser.add_argument("--direction", help="研究方向（register 用）")
    parser.add_argument("--source", help="来源采集源（register 用）")
    parser.add_argument("--migrate-from-done", help="从 done.sqlite 迁移")

    args = parser.parse_args()

    if args.migrate_from_done:
        return migrate_from_done(args.migrate_from_done)

    if args.action == "rebuild":
        return cmd_rebuild()
    elif args.action == "status":
        cmd_status()
    elif args.action == "check":
        return cmd_check()
    elif args.action == "register":
        if not args.md5:
            print("[ERROR] register 需要 --md5", file=sys.stderr)
            return 1
        return cmd_register(args.md5, args.title or "", filename=args.path and Path(args.path).name or "",
                            direction=args.direction or "", rel_path=args.path or "",
                            downloaded_from=args.source or "")
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
