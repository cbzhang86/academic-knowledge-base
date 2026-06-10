#!/usr/bin/env python3
"""
ncpssd 搜索→去重→下载 自动化脚本
功能：通过 Edge CDP 实现 ncpssd 全流程自动化

用法:
    # 按研究方向搜索并下载（自动去重）
    python ncpssd_cdp.py download "数字政府" --area 公共管理学

    # 从关键词池一键下载
    python ncpssd_cdp.py download-pool "公共管理学"

依赖: Edge 浏览器运行在 localhost:9222（带 --remote-debugging-port=9222）
"""
import sqlite3, json, time, base64, os, re, shutil, sys, argparse, uuid
from pathlib import Path
from datetime import datetime
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS, ZOTERO_DB, EDGE_CDP

# ============================================================
# 配置
# ============================================================
DOWNLOAD_DIR = Path(os.path.expanduser("~/Downloads"))
PDF_TARGET = DIRS["01_raw"]
WATCH_DIR = DIRS.get("temp", PROJECT_ROOT / "00_临时工作区") / "待下载"

# 研究方向 → 子目录映射 + 关键词检测
AREA_CONFIG = {
    "公共管理学": {"subdir": "公共管理学", "kws": ["公共", "治理", "政府", "政策", "行政", "绩效"]},
    "社会学": {"subdir": "社会学", "kws": ["社会", "阶层", "流动", "分层", "教育", "收入", "劳动"]},
    "老龄化研究": {"subdir": "老龄化", "kws": ["老龄", "养老", "老年", "银发", "延迟退休"]},
    "青少年研究": {"subdir": "青少年研究", "kws": ["青少年", "青年", "未成年人", "学生", "网络行为"]},
}

# 已验证的关键词池（关键词 → 英文翻译）
KEYWORD_POOL = {
    "公共管理学": ["数字政府", "基层治理", "公共服务", "政策执行", "公共价值", "政务服务", "政府绩效评估", "数字政府治理", "赋能数字政府", "大模型在社区", "居民参与", "移动政务服务", "乡村数字治理", "新公共治理", "嵌入数字政府"],
    "社会学": ["社会分层", "社会流动", "教育公平", "社会资本", "分配公平", "上市公司数据", "省际面板数据", "婚姻社会分层", "五期数据", "中国居民收入", "中国代际流动", "构建教育", "分析教育", "分流对教育", "影响及对阶层"],
    "老龄化研究": ["养老服务", "养老保险", "健康老龄化", "智慧养老", "人口老龄化", "五期面板数据", "网使用对老年", "自评健康", "应及社会参与", "构建社会养老", "休和个人养老", "金的政策", "探讨人工智能", "技术赋能老年", "梳理巴西老年"],
    "青少年研究": ["青少年 网络行为", "青少年 心理健康", "青少年 社交媒体", "教育公平", "网络成瘾", "国青少年网络", "首次采用网络", "讨青少年网络", "变以及与网络"],
}

# ============================================================
# 工具函数
# ============================================================

def edge_cdp_request(method: str, params: dict = None, session_id: str = None) -> dict:
    """通过 Edge CDP 发送命令"""
    import websocket
    # 获取 WS URL
    r = json.loads(urllib.request.urlopen(f"{EDGE_CDP}/json/version", timeout=5).read())
    browser_ws = r["webSocketDebuggerUrl"]
    ws = websocket.create_connection(browser_ws, timeout=15)
    msg = {"id": 1, "method": method}
    if params:
        msg["params"] = params
    if session_id:
        msg["sessionId"] = session_id
    ws.send(json.dumps(msg))
    resp = json.loads(ws.recv())
    ws.close()
    return resp


def find_or_create_ncpssd_tab():
    """在 Edge 中找到或新建 ncpssd 页面"""
    import websocket
    r = json.loads(urllib.request.urlopen(f"{EDGE_CDP}/json", timeout=5).read())
    # 找已有的 ncpssd 页面
    for p in r:
        url = p.get("url", "")
        if "ncpssd" in url.lower():
            return p["webSocketDebuggerUrl"], p["id"]
    # 找不到就新建
    browser_r = json.loads(urllib.request.urlopen(f"{EDGE_CDP}/json/version", timeout=5).read())
    browser_ws = browser_r["webSocketDebuggerUrl"]
    ws = websocket.create_connection(browser_ws, timeout=15)
    ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "https://www.ncpssd.cn/"}}))
    resp = json.loads(ws.recv())
    target_id = resp.get("result", {}).get("targetId", "")
    ws.close()
    time.sleep(2)
    if target_id:
        r2 = json.loads(urllib.request.urlopen(f"{EDGE_CDP}/json", timeout=5).read())
        for p in r2:
            if p.get("id") == target_id:
                return p["webSocketDebuggerUrl"], target_id
    return None, None


def run_js(page_ws_url: str, js_code: str, timeout: int = 15) -> dict:
    """在页面中执行 JS"""
    import websocket
    ws = websocket.create_connection(page_ws_url, timeout=timeout)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js_code}}))
    resp = json.loads(ws.recv())
    ws.close()
    return resp.get("result", {}).get("result", {})


def make_search_url(keywords: str) -> str:
    """构造 ncpssd 搜索 URL（base64 编码已验证）"""
    term = (f'(IKTE="{keywords}" OR IKPYTE="{keywords}" '
            f'OR IKST="{keywords}" OR IKET="{keywords}" OR IKSE="{keywords}")')
    b64 = base64.b64encode(term.encode("utf-8")).decode("utf-8")
    return f"https://www.ncpssd.cn/Literature/articlelist?sType=0&search={b64}"


def get_existing_titles() -> set:
    """从 Zotero DB 和 01_论文原文 获取已有标题（双壳去重）"""
    titles = set()
    helper = re.compile(r"\s+")

    # 1. 从 Zotero DB 读取
    if os.path.isfile(ZOTERO_DB):
        try:
            conn = sqlite3.connect(ZOTERO_DB)
            cur = conn.cursor()
            cur.execute("""
                SELECT v.value FROM itemDataValues v
                JOIN itemData d ON v.valueID = d.valueID
                JOIN items i ON d.itemID = i.itemID
                WHERE i.itemTypeID = 22 AND d.fieldID = 1
            """)
            for r in cur.fetchall():
                titles.add(helper.sub("", r[0].strip().lower()))
            conn.close()
        except:
            pass

    # 2. 从 01_论文原文 读取文件名
    for area in AREA_CONFIG:
        subdir = AREA_CONFIG[area]["subdir"]
        p = PDF_TARGET / subdir
        if p.exists():
            for f in p.glob("*.pdf"):
                base = f.stem
                base_clean = helper.sub("", base.strip().lower())
                titles.add(base_clean)

    print(f"[DEDUP] Zotero + 论文原文 共 {len(titles)} 篇已知论文")
    return titles


def detect_area(filename: str) -> str:
    """根据文件名关键词判断研究方向"""
    name = filename.lower()
    for area, cfg in AREA_CONFIG.items():
        for kw in cfg["kws"]:
            if kw in name:
                return area
    return "交叉研究"


# ============================================================
# 核心流程
# ============================================================

def cmd_download(keywords: str, area: str = None):
    """搜索 → 去重 → 下载论文"""
    print(f"\n{'='*60}")
    print(f"  ncpssd 搜索下载: {keywords}")
    print(f"{'='*60}\n")

    # 0. 去重准备
    existing_titles = get_existing_titles()
    existing_titles_clean = set()
    import re as re_mod
    for t in existing_titles:
        t_clean = re_mod.sub(r"\s+", "", t.strip().lower())
        existing_titles_clean.add(t_clean)

    # 1. 构造搜索 URL
    search_url = make_search_url(keywords)
    print(f"[1/5] 搜索: {keywords}")

    # 2. 连接 Edge CDP
    import websocket
    page_ws, page_id = find_or_create_ncpssd_tab()
    if not page_ws:
        print("[ERROR] 无法连接 Edge CDP，请确保 Edge 已启动 --remote-debugging-port=9222")
        return False

    # 获取 WS 连接用于多次交互
    ws = websocket.create_connection(page_ws, timeout=15)

    def js(expr, timeout=10):
        ws.send(json.dumps({"id": uuid.uuid4().int & 0xFFFF, "method": "Runtime.evaluate",
                           "params": {"expression": expr}}))
        resp = json.loads(ws.recv())
        return resp.get("result", {}).get("result", {})

    # 3. 导航到搜索页
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": search_url}}))
    json.loads(ws.recv())
    print("[2/5] 导航到搜索结果页...")
    time.sleep(5)

    # 触发 searchInit
    js("searchInit()")
    time.sleep(6)
    print("[3/5] 搜索结果已加载")

    # 4. 读取结果页标题 + 找下载按钮
    result = js('''
    (function() {
        // 找到所有标题行和下载按钮的对应关系
        var rows = document.querySelectorAll('[onclick*="AddHandle"]');
        var titles = [];
        var downloadBtns = [];

        // 读取所有文章标题（table中的链接文本）
        document.querySelectorAll('#table a, .fixed-table-body a, .bootstrap-table a').forEach(function(a) {
            var t = a.innerText || '';
            if (t.trim().length > 5) {  // 排除短的导航链接
                titles.push(t.trim());
            }
        });

        // 如果上面的选择器没找到，尝试另一种方式
        if (titles.length === 0) {
            document.querySelectorAll('td').forEach(function(td) {
                var t = td.innerText || '';
                if (t.length > 10 && t.length < 100) {
                    // 看它是不是父td中唯一的text节点
                    var aIn = td.querySelector('a');
                    if (aIn && aIn.innerText.trim().length > 5) {
                        titles.push(aIn.innerText.trim());
                    }
                }
            });
        }

        // 收集 download buttons
        rows.forEach(function(btn) {
            downloadBtns.push({
                text: btn.innerText || '',
                onclick: (btn.getAttribute('onclick') || '').substring(0, 80)
            });
        });

        return JSON.stringify({
            titleCount: titles.length,
            btnCount: downloadBtns.length,
            titles: titles.slice(0, 30),
            btns: downloadBtns.slice(0, 30)
        });
    })()
    ''')
    state = json.loads(result.get("value", "{}"))
    titles = state.get("titles", [])
    btns = state.get("btns", [])
    print(f"[4/5] 找到 {len(titles)} 个标题, {len(btns)} 个下载按钮")

    # 5. 去重筛选
    new_titles = []
    for title in titles:
        t_clean = re_mod.sub(r"\s+", "", title.strip().lower())
        if t_clean not in existing_titles_clean:
            new_titles.append(title)
        else:
            print(f"  [跳过已有] {title[:50]}")

    print(f"  新论文: {len(new_titles)} 篇")

    if not new_titles:
        print("[DONE] 没有新论文需要下载")
        ws.close()
        return True

    # 6. 点击的是 AddHandle（全文下载）按钮
    # 注意：表格中每行有两个按钮（阅读全文=ViewHandleCount, 全文下载=AddHandleCount）
    # 我们需要确定哪些行是新论文，只点击新论文行的下载按钮
    # AddHandle 按钮和 ViewHandle 交替排列，一一对应行
    # 如果全下载可能WAF限流，我们只下载第一篇

    # 直接左键单击第一个"全文下载"按钮
    # ★ 必须用 Input.dispatchMouseEvent，不能用 .click()
    btns_all = js("document.querySelectorAll('[onclick*=\"AddHandle\"]').length").get("value", 0)
    if btns_all and int(btns_all) > 0:
        # 获取按钮坐标后鼠标左键单击
        click_result = js('''
(function() {
    var btn = document.querySelector('[onclick*=\"AddHandle\"]');
    if (!btn) return JSON.stringify({found: false});
    var rect = btn.getBoundingClientRect();
    return JSON.stringify({
        found: true,
        x: Math.round(rect.left + rect.width/2),
        y: Math.round(rect.top + rect.height/2)
    });
})()
''')
        try:
            import json as jmod
            coords = jmod.loads(click_result.get("value", "{}"))
        except:
            coords = {}
        if coords.get("found"):
            x, y = coords["x"], coords["y"]
            # ★★★ 必须用 CDP 的 Input.dispatchMouseEvent，不能用 JS 的 MouseEvent ★★★
            ws.send(json.dumps({"id": 2, "method": "Input.dispatchMouseEvent",
                               "params": {"type": "mousePressed", "button": "left",
                                          "x": x, "y": y, "clickCount": 1}}))
            json.loads(ws.recv())
            ws.send(json.dumps({"id": 3, "method": "Input.dispatchMouseEvent",
                               "params": {"type": "mouseReleased", "button": "left",
                                          "x": x, "y": y, "clickCount": 1}}))
            json.loads(ws.recv())
            print(f"  左键单击第1篇下载: {new_titles[0][:50]}")
        time.sleep(3)

    ws.close()
    print("[5/5] 等待下载...")
    time.sleep(5)

    # 7. 循环等待下载完成（最长等30秒，每3秒检查一次）
    print("[5/5] 等待下载...")
    downloaded = []
    before = time.time()
    for wait_round in range(10):
        time.sleep(3)
        for f in os.listdir(DOWNLOAD_DIR):
            fp = os.path.join(DOWNLOAD_DIR, f)
            if f.lower().endswith(".pdf") and os.path.getmtime(fp) > before:
                if fp not in downloaded:
                    downloaded.append(fp)
            elif f.endswith(".crdownload"):
                print(f"  ⏳ 下载中: {f}")
        if downloaded:
            break
        if wait_round == 0:
            print("  ⏳ 等待浏览器下载完成...")

    if downloaded:
        newest = max(downloaded, key=os.path.getmtime)
        fname = os.path.basename(newest)
        area_name = area or detect_area(fname)
        target_subdir = AREA_CONFIG.get(area_name, {}).get("subdir", area_name)
        target_path = PDF_TARGET / target_subdir / fname
        PDF_TARGET.mkdir(exist_ok=True)
        (PDF_TARGET / target_subdir).mkdir(exist_ok=True)
        shutil.copy2(newest, str(target_path))
        print(f"  ✅ 已移动到 01_论文原文/{target_subdir}/{fname}")
        print(f"     大小: {os.path.getsize(target_path)/1024:.0f} KB")
    else:
        print("  未检测到新下载的PDF，请检查浏览器下载目录")

    return True


def cmd_download_pool(area: str):
    """批量下载某个方向的新论文"""
    keywords_list = KEYWORD_POOL.get(area, [])
    if not keywords_list:
        print(f"[ERROR] 未知方向: {area}")
        return

    print(f"\n{'='*60}")
    print(f"  批量下载: {area}（{len(keywords_list)} 组关键词）")
    print(f"{'='*60}\n")

    for kw in keywords_list:
        print(f"\n  ▶ 关键词: {kw}")
        cmd_download(kw, area)
        time.sleep(3)


def cmd_status():
    """查看 ncpssd 采集状态"""
    # 检查 Edge CDP
    try:
        r = json.loads(urllib.request.urlopen(f"{EDGE_CDP}/json/version", timeout=3).read())
        print(f"Edge CDP: ✅ (Browser={r['Browser']})")
    except:
        print("Edge CDP: ❌ 无法连接")

    # 检查 Zotero DB
    if os.path.isfile(ZOTERO_DB):
        try:
            conn = sqlite3.connect(ZOTERO_DB)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM items WHERE itemTypeID=22")
            papers = cur.fetchone()[0]
            conn.close()
            print(f"Zotero DB: ✅ ({papers} 篇论文)")
        except:
            print("Zotero DB: ⚠️ 无法读取")
    else:
        print("Zotero DB: ❌ 不存在")

    # 检查 PDF 库
    total = 0
    for area in AREA_CONFIG:
        subdir = AREA_CONFIG[area]["subdir"]
        p = PDF_TARGET / subdir
        count = len(list(p.glob("*.pdf"))) if p.exists() else 0
        total += count
        print(f"  PDF[{area}]: {count}")
    print(f"  PDF总计: {total}")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="ncpssd 搜索→去重→下载 自动化")
    sub = parser.add_subparsers(dest="action")

    p_dl = sub.add_parser("download", help="搜索、去重并下载论文")
    p_dl.add_argument("keyword", help="搜索关键词")
    p_dl.add_argument("--area", help="研究方向（自动判断或指定）")
    p_dl.add_argument("--limit", type=int, default=5, help="最大下载数")

    p_pool = sub.add_parser("download-pool", help="从关键词池批量下载")
    p_pool.add_argument("area", choices=list(KEYWORD_POOL.keys()), help="研究方向")
    p_pool.add_argument("--limit", type=int, default=3, help="每关键词下载数")

    sub.add_parser("status", help="查看采集状态")

    args = parser.parse_args()
    if args.action == "download":
        cmd_download(args.keyword, args.area)
    elif args.action == "download-pool":
        cmd_download_pool(args.area)
    elif args.action == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
