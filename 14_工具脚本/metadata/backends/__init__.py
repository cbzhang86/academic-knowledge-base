"""归档后端统一接口。

设计原则：
  archive() 是模板方法，封装了"归档 + register"的原子操作：
  1. 调用子类的 _do_archive() 执行具体归档逻辑
  2. 成功后自动调用 _call_dedup_register()
  3. 任何一步失败返回错误状态，不产生脏数据
"""

import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from abc import ABC, abstractmethod


class ArchiveBackend(ABC):
    """归档后端抽象基类。"""

    def __init__(self, project_root: Path, dedup_db: Path):
        self.project_root = project_root
        self.dedup_db = dedup_db

    def archive(self, pdf_path: Path, paper_info: dict) -> dict:
        """模板方法：归档 + register 原子操作。

        Args:
            pdf_path: PDF 文件的绝对路径
            paper_info: {
                "title": str,
                "filename": str,
                "direction": str,
                "rel_path": str,   // 相对于 01_raw 的路径
                "downloaded_from": str,  // 来源源
                "md5": str,        // 可选，不传则自动计算
            }

        Returns:
            {"status": "ok"|"error"|"skipped", "message": str, "dest": str}
        """
        try:
            result = self._do_archive(pdf_path, paper_info)
            if result.get("status") == "ok":
                self._call_dedup_register(pdf_path, paper_info)
            return result
        except Exception as e:
            return {"status": "error", "message": str(e), "dest": ""}

    @abstractmethod
    def _do_archive(self, pdf_path: Path, paper_info: dict) -> dict:
        """子类实现具体归档逻辑。

        Returns:
            {"status": "ok"|"error"|"skipped", "message": str, "dest": str}
        """
        ...

    def _call_dedup_register(self, pdf_path: Path, paper_info: dict):
        """调用 dedup register 写入索引。"""
        import hashlib
        md5 = paper_info.get("md5") or hashlib.md5(pdf_path.read_bytes()).hexdigest()
        title = paper_info.get("title", pdf_path.stem)
        filename = paper_info.get("filename", pdf_path.name)
        direction = paper_info.get("direction", "")
        rel_path = paper_info.get("rel_path", str(pdf_path.relative_to(self.project_root / "01_raw")) if (self.project_root / "01_raw") in pdf_path.parents else "")
        source = paper_info.get("downloaded_from", "manual")

        try:
            import sqlite3
            conn = sqlite3.connect(str(self.dedup_db))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO papers
                (md5, title, raw_title, filename, direction, rel_path, first_seen, file_mtime, downloaded_from)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (md5, title[:100], title[:200], filename[:200], direction, rel_path,
                  __import__('datetime').datetime.now().isoformat(),
                  __import__('datetime').datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat(),
                  source))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  [WARN] dedup register 失败: {e}", file=sys.stderr)

    @classmethod
    @abstractmethod
    def detect(cls, project_root: Path) -> bool:
        """检测当前环境是否支持该后端。"""
        ...


def get_available_backends(project_root: Path) -> list:
    """检测所有可用的后端。

    Returns:
        [(backend_key, display_name, backend_class), ...]
    """
    backends = []
    try:
        from .filesystem.archive import FilesystemBackend
        backends.append(("filesystem", "纯文件系统（默认，零依赖）", FilesystemBackend))
    except Exception:
        pass
    try:
        from .zotero.archive import ZoteroBackend
        if ZoteroBackend.detect(project_root):
            backends.append(("zotero", f"Zotero", ZoteroBackend))
    except Exception:
        pass
    return backends


def get_backend(backend_key: str, project_root: Path, dedup_db: Path) -> ArchiveBackend:
    """工厂函数：根据 key 获取后端实例。

    Args:
        backend_key: filesystem / zotero / feishu / notion
        project_root: 项目根路径
        dedup_db: dedup.db 路径

    Returns:
        ArchiveBackend 实例
    """
    if backend_key == "filesystem":
        from .filesystem.archive import FilesystemBackend
        return FilesystemBackend(project_root, dedup_db)
    elif backend_key == "zotero":
        from .zotero.archive import ZoteroBackend
        return ZoteroBackend(project_root, dedup_db)
    else:
        raise ValueError(f"不支持的归档后端: {backend_key}")
