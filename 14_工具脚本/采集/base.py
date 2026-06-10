#!/usr/bin/env python3
"""采集源抽象基类 — 所有论文源统一接口"""
import sys, os, re, shutil, time, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

try:
    from _config import PROJECT_ROOT, DIRS, ZOTERO_DB
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS, ZOTERO_DB

# === 共享配置 ===
EDGE_CDP = "http://127.0.0.1:9222"
DOWNLOAD_DIR = Path(os.path.expanduser("~/Downloads"))
PDF_TARGET = DIRS["01_raw"]

AREA_CONFIG = {
    "公共管理学": {"subdir": "公共管理学", "kws": ["公共", "治理", "政府", "政策", "行政", "绩效"]},
    "社会学": {"subdir": "社会学", "kws": ["社会", "阶层", "流动", "分层", "教育", "收入", "劳动"]},
    "老龄化研究": {"subdir": "老龄化", "kws": ["老龄", "养老", "老年", "银发", "延迟退休"]},
    "青少年研究": {"subdir": "青少年研究", "kws": ["青少年", "青年", "未成年人", "学生", "网络行为"]},
}

KEYWORD_POOL = {
    "公共管理学": ["数字政府", "基层治理", "公共服务", "政策执行", "公共价值"],
    "社会学": ["社会分层", "社会流动", "教育公平", "社会资本", "分配公平"],
    "老龄化研究": ["养老服务", "养老保险", "健康老龄化", "智慧养老", "人口老龄化"],
    "青少年研究": ["青少年 网络行为", "青少年 心理健康", "青少年 社交媒体", "教育公平", "网络成瘾"],
}

def get_existing_titles() -> set:
    """双壳去重 — 从 Zotero DB 和 01_论文原文 获取已有标题"""
    titles = set()
    helper = re.compile(r"\s+")
    if ZOTERO_DB and ZOTERO_DB.exists():
        try:
            conn = sqlite3.connect(str(ZOTERO_DB))
            cur = conn.cursor()
            cur.execute("SELECT v.value FROM itemDataValues v JOIN itemData d ON v.valueID=d.valueID JOIN items i ON d.itemID=i.itemID WHERE i.itemTypeID=22 AND d.fieldID=1")
            for r in cur.fetchall():
                titles.add(helper.sub("", r[0].strip().lower()))
            conn.close()
        except:
            pass
    for area in AREA_CONFIG:
        p = PDF_TARGET / AREA_CONFIG[area]["subdir"]
        if p.exists():
            for f in p.glob("*.pdf"):
                titles.add(helper.sub("", f.stem.strip().lower()))
    print(f"[DEDUP] Zotero + 论文原文 共 {len(titles)} 篇已知论文")
    return titles


def sanitize_filename(title: str, max_len: int = 100) -> str:
    """将论文标题转为安全的文件名：去非法字符、按词截断、去尾随标点"""
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)
    safe = re.sub(r'\s+', '_', safe)
    safe = safe.strip('_. ')
    if len(safe) > max_len:
        # 按词截断，不砍半字
        safe = safe[:max_len]
        last_underscore = safe.rfind('_')
        if last_underscore > max_len - 20:  # 尽量保留完整词语
            safe = safe[:last_underscore]
        safe = safe.rstrip('_-. ')
    return safe or "untitled"


def detect_area(filename: str, keywords: list = None) -> str:
    """根据文件名和搜索关键词判断研究方向"""
    name = filename.lower()
    # 优先用搜索关键词匹配（比文件名更可靠）
    if keywords:
        kw_text = " ".join(k.lower() for k in keywords)
        for area, cfg in AREA_CONFIG.items():
            for kw in cfg["kws"]:
                if kw in kw_text:
                    return area
    # 回退到文件名关键词匹配
    for area, cfg in AREA_CONFIG.items():
        for kw in cfg["kws"]:
            if kw in name:
                return area
    return "交叉研究"


def make_standard_filename(paper: dict, max_title_len: int = 80) -> str:
    """统一生成标准文件名：年份_作者_原标题.pdf

    所有采集源统一使用此函数，不再各自拼接。

    Args:
        paper: 论文信息字典，需包含:
            - title (str): 论文标题
            - year (str, optional): 出版年份
            - author (str, optional): 第一作者姓氏/中文名
        max_title_len: 标题段最大长度
    Returns:
        标准文件名，如 '2026_吴玉韶_十五五时期我国养老服务体系治理逻辑的结构性转向.pdf'
    """
    title = paper.get("title", "").strip()
    if not title:
        return "untitled.pdf"

    # 安全化标题
    safe = re.sub(r'[\\/:*?"<>|]', '_', title)
    safe = re.sub(r'\s+', '_', safe).strip('_. ')
    # 按词截断
    if len(safe) > max_title_len:
        safe = safe[:max_title_len]
        last_u = safe.rfind('_')
        if last_u > max_title_len - 15:
            safe = safe[:last_u]
        safe = safe.rstrip('_-. ')

    parts = []
    year = paper.get("year") or ""
    author = paper.get("author") or ""
    if year:
        parts.append(str(year))
    if author:
        # 作者名清洗：去掉脚注标记 [1]、邮箱等
        a = re.sub(r'\[[\d,\s]+\]', '', author).strip()
        if len(a) > 25:
            a = a.split(',')[0].split(' and ')[0].strip()  # 多作者时只取第一作者
            parts = [str(year)]
            parts.append(a)
        elif a:
            parts.append(a)
    if safe:
        parts.append(safe)

    return '_'.join(parts) + '.pdf'


def archive_pdf(src_path: Path, area: str = None) -> bool:
    """将 PDF 归档到 01_论文原文/{方向}/，清理临时文件

    Args:
        src_path: PDF 临时文件路径
        area: 研究方向（可选，自动检测）
    Returns:
        bool: 是否归档成功
    """
    fname = src_path.name
    # 清理双后缀（.pdf.pdf → .pdf）
    fname = re.sub(r'\.pdf\.pdf$', '.pdf', fname, flags=re.IGNORECASE)
    area_name = area or detect_area(fname)
    subdir = AREA_CONFIG.get(area_name, {}).get("subdir", area_name)
    target = PDF_TARGET / subdir
    target.mkdir(parents=True, exist_ok=True)
    dest = target / fname
    # 如果已存在同名文件，加序号
    if dest.exists():
        stem = dest.stem
        counter = 1
        while dest.exists():
            dest = target / f"{stem}_{counter}.pdf"
            counter += 1
    shutil.copy2(str(src_path), str(dest))
    # 清理临时文件
    if src_path.exists():
        os.remove(str(src_path))
    rel = f"01_论文原文/{subdir}/{dest.name}"
    print(f"  ✅ 归档: {rel} ({os.path.getsize(dest)/1024:.0f}KB)")
    return True


class BaseSource(ABC):
    """采集源基类 — 每个源实现 search() 和 download()"""

    @abstractmethod
    def name(self) -> str:
        """源名称，如 'ncpssd'、'pubmed'、'arxiv'"""
        pass

    @abstractmethod
    def search(self, keyword: str, limit: int = 5) -> list:
        """搜索论文，返回 [{title, url, source}]"""
        pass

    @abstractmethod
    def download(self, paper: dict) -> bool:
        """下载单篇论文PDF，返回成功/失败"""
        pass
