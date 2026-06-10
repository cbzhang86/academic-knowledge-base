#!/usr/bin/env python3
"""Zotero 归档后端 — 可选，需要 Zotero 桌面端。

特性：
- 将 PDF 复制到 Zotero storage
- 写入 Zotero SQLite（items/attachments/collections）
- 在 dedup.db 中标记 zotero_imported=1
- 依赖 Zotero 桌面端的 SQLite 数据库
"""

import sys, os, sqlite3, uuid, hashlib, shutil, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime
from .. import ArchiveBackend


class ZoteroBackend(ArchiveBackend):
    """Zotero 归档后端。"""

    def __init__(self, project_root: Path, dedup_db: Path):
        super().__init__(project_root, dedup_db)
        # 从全局配置获取 Zotero 路径
        try:
            from global_config import ZOTERO_DB
            self.zotero_db = ZOTERO_DB
        except (ImportError, AttributeError):
            # 从配置读取
            import yaml
            meta_path = project_root / "config" / "metadata.yaml"
            if meta_path.exists():
                cfg = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
                zotero_cfg = cfg.get("zotero", {})
                db_path = zotero_cfg.get("db_path", os.path.expanduser("~/Zotero/zotero.sqlite"))
            else:
                db_path = os.path.expanduser("~/Zotero/zotero.sqlite")
            self.zotero_db = Path(db_path)

        self.zotero_data = self.zotero_db.parent
        self.storage = self.zotero_data / "storage"

    def _do_archive(self, pdf_path: Path, paper_info: dict) -> dict:
        if not self.zotero_db.exists():
            return {"status": "skipped", "message": f"Zotero DB 不存在: {self.zotero_db}", "dest": ""}

        direction = paper_info.get("direction", "交叉研究")
        title = paper_info.get("title", pdf_path.stem)

        try:
            conn = sqlite3.connect(str(self.zotero_db))
            cursor = conn.cursor()

            # 1. 创建 Zotero item
            item_key = uuid.uuid4().hex[:8]
            date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO items (itemTypeID, dateAdded, dateModified, clientDateModified, key, synced)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (22, date_added, date_added, date_added, item_key))
            item_id = cursor.lastrowid

            # 2. 写入标题
            cursor.execute("SELECT valueID FROM itemDataValues WHERE value = ?", (title,))
            row = cursor.fetchone()
            if row:
                value_id = row[0]
            else:
                cursor.execute("INSERT INTO itemDataValues (value) VALUES (?)", (title,))
                value_id = cursor.lastrowid
            cursor.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, 1, ?)", (item_id, value_id))

            # 3. 创建附件
            storage_dir = self.storage / item_key
            storage_dir.mkdir(parents=True, exist_ok=True)
            dest_path = storage_dir / pdf_path.name
            shutil.copy2(str(pdf_path), str(dest_path))

            # 附件 item
            att_key = uuid.uuid4().hex[:8]
            content_type = "application/pdf"
            cursor.execute("""
                INSERT INTO items (itemTypeID, dateAdded, dateModified, clientDateModified, key, synced)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (14, date_added, date_added, date_added, att_key))
            att_id = cursor.lastrowid

            # 附件路径
            rel_path = f"storage:{item_key}/{pdf_path.name}"
            cursor.execute("""
                INSERT INTO itemAttachments (itemID, contentType, path, syncState)
                VALUES (?, ?, ?, 0)
            """, (att_id, content_type, rel_path))

            # 关联附件到父 item
            cursor.execute("INSERT INTO itemAttachmentsLink (sourceItemID, targetItemID) VALUES (?, ?)", (item_id, att_id))

            # 4. 添加到集合（按方向）
            # 查找或创建集合
            cursor.execute("SELECT collectionID FROM collections WHERE collectionName = ?", (direction,))
            row = cursor.fetchone()
            if row:
                collection_id = row[0]
            else:
                col_key = uuid.uuid4().hex[:8]
                cursor.execute("""
                    INSERT INTO collections (collectionName, key, dateAdded, dateModified, version)
                    VALUES (?, ?, ?, ?, 1)
                """, (direction, col_key, date_added, date_added))
                collection_id = cursor.lastrowid

            cursor.execute("INSERT INTO collectionItems (collectionID, itemID) VALUES (?, ?)", (collection_id, item_id))

            conn.commit()
            conn.close()

            # 5. 标记 dedup.db 中的 zotero_imported
            self._mark_zotero_imported(paper_info)

            return {
                "status": "ok",
                "message": f"已导入 Zotero [{direction}]: {title[:50]}",
                "dest": str(dest_path),
            }

        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                return {"status": "error", "message": f"Zotero DB 被占用（请关闭 Zotero 后重试）: {e}", "dest": ""}
            return {"status": "error", "message": f"Zotero DB 错误: {e}", "dest": ""}
        except Exception as e:
            return {"status": "error", "message": f"导入失败: {e}", "dest": ""}

    def _mark_zotero_imported(self, paper_info: dict):
        """在 dedup.db 中标记已导入 Zotero。"""
        md5 = paper_info.get("md5")
        if not md5:
            return
        try:
            conn = sqlite3.connect(str(self.dedup_db))
            cursor = conn.cursor()
            cursor.execute("UPDATE papers SET zotero_imported = 1 WHERE md5 = ?", (md5,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        """检测 Zotero SQLite 是否存在。"""
        try:
            from global_config import ZOTERO_DB
            return ZOTERO_DB.exists()
        except (ImportError, AttributeError):
            return Path(os.path.expanduser("~/Zotero/zotero.sqlite")).exists()
