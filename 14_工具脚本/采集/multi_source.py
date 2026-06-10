#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
"""统一采集调度 — 自动判断用哪个源，全流程自动化"""

import sys, os, re, time, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from base import KEYWORD_POOL, get_existing_titles, archive_pdf, AREA_CONFIG

SOURCES = []

def load_sources():
    """动态加载所有 *_source.py 模块"""
    src_dir = Path(__file__).parent
    for f in sorted(src_dir.glob("*_source.py")):
        name = f.stem
        if name in ("base", "multi_source"):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(name, str(f))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for attr in dir(mod):
                cls = getattr(mod, attr)
                if isinstance(cls, type) and hasattr(cls, 'name') and hasattr(cls, 'search') and hasattr(cls, 'download'):
                    if cls.__name__ not in ('BaseSource',):
                        instance = cls()
                        SOURCES.append(instance)
                        print(f"  [加载源] {instance.name()}")
        except Exception as e:
            print(f"  [加载失败] {name}: {e}")

def should_use_source(keyword):
    """判断关键词应该用哪些源
    规则：有中文 → 所有源都试（开放源也支持中文搜索）
          纯英文 → arXiv/OpenAlex
    """
    has_chinese = bool(re.search(r'[一-鿿]', keyword))

    if has_chinese:
        return ["ncpssd", "arxiv", "openalex"]  # 中文关键词也用开放源
    else:
        return ["arxiv", "openalex", "semantic_scholar"]  # 纯英文 → 开放源

def search_all(keyword, limit=5, direction=None):
    """在所有合适的源中搜索，返回合并+去重后的结果"""
    if not SOURCES:
        load_sources()

    sources_to_use = should_use_source(keyword)
    existing = get_existing_titles()
    all_results = []
    seen_titles = set()

    # 研究方向相关关键词——用于过滤不相关论文
    RELEVANT_KWS = [
        "公共", "治理", "政府", "政策", "养老", "老龄",
        "社会", "阶层", "流动", "分层", "公平", "分配",
        "数字", "技术", "排斥", "鸿沟", "融入", "包容",
        "社区", "参与", "服务", "保障", "福祉", "行政",
        "public", "govern", "digital", "elder",
        "social", "policy", "welfare", "inclusion", "exclusion",
        "democra", "service", "innov", "adopt", "technolog",
        "equit", "justice", "divide", "civic",
    ]

    for src in SOURCES:
        if src.name() not in sources_to_use:
            continue
        print(f"\n[{src.name()}] 搜索: {keyword}")
        try:
            papers = src.search(keyword, limit)
        except Exception as e:
            print(f"  ⚠️ 搜索失败: {e}")
            continue
        for p in papers:
            title = p.get("title", "").strip()
            if not title:
                continue

            # 相关性粗筛——只保留标题中含相关关键词的论文
            title_lower = title.lower()
            has_relevant = any(kw in title_lower for kw in RELEVANT_KWS)
            # 中文论文默认全部保留（中文搜索命中率本身已过滤）
            has_chinese = bool(re.search(r'[一-鿿]', title))
            if not has_chinese and not has_relevant:
                print(f"  [跳过 不相关] {title[:60]}")
                continue

            # 去重
            t_clean = re.sub(r"\s+", "", title.lower())[:60]
            if t_clean in seen_titles:
                continue
            seen_titles.add(t_clean)
            # 检查是否已有
            is_dup = any(t_clean in e for e in existing)
            p["duplicate"] = is_dup
            # 传入方向信息，供下载时归档到正确目录
            p["direction"] = direction
            all_results.append(p)
            status = "已有" if is_dup else "新"
            print(f"  [{status}] [{p['source']}] {p['title'][:60]}")
        time.sleep(1)

    return all_results

def download_all(papers, max_download=3):
    """从搜索结果中下载新论文"""
    downloaded = 0
    for p in papers:
        if downloaded >= max_download:
            break
        if p.get("duplicate"):
            continue
        for src in SOURCES:
            if src.name() == p["source"]:
                print(f"\n  下载: {p['title'][:40]}")
                try:
                    if src.download(p):
                        downloaded += 1
                except Exception as e:
                    print(f"  ⚠️ 下载失败: {e}")
                time.sleep(1)
                break
    return downloaded

def cmd_search(keyword, limit=5):
    """搜索（不下载）"""
    results = search_all(keyword, limit)
    print(f"\n总计: {len(results)} 条结果")
    new_count = sum(1 for r in results if not r.get("duplicate"))
    print(f"新论文: {new_count} 篇")

def cmd_search_dl(keyword, limit=3, direction=None):
    """搜索并下载新论文"""
    results = search_all(keyword, limit, direction=direction)
    new_papers = [r for r in results if not r.get("duplicate")]
    if not new_papers:
        print("\n无新论文需要下载")
        return
    n = download_all(new_papers, max_download=limit)
    print(f"\n下载完成: {n} 篇")

def cmd_pool(area, limit=3):
    """按方向从关键词池批量搜索下载（自动判断源）"""
    kws = KEYWORD_POOL.get(area, [])
    if not kws:
        print(f"[ERROR] 未知方向: {area}")
        return
    total_dl = 0
    for kw in kws:
        print(f"\n{'='*50}")
        print(f"关键词: {kw}")
        print(f"{'='*50}")
        cmd_search_dl(kw, limit, direction=area)
        total_dl += 1
    print(f"\n方向 [{area}] 批量下载完成")

def cmd_status():
    """查看所有源状态"""
    if not SOURCES:
        load_sources()
    print(f"已加载源: {len(SOURCES)}")
    for src in SOURCES:
        print(f"  ✅ {src.name()}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="智能多源采集")
    sub = parser.add_subparsers(dest="cmd")

    p_s = sub.add_parser("search", help="搜索（智能判断源）")
    p_s.add_argument("keyword")
    p_s.add_argument("--limit", type=int, default=5)
    p_s.add_argument("--direction", help="研究方向（如 老龄化研究）")

    p_sd = sub.add_parser("search-dl", help="搜索并下载")
    p_sd.add_argument("keyword")
    p_sd.add_argument("--limit", type=int, default=3)
    p_sd.add_argument("--direction", help="研究方向（如 老龄化研究）")

    p_pool = sub.add_parser("pool", help="从关键词池批量搜索下载")
    p_pool.add_argument("area", choices=list(KEYWORD_POOL.keys()))
    p_pool.add_argument("--limit", type=int, default=3)

    p_stat = sub.add_parser("status", help="查看源状态")

    args = parser.parse_args()
    if args.cmd == "search":
        cmd_search(args.keyword, args.limit)
    elif args.cmd == "search-dl":
        cmd_search_dl(args.keyword, args.limit, direction=args.direction)
    elif args.cmd == "pool":
        cmd_pool(args.area, args.limit)
    elif args.cmd == "status":
        cmd_status()
    else:
        parser.print_help()
