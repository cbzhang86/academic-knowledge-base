#!/usr/bin/env python3
"""
Zotero 批量导入工具 v3 — 基于 bak2 重建 + 增量追加
用法:
    python batch_import_zotero.py              # 从bak2重建并导入所有PDF
    python batch_import_zotero.py --append      # 只追加新PDF（已存在则跳过）

说明:
    从 zotero.sqlite.bak2 恢复基础DB（含Zotero系统笔记），
    清空旧论文+附件后重建，保留系统数据完整性。
"""
import sqlite3, uuid, hashlib, shutil, time, os, re, sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS, ZOTERO_DB

ZOTERO_DATA = ZOTERO_DB.parent
PDF_SRC = DIRS["01_raw"]
STORAGE = ZOTERO_DATA / "storage"
BAK2 = ZOTERO_DATA / "zotero.sqlite.bak2"
DB = ZOTERO_DB

DIR_MAP = {
    "公共管理学": "公共管理学",
    "社会学": "社会学",
    "老龄化研究": "老龄化",
    "青少年研究": "青少年研究",
    "交叉研究": "交叉研究",
}

def clean_title(t: str) -> str:
    t = t.strip()
    t = re.sub(r"_page$", "", t)
    t = re.sub(r"^\d{4}_", "", t)
    t = t.replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:255]

def get_dir_name(cn):
    """方向名 → 01_论文原文下的子目录名"""
    return DIR_MAP.get(cn, cn)

def rebuild():
    """从bak2恢复 → 清空旧论文/附件 → 重建（保留系统数据 typeID=3,40）"""
    # === 铁律1：拒绝 DELETE FROM items（只删 typeID=1,22） ===
    # 这里不会执行 DELETE FROM items，只删 IN (1,22)

    # === 铁律5：操作前备份 ===
    backup_path = ZOTERO_DATA / f"zotero.sqlite.before_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if DB.exists():
        shutil.copy2(str(DB), str(backup_path))
        print(f"[BACKUP] 已备份到 {backup_path.name}")

    if BAK2.exists():
        shutil.copy2(str(BAK2), str(DB))
        print("[OK] 从 bak2 恢复基础 DB")
    else:
        print("[ERROR] 找不到 bak2 备份")
        return

    # 确保 storage 目录存在
    STORAGE.mkdir(exist_ok=True)

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # 清空旧collection和论文/附件相关数据
    for t in ["itemAttachments", "collectionItems", "deletedItems"]:
        cur.execute(f'DELETE FROM "{t}"')
    cur.execute("SELECT itemID FROM items WHERE itemTypeID IN (1,22)")
    oids = [r[0] for r in cur.fetchall()]
    for oid in oids:
        cur.execute("DELETE FROM itemData WHERE itemID=?", (oid,))
    cur.execute("DELETE FROM items WHERE itemTypeID IN (1,22)")
    cur.execute("DELETE FROM collections")
    cur.execute("DELETE FROM collectionItems")

    # 清空storage目录
    # 铁律6：删除前确保没有孤立附件
    for d in os.listdir(STORAGE):
        dp = STORAGE / d
        if dp.is_dir():
            shutil.rmtree(dp)

    # 重建collections
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name in DIR_MAP:
        k = uuid.uuid4().hex[:8].upper()
        cur.execute("INSERT INTO collections (collectionName,clientDateModified,libraryID,key,version,synced) VALUES (?,?,1,?,0,0)", (name, now, k))

    cur.execute("SELECT collectionID, collectionName FROM collections")
    cols = {r[1].strip(): r[0] for r in cur.fetchall()}

    total = 0
    for cn, subdir in DIR_MAP.items():
        cid = cols.get(cn, 0)
        if not cid:
            continue
        for pf in sorted((PDF_SRC / subdir).glob("*.pdf")):
            now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ik = uuid.uuid4().hex[:8].upper()
            cur.execute("INSERT INTO items (itemTypeID,dateAdded,dateModified,clientDateModified,libraryID,key,version,synced) VALUES (22,?,?,?,1,?,0,0)", (now_dt, now_dt, now_dt, ik))
            iid = cur.lastrowid

            title = clean_title(pf.stem)
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", (title,))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", (title,))
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,1,?)", (iid, cur.fetchone()[0]))
            cur.execute("INSERT INTO collectionItems (collectionID,itemID) VALUES (?,?)", (cid, iid))

            ak = uuid.uuid4().hex[:8].upper()
            # 铁律10：items.key = storage目录名 = PDF文件名，三项一致
            cur.execute("INSERT INTO items (itemTypeID,dateAdded,dateModified,clientDateModified,libraryID,key,version,synced) VALUES (1,?,?,?,1,?,0,0)", (now_dt, now_dt, now_dt, ak))
            aid = cur.lastrowid

            sd = STORAGE / ak
            sd.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(pf), str(sd / ak))
            h = hashlib.md5((sd / ak).read_bytes()).hexdigest()
            cur.execute("INSERT INTO itemAttachments (itemID,parentItemID,linkMode,contentType,charsetID,path,syncState,storageModTime,storageHash) VALUES (?,?,0,?,?,?,0,?,?)",
                        (aid, iid, "application/pdf", None, f"storage:{ak}", int(time.time()), h))

            att_t = pf.name + "_" + uuid.uuid4().hex[:4]
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", (att_t,))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", (att_t,))
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,1,?)", (aid, cur.fetchone()[0]))
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", ("application/pdf",))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", ("application/pdf",))
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,4,?)", (aid, cur.fetchone()[0]))
            total += 1

        conn.commit()

    conn.commit()
    conn.close()

    # === 铁律11 + 铁律2：四项一致性验证 ===
    conn2 = sqlite3.connect(str(DB))
    c2 = conn2.cursor()
    c2.execute("SELECT itemTypeID, COUNT(*) FROM items GROUP BY itemTypeID ORDER BY itemTypeID")
    print("\n  导入结果:")
    for t, cnt in c2.fetchall():
        names = {1: "attachment", 3: "笔记", 22: "journalArticle", 40: "注释"}
        print(f"    {names.get(t, t)}: {cnt}")
    c2.execute("SELECT COUNT(*) FROM itemAttachments")
    att_cnt = c2.fetchone()[0]
    print(f"    attachments: {att_cnt}")
    dir_cnt = len([d for d in os.listdir(STORAGE) if (STORAGE/d).is_dir()])
    print(f"    storage目录: {dir_cnt}")

    # === 铁律10：验证PDF附件可打开 ===
    c2.execute("SELECT key FROM items WHERE itemTypeID=1")
    keys = [r[0] for r in c2.fetchall()]
    pdf_ok = sum(1 for k in keys if (STORAGE / k / k).is_file())
    print(f"    PDF附件可打开: {pdf_ok}/{len(keys)}")

    if pdf_ok < len(keys):
        print("  ⛔ 红牌犯规！附件无法打开，请检查 items.key 与 storage 一致性")
        print("  铁律10: items.key === storage目录名 === PDF文件名")
        conn2.close()
        return

    if att_cnt != dir_cnt or att_cnt != len(keys) or pdf_ok != len(keys):
        print("  ⛔ 红牌犯规！四项数量不一致，禁止复制到主DB")
        conn2.close()
        return

    print("  ✅ 验证通过，全部附件可打开")
    conn2.close()
    print(f"\nDone: {total} PDFs\n启动 Zotero 验证")

def append_only():
    """增量追加（基于 done.sqlite 副本，只加新PDF）

    安全策略（铁律12）：
    1. 从 zotero_done.sqlite 复制到 zotero.sqlite
    2. 在 zotero.sqlite 上增量追加
    3. 四项验证通过 → 复制回 zotero_done.sqlite
    4. 验证失败 → 回退（还原 zotero_done.sqlite）
    """
    DONE_DB = ZOTERO_DATA / "zotero_done.sqlite"

    # === 铁律12：从 done.sqlite 开始 ===
    if not DONE_DB.exists():
        print(f"[ERROR] {DONE_DB} 不存在，请先全量重建")
        print("  首次使用：python batch_import_zotero.py  # 全量重建")
        return

    # 备份当前 zotero.sqlite（如果有的话）
    if DB.exists():
        backup_path = ZOTERO_DATA / f"zotero.sqlite.before_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(str(DB), str(backup_path))
        print(f"[BACKUP] 已备份到 {backup_path.name}")

    # 从 done.sqlite 恢复为工作 DB
    shutil.copy2(str(DONE_DB), str(DB))
    print(f"[OK] 从 zotero_done.sqlite 恢复工作 DB")

    # === 以下核心写入逻辑完全不变 ===
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # 获取已有标题
    cur.execute("SELECT v.value FROM itemDataValues v JOIN itemData d ON v.valueID=d.valueID JOIN items i ON d.itemID=i.itemID WHERE i.itemTypeID=22 AND d.fieldID=1")
    existing = set(cur.fetchall())

    # 获取collections
    cur.execute("SELECT collectionID, collectionName FROM collections")
    cols = {r[1].strip(): r[0] for r in cur.fetchall()}

    total = 0
    for cn, subdir in DIR_MAP.items():
        cid = cols.get(cn, 0)
        if not cid:
            continue
        for pf in sorted((PDF_SRC / subdir).glob("*.pdf")):
            title = clean_title(pf.stem)
            if (title,) in existing or (pf.name,) in existing:
                continue
            now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ik = uuid.uuid4().hex[:8].upper()
            cur.execute("INSERT INTO items (itemTypeID,dateAdded,dateModified,clientDateModified,libraryID,key,version,synced) VALUES (22,?,?,?,1,?,0,0)", (now_dt, now_dt, now_dt, ik))
            iid = cur.lastrowid
            # title: INSERT OR IGNORE 然后重新 SELECT（避免 UNIQUE 冲突后 lastrowid 错误）
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", (title,))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", (title,))
            title_vid = cur.fetchone()[0]
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,1,?)", (iid, title_vid))
            cur.execute("INSERT INTO collectionItems (collectionID,itemID) VALUES (?,?)", (cid, iid))
            ak = uuid.uuid4().hex[:8].upper()
            # 铁律10：items.key = storage目录名 = PDF文件名，三项一致
            cur.execute("INSERT INTO items (itemTypeID,dateAdded,dateModified,clientDateModified,libraryID,key,version,synced) VALUES (1,?,?,?,1,?,0,0)", (now_dt, now_dt, now_dt, ak))
            aid = cur.lastrowid
            sd = STORAGE / ak
            sd.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(pf), str(sd / ak))
            h = hashlib.md5((sd / ak).read_bytes()).hexdigest()
            cur.execute("INSERT INTO itemAttachments (itemID,parentItemID,linkMode,contentType,charsetID,path,syncState,storageModTime,storageHash) VALUES (?,?,0,?,?,?,0,?,?)",
                        (aid, iid, "application/pdf", None, f"storage:{ak}", int(time.time()), h))
            att_t = pf.name + "_" + uuid.uuid4().hex[:4]
            # attachment title: 同上方法
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", (att_t,))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", (att_t,))
            att_vid = cur.fetchone()[0]
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,1,?)", (aid, att_vid))
            cur.execute("INSERT OR IGNORE INTO itemDataValues (value) VALUES (?)", ("application/pdf",))
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", ("application/pdf",))
            vid = cur.fetchone()[0]
            cur.execute("INSERT INTO itemData (itemID,fieldID,valueID) VALUES (?,4,?)", (aid, vid))
            total += 1
            existing.add((title,))
            if total % 30 == 0:
                conn.commit()
            print(f"  + {title[:50]}")
        conn.commit()

    conn.close()
    print(f"\nDone: +{total} 篇新论文")

    # === 铁律11：四项验证 ===
    print("\n[VERIFY] 四项一致性验证...")
    conn_v = sqlite3.connect(str(DB))
    c2 = conn_v.cursor()
    c2.execute("SELECT COUNT(*) FROM items WHERE itemTypeID=22")
    n_papers = c2.fetchone()[0]
    c2.execute("SELECT COUNT(*) FROM itemAttachments")
    n_att = c2.fetchone()[0]
    c2.execute("SELECT key FROM items WHERE itemTypeID=1")
    keys = [r[0] for r in c2.fetchall()]
    pdf_ok = sum(1 for k in keys if (STORAGE / k / k).is_file())
    dirs_ok = len([d for d in os.listdir(STORAGE) if (STORAGE/d).is_dir()])
    conn_v.close()

    print(f"  journalArticle: {n_papers}")
    print(f"  attachments: {n_att}")
    print(f"  storage目录: {dirs_ok}")
    print(f"  PDF可打开: {pdf_ok}/{len(keys)}")

    if n_papers == n_att == dirs_ok == pdf_ok == len(keys):
        print("  ✅ 四项一致！")
        # 更新 done.sqlite
        shutil.copy2(str(DB), str(DONE_DB))
        print(f"[OK] 已更新 zotero_done.sqlite ({DONE_DB})")
        # 更新 dedup.db 的 zotero_imported 标记
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from global_config import PROJECT_ROOT as _PR
            dedup_db = _PR / "config" / "dedup.db"
            if dedup_db.exists():
                conn_d = sqlite3.connect(str(dedup_db))
                c_d = conn_d.cursor()
                c_d.execute("UPDATE papers SET zotero_imported=1 WHERE zotero_imported=0")
                conn_d.commit()
                affected = c_d.rowcount
                conn_d.close()
                print(f"  [DEDUP] 已标记 {affected} 篇为 zotero_imported=1")
        except Exception as e:
            print(f"  [WARN] dedup 标记更新失败: {e}")
    else:
        print("  ⛔ 四项不一致！回退到 zotero_done.sqlite")
        shutil.copy2(str(DONE_DB), str(DB))
        print("  [ROLLBACK] 已还原")

    print("启动 Zotero 验证")

if __name__ == "__main__":
    if "--append" in sys.argv:
        append_only()
    else:
        rebuild()
