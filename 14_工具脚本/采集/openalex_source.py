#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
"""OpenAlex 论文源 — 开放API，无需登录"""
import sys, os, re, urllib.request, urllib.parse, json, time
sys.stdout.reconfigure(encoding='utf-8')
from base import BaseSource, get_existing_titles, archive_pdf, make_standard_filename
from pathlib import Path

class OpenAlexSource(BaseSource):
    def name(self): return "openalex"

    def search(self, keyword: str, limit: int = 5) -> list:
        encoded = urllib.parse.quote(keyword)
        url = f"https://api.openalex.org/works?search={encoded}&per_page={limit}&select=id,doi,title,publication_year,authorships,primary_location,best_oa_location"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; research-kb)"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            results = []
            for work in data.get("results", []):
                title = work.get("title", "")
                doi = work.get("doi", "")
                year = work.get("publication_year") or ""
                # 第一作者
                author = ""
                authorships = work.get("authorships") or []
                if authorships:
                    first = authorships[0].get("author", {})
                    raw = first.get("display_name", "")
                    # 中文名去空格（OpenAlex 返回 "高 洋"）
                    if re.search(r'[一-鿿]', raw):
                        raw = raw.replace(' ', '')
                    # 英文名取姓
                    elif raw and ' ' in raw:
                        raw = raw.split()[-1].rstrip('.,; ')
                    author = raw

                oa_url = ""
                loc = work.get("primary_location") or {}
                if loc and loc.get("pdf_url"):
                    oa_url = loc["pdf_url"]
                if not oa_url:
                    oa_loc = work.get("best_oa_location") or {}
                    if oa_loc and oa_loc.get("pdf_url"):
                        oa_url = oa_loc["pdf_url"]

                results.append({
                    "title": title or "",
                    "url": oa_url or doi or "",
                    "source": "openalex",
                    "doi": doi or "",
                    "year": str(year) if year else "",
                    "author": author,
                    "has_pdf": bool(oa_url),
                })
            return results
        except Exception as e:
            print(f"  [OpenAlex ERROR] {e}")
            return []

    def download(self, paper: dict) -> bool:
        if not paper.get("url") or paper.get("has_pdf") is False:
            if paper.get("doi"):
                print(f"  有DOI({paper['doi']})但无OA PDF，可手动查找")
            return False
        try:
            req = urllib.request.Request(paper["url"], headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=30)
            # 统一生成标准文件名
            fname = make_standard_filename(paper)
            dest = os.path.expanduser(f"~/{fname}")
            with open(dest, "wb") as fh:
                fh.write(resp.read())
            time.sleep(1)
            return archive_pdf(Path(dest), area=paper.get("direction"))
        except Exception as e:
            print(f"  [下载失败] {paper['title'][:40]}: {e}")
            return False


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "digital government"
    src = OpenAlexSource()
    papers = src.search(kw, 3)
    for p in papers:
        has = '📄' if p['has_pdf'] else '📝'
        print(f"  {has} [{p.get('year','?')}] {p.get('author','?')} — {p['title'][:60]}")
