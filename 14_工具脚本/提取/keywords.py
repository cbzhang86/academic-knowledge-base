#!/usr/bin/env python3
"""智能关键词生成器 — 从精读报告+研究空白自动生成关键词"""

import sys, os, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from collections import Counter

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

RPT_DIR = DIRS["02_reports"]
GAP_DIR = DIRS["03_materials"] / "研究空白"

def extract_keywords(area_dir):
    """从精读报告的 theme 字段提取关键词"""
    kws = Counter()
    dp = RPT_DIR / area_dir
    if not dp.exists(): return kws
    for f in dp.glob("*_精读报告.md"):
        with open(str(f), 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()[:500]
        m = re.search(r"theme:\s*['\"](.+?)['\"]", content)
        if m:
            theme = m.group(1)
            words = re.findall(r'[一-鿿]{2,4}(?:治理|政策|政府|服务|教育|养老|保险|分层|流动|公平|分配|收入|资本|网络|行为|健康|医疗|保障|参与|创新|技术|数字|智能|数据|金融|财政|环保|税费|组织|评估|绩效|执行|应急|安全|风险|就业|劳动|生育|家庭|阶层|群体|青年|老年|乡村|社区)', theme)
            for w in words:
                if len(w) >= 4:
                    kws[w] += 1
    return kws

def merge_and_sort(kws_counter, existing_kws, max_kws=10):
    """合并现有+增量关键词，按频次排序"""
    result = list(existing_kws)
    added = set()
    for kw, count in kws_counter.most_common(30):
        if len(result) >= max_kws + len(existing_kws):
            break
        if kw not in result and len(kw) >= 4:
            result.append(kw)
            added.add(kw)
    return result, added

def generate_all():
    areas_config = {
        "公共管理学": {"dir": "公共管理学", "existing": ["数字政府", "基层治理", "公共服务", "政策执行", "公共价值"]},
        "社会学": {"dir": "社会学", "existing": ["社会分层", "社会流动", "教育公平", "社会资本", "分配公平"]},
        "老龄化研究": {"dir": "老龄化", "existing": ["养老服务", "养老保险", "健康老龄化", "智慧养老", "人口老龄化"]},
        "青少年研究": {"dir": "青少年研究", "existing": ["青少年 网络行为", "青少年 心理健康", "青少年 社交媒体", "教育公平", "网络成瘾"]},
    }

    result = {}
    for area_key, cfg in areas_config.items():
        kws = extract_keywords(cfg["dir"])
        merged, added = merge_and_sort(kws, cfg["existing"])
        result[area_key] = merged
    return result

def main():
    new_pool = generate_all()

    for area, kws in new_pool.items():
        print(f"{area}:")
        for kw in kws:
            print(f"  - {kw}")
        print()

    # 只写 JSON，不修改源码
    json_path = PROJECT_ROOT / "config" / "auto_keywords.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(json_path), 'w', encoding='utf-8') as f:
        json.dump(new_pool, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 已导出: {json_path}")
    print(f"  ℹ️  关键词已写入 JSON 文件。如需生效，请手动同步到 config/areas.yaml")
    print(f"  ℹ️  不再自动修改脚本源码。")

if __name__ == "__main__":
    main()
