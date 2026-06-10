#!/usr/bin/env python3
"""研究启动器：从想法到 ARS 原料包"""

import sys, os, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

RPT_DIR = DIRS["02_reports"]
MATER_DIR = DIRS["03_materials"]
METHOD_DIR = DIRS["04_methods"]
OUTPUT_DIR = DIRS["10_output"] / "原料包"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_theory_xref():
    """加载理论交叉索引"""
    fp = MATER_DIR / "理论框架/00_理论交叉索引.md"
    if not fp.exists(): return {}
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    theories = {}
    current = None
    for line in content.split("\n"):
        if line.startswith("## "):
            current = line.replace("## ", "").strip()
            theories[current] = []
        elif current and "- [[" in line:
            theories[current].append(line.strip())
    return theories

def load_gaps(area):
    """加载某方向的研究空白"""
    fp = MATER_DIR / f"研究空白/{area}_研究空白.md"
    if not fp.exists(): return ""
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()

def search_reports(keyword, max_results=15):
    """在精读报告中搜索相关论文"""
    results = []
    kw_lower = keyword.lower()
    # 分词：支持"养老服务 数智化转型"这种多词查询
    kw_parts = [k.strip() for k in kw_lower.split() if len(k.strip()) > 1]
    for d in sorted(os.listdir(str(RPT_DIR))):
        dp = RPT_DIR / d
        if not dp.is_dir(): continue
        for f in sorted(dp.glob("*_精读报告.md")):
            with open(str(f), "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            # 搜索标题、主题、核心发现、理论框架
            search_text = content[:500].lower()  # frontmatter + 开头
            if "### 核心发现" in content:
                s = content.find("### 核心发现")
                search_text += content[s:s+1500].lower()
            if "### 理论框架" in content:
                s = content.find("### 理论框架")
                search_text += content[s:s+1000].lower()

            matched = False
            for kp in kw_parts:
                if kp in search_text:
                    matched = True
                    break
            if kw_lower in search_text:
                matched = True

            if matched:
                tm = re.search(r"title:\s*['\"](.+?)['\"]", content[:300])
                title = tm.group(1) if tm else f.stem
                score_m = re.search(r"score:\s*['\"]?(\d+\.?\d*)", content[:300])
                score = score_m.group(1) if score_m else ""
                finding = ""
                if "### 核心发现" in content:
                    s = content.find("### 核心发现")
                    rest = content[s+len("### 核心发现"):]
                    end = len(rest)
                    for m in ['\n### 关键论点', '\n## ', '\n---\n']:
                        pos = rest.find(m, 10)
                        if pos > 0 and pos < end: end = pos
                    finding = rest[:end].strip()[:200]
                results.append({
                    "area": d, "title": title, "score": score,
                    "finding": finding, "file": f.name
                })
    results.sort(key=lambda x: float(x["score"]) if x["score"] else 0, reverse=True)
    return results[:max_results]

def search_claims(keyword, max_results=10):
    """在关键论点中搜索"""
    fp = MATER_DIR / "关键论点/跨篇关键论点汇编.md"
    if not fp.exists(): return []
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    results = []
    kw_lower = keyword.lower()
    current_title = ""
    for line in content.split("\n"):
        if line.startswith("### "):
            current_title = line.replace("### ", "").strip()
        elif kw_lower in line.lower() and line.startswith("- "):
            results.append(f"  - {current_title}: {line[2:100]}")
    return results[:max_results]

def search_methods(keyword):
    """搜索相关方法"""
    fp = METHOD_DIR / "00_方法论总索引.md"
    if not fp.exists(): return []
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    results = []
    kw_lower = keyword.lower()
    for line in content.split("\n"):
        if kw_lower in line.lower() and "|" in line:
            results.append(line.strip())
    return results[:10]

def generate_research_brief(idea, direction=""):
    """从研究想法生成 ARS 原料包"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', idea)[:40]

    # 搜索相关论文
    papers = search_reports(idea)
    # 搜索研究空白
    gaps_text = ""
    if direction:
        gaps_text = load_gaps(direction)
    else:
        # 在所有方向中找
        for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
            g = load_gaps(d)
            if g and idea[:4] in g[:500].lower():
                gaps_text += f"\n### {d}\n{g[:2000]}"

    # 搜索关键论点
    claims = search_claims(idea)
    # 搜索理论
    theories = load_theory_xref()
    relevant_theories = {k: v for k, v in theories.items() if any(kw in k for kw in idea.split())}

    # 搜索方法
    methods = search_methods(idea)

    # 构建输出
    lines = [
        f"# 研究启动报告：{idea}",
        f"> 生成时间: {timestamp}",
        f"> 来源: 公共管理科研知识库（108篇精读 + 跨篇沉淀）",
        "",
        "---",
        "",
        "## 一、研究问题",
        "",
        f"{idea}",
        "",
        "---",
        "",
        "## 二、已有文献基础（来自知识库）",
        "",
    ]

    if papers:
        lines.append(f"### 相关精读报告（{len(papers)}篇）")
        lines.append("")
        for p in papers:
            score_str = f" ⭐{p['score']}" if p['score'] else ""
            lines.append(f"- **{p['title']}**{score_str} [{p['area']}]")
            if p['finding']:
                lines.append(f"  - 核心发现: {p['finding'][:150]}")
        lines.append("")
    else:
        lines.append("> 知识库中未找到直接相关的精读报告，可能需要补充检索。")
        lines.append("")

    if claims:
        lines.append("### 相关论点引用")
        lines.append("")
        for c in claims[:5]:
            lines.append(c)
        lines.append("")

    if relevant_theories:
        lines.append("### 可用的理论框架")
        lines.append("")
        for t, entries in list(relevant_theories.items())[:5]:
            lines.append(f"- **{t}**: {len(entries)}篇论文使用")
            for e in entries[:3]:
                lines.append(f"  - {e}")
        lines.append("")
    else:
        # 推荐常用理论
        lines.append("### 推荐关注的理论框架")
        lines.append("")
        common_theories = [
            "制度变迁理论", "社会参与理论", "人力资本理论",
            "推拉理论", "生态系统理论", "批判教育学", "冰山模型",
            "信息不对称理论", "市场一体化理论", "社会分层理论"
        ]
        for t in common_theories:
            if t in theories:
                entries = theories[t]
                lines.append(f"- **{t}**: {len(entries)}篇论文使用")

    if methods:
        lines.append("### 相关方法")
        lines.append("")
        for m in methods[:5]:
            if m.startswith("|"):
                parts = [p.strip() for p in m.split("|")]
                if len(parts) >= 3:
                    lines.append(f"- {parts[1]}: {parts[2]}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 三、研究空白",
        "",
    ])

    if gaps_text:
        # 提取空白要点
        gap_lines = gaps_text.split("\n")
        for gl in gap_lines:
            if gl.startswith("### ") or gl.startswith("- "):
                lines.append(gl)
        lines.append("")
    else:
        lines.append("> 知识库中未标记相关研究空白。")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 四、建议的研究方向",
        "",
        "基于上述分析，建议从以下角度切入：",
        "",
        "1. **理论层面**: 选择上述理论框架中的一个或多个，结合研究空白形成理论贡献",
        "2. **方法层面**: 参考同类研究的方法选择，注意已有研究的方法局限",
        "3. **实证层面**: 针对研究空白中指出的数据/样本局限进行改进",
        "",
        "---",
        "",
        "## 五、后续操作",
        "",
        "将此报告作为输入，在 Claude Code 中运行:",
        "",
        "```",
        "/ars-plan",
        "```",
        "",
        "然后将本报告的内容粘贴给 ARS 作为背景。",
        "",
        "或者运行完整流程：",
        "",
        "```",
        "/ars-full",
        "```",
        "",
        "---",
        "",
        "*本报告由公共管理科研知识库自动生成*",
    ])

    # 写入文件
    output_path = OUTPUT_DIR / f"研究启动_{safe_name}.md"
    with open(str(output_path), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] 研究启动报告: {output_path}")
    print(f"  相关论文: {len(papers)}")
    print(f"  相关论点: {len(claims)}")
    print(f"  相关理论: {len(relevant_theories)}")
    return str(output_path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="研究启动器")
    parser.add_argument("idea", help="研究想法/关键词")
    parser.add_argument("--direction", "-d", help="研究方向（可选）")
    args = parser.parse_args()
    generate_research_brief(args.idea, args.direction or "")

if __name__ == "__main__":
    main()
