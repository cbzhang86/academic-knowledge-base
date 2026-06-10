#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
"""arXiv 论文源 — 开放API，无需登录"""
import sys, os, re, urllib.request, json, time
sys.stdout.reconfigure(encoding='utf-8')
from base import BaseSource, get_existing_titles, archive_pdf, make_standard_filename
from pathlib import Path

class ArxivSource(BaseSource):
    def name(self): return "arxiv"

    def search(self, keyword: str, limit: int = 5) -> list:
        # 用 arXiv API 的 all 字段搜索，但加 category 过滤
        _keyword = keyword
        # 自动加社会科学相关分类过滤
        social_cats = ['cs.CY', 'cs.HC', 'cs.SI', 'econ.GN', 'q-bio.PE', 'q-fin.GN', 'stat.AP', 'stat.ME']
        cat_filter = '(' + '+OR+'.join(f'cat:{c}' for c in social_cats) + ')'
        # 先不加分类过滤（会漏掉未分类的新论文），通过关键词匹配过滤
        url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(keyword)}&max_results={limit}&sortBy=relevance"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            xml = resp.read().decode("utf-8")
            results = []
            for entry in re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL):
                title_m = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                id_m = re.search(r'<id>(.*?)</id>', entry)
                # 年份: 从 published 或 arXiv ID 提取
                pub_m = re.search(r'<published>(\d{4})', entry)
                if not pub_m:
                    pub_m = re.search(r'<updated>(\d{4})', entry)
                # 作者
                authors = re.findall(r'<author>.*?<name>(.*?)</name>.*?</author>', entry, re.DOTALL)
                first_author = authors[0].strip() if authors else ""
                # 英文名取姓
                if first_author and ' ' in first_author:
                    first_author = first_author.split()[-1].rstrip('.,;')

                if title_m and id_m:
                    title = title_m.group(1).strip().replace('\n', ' ')
                    arxiv_id = id_m.group(1).strip().split('/')[-1].split('v')[0]
                    # 年份
                    year = pub_m.group(1) if pub_m else ""
                    if not year and len(arxiv_id) >= 2:
                        pre = arxiv_id[:2]
                        year = f"20{pre}" if int(pre) <= 30 else f"19{pre}"

                    results.append({
                        "title": title,
                        "url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        "source": "arxiv",
                        "year": year,
                        "author": first_author,
                        "arxiv_id": arxiv_id,
                    })
            return results
        except Exception as e:
            print(f"  [arXiv ERROR] {e}")
            return []

    def download(self, paper: dict) -> bool:
        try:
            req = urllib.request.Request(paper["url"], headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=30)
            # 统一用 make_standard_filename 生成标准文件名
            fname = make_standard_filename(paper)
            dest = os.path.expanduser(f"~/{fname}")
            with open(dest, "wb") as fh:
                fh.write(resp.read())
            time.sleep(1)
            return archive_pdf(Path(dest), area=paper.get("direction"))
        except Exception as e:
            print(f"  [下载失败] {paper['title'][:40]}: {e}")
            return False


def search_and_download(keyword: str, limit: int = 3, area: str = None):
    """一键搜索+去重+下载"""
    existing = get_existing_titles()
    src = ArxivSource()
    papers = src.search(keyword, limit)
    if not papers:
        print("  无结果")
        return

    new_papers = []
    for p in papers:
        t_clean = re.sub(r"\s+", "", p["title"].strip().lower())[:60]
        is_dup = any(t_clean in e for e in existing)
        if not is_dup:
            new_papers.append(p)
            print(f"  [新] {p['title'][:60]}")
        else:
            print(f"  [跳过] {p['title'][:40]}")

    if not new_papers:
        print("[DONE] 无新论文")
        return

    for p in new_papers[:limit]:
        print(f"  下载中: {p['title'][:40]}")
        src.download(p)


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "machine learning"
    search_and_download(kw)
