#!/usr/bin/env python3
"""
ARS-知识库桥接层：为 ARS 各阶段生成知识包。
在 ARS 每个阶段启动前运行，将知识库沉淀注入到下一阶段的上下文。

用法：
  python ars_kb_bridge.py stage-25 --topic "数字排斥" --refs "ref1,ref2,ref3"
  python ars_kb_bridge.py stage-3  --topic "养老服务 数字排斥"
  python ars_kb_bridge.py stage-4  --comments "来自审稿意见的txt文件路径"
  python ars_kb_bridge.py stage-5  --refs "最终引文列表文件路径"
"""
import sys, os, re, json, argparse
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
OUTPUT_DIR = PROJECT_ROOT / "10_研究输出" / "ars_output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ────────────── 知识库查询函数（复用 research_starter.py 的核心逻辑） ──────────────

def load_theory_xref():
    """加载理论交叉索引"""
    fp = MATER_DIR / "理论框架" / "00_理论交叉索引.md"
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
    """在精读报告中按关键词搜索，返回 {title, score, area, finding, theory, file}"""
    results = []
    kw_lower = keyword.lower()
    kw_parts = [k.strip() for k in kw_lower.split() if len(k.strip()) > 1]
    for d in sorted(os.listdir(str(RPT_DIR))):
        dp = RPT_DIR / d
        if not dp.is_dir(): continue
        for f in sorted(dp.glob("*_精读报告.md")):
            with open(str(f), "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            search_text = content[:500].lower()
            if "### 核心发现" in content:
                s = content.find("### 核心发现")
                search_text += content[s:s+1500].lower()
            if "### 理论框架" in content:
                s = content.find("### 理论框架")
                search_text += content[s:s+1000].lower()

            matched = any(kp in search_text for kp in kw_parts) or kw_lower in search_text
            if not matched:
                continue

            tm = re.search(r"title:\s*['\"](.+?)['\"]", content[:300])
            title = tm.group(1) if tm else f.stem
            score_m = re.search(r"score:\s*['\"]?(\d+\.?\d*)", content[:300])
            score = float(score_m.group(1)) if score_m else 0

            # 提取核心发现全文
            finding = ""
            if "### 核心发现" in content:
                s = content.find("### 核心发现")
                rest = content[s+len("### 核心发现"):]
                end = len(rest)
                for m in ['\n### 关键论点', '\n## ', '\n---\n']:
                    pos = rest.find(m, 10)
                    if pos > 0 and pos < end: end = pos
                finding = rest[:end].strip()[:300]

            # 提取理论框架摘要
            theory = ""
            if "### 理论框架" in content:
                s = content.find("### 理论框架")
                rest = content[s+len("### 理论框架"):]
                end = len(rest)
                for m in ['\n###', '\n---\n']:
                    pos = rest.find(m, 10)
                    if pos > 0 and pos < end: end = pos
                theory = rest[:end].strip()[:200]

            results.append({
                "area": d, "title": title, "score": score,
                "finding": finding, "theory": theory, "file": f.name
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def search_reports_by_refs(ref_list):
    """输入论文的参考文献列表，找出知识库中已精读的匹配项"""
    matches = []
    for ref in ref_list:
        ref_lower = ref.strip().lower()
        if len(ref_lower) < 10:
            continue
        for d in sorted(os.listdir(str(RPT_DIR))):
            dp = RPT_DIR / d
            if not dp.is_dir(): continue
            for f in sorted(dp.glob("*_精读报告.md")):
                with open(str(f), "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()[:2000].lower()
                # 在 frontmatter 和开头搜索 ref 关键词
                if ref_lower[:20] in content:
                    tm = re.search(r"title:\s*['\"](.+?)['\"]", fh.read()[:300] if False else content[:300])
                    title = tm.group(1) if tm else f.stem
                    score_m = re.search(r"score:\s*['\"]?(\d+\.?\d*)", content[:300])
                    score = float(score_m.group(1)) if score_m else 0
                    matches.append({
                        "ref": ref, "title": title, "score": score,
                        "area": d, "file": f.name
                    })
                    break
    return matches


def search_claims(keyword, max_results=10):
    """在关键论点中搜索"""
    fp = MATER_DIR / "关键论点" / "跨篇关键论点汇编.md"
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
            results.append(f"  - {current_title}: {line[2:120]}")
    return results[:max_results]


# ────────────── 各阶段知识包生成器 ──────────────

def gen_stage_25(topic, refs):
    """
    ARS 阶段 2.5（完整性审核）知识包。
    输入：论文主题关键词 + 参考文献列表
    输出：精读报告对照表，用于三角验证参考文献
    """
    lines = [
        "## 📚 知识库-论文引文对照",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 基于知识库 {len(list(RPT_DIR.rglob('*_精读报告.md')))} 篇精读报告",
        "",
    ]

    # 1. 按主题搜索相关精读
    papers = search_reports(topic, max_results=10)
    if papers:
        lines.append("### 与论文主题相关的高分精读报告")
        lines.append("")
        for p in papers:
            lines.append(f"- **{p['title']}** ⭐{p['score']} [{p['area']}]")
            if p['finding']:
                lines.append(f"  - 核心发现: {p['finding'][:150]}")
        lines.append("")
    else:
        lines.append("> 知识库中未找到与论文主题直接匹配的精读报告。")
        lines.append("")

    # 2. 引文对照
    if refs:
        matches = search_reports_by_refs(refs)
        if matches:
            lines.append("### 参考文献 vs 知识库精读对照")
            lines.append("")
            lines.append("| 参考文献关键词 | 知识库中匹配的精读 | 评分 | 方向 |")
            lines.append("|---------------|-------------------|:---:|:----:|")
            for m in matches:
                lines.append(f"| {m['ref'][:40]} | {m['title'][:40]} | {m['score']} | {m['area']} |")
            lines.append("")
            lines.append("**使用建议**：完整性审核时，对本表中匹配的引文做交叉验证——精读报告中的核心发现是否支持论文中的引用上下文。")
            lines.append("")
        else:
            lines.append("> 参考文献无法与知识库中已有精读匹配（可能引用了知识库未收录的论文）。")
            lines.append("")

    return "\n".join(lines)


def gen_stage_3(topic):
    """
    ARS 阶段 3（同行评审）知识包。
    注入理论框架 + 研究空白，让审稿人知道论文的学术定位。
    """
    lines = [
        "## 📚 知识库背景 —— 审稿参考",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "### 一、可用理论框架",
        "",
    ]

    # 理论框架
    theories = load_theory_xref()
    kw_parts = topic.lower().split()
    relevant = {k: v for k, v in theories.items()
                if any(kw in k.lower() for kw in kw_parts)}
    if relevant:
        for t, entries in list(relevant.items())[:8]:
            lines.append(f"- **{t}**: {len(entries)}篇论文使用")
            for e in entries[:3]:
                lines.append(f"  - {e}")
        lines.append("")
    else:
        lines.append("> （未找到与主题直接匹配的理论框架，以下是高频理论供参考）")
        lines.append("")
        for t in list(theories.keys())[:10]:
            lines.append(f"- {t}: {len(theories[t])}篇论文使用")
        lines.append("")

    # 关键论点
    claims = search_claims(topic)
    if claims:
        lines.append("### 二、相关关键论点")
        lines.append("")
        for c in claims[:5]:
            lines.append(c)
        lines.append("")

    # 研究空白
    lines.append("### 三、相关研究空白")
    lines.append("")
    found_gap = False
    for d in ["公共管理学", "社会学", "老龄化", "交叉研究"]:
        gaps_text = load_gaps(d)
        if not gaps_text: continue
        gap_lines = gaps_text.split("\n")
        relevant_gaps = [g for g in gap_lines
                         if any(kw in g.lower() for kw in kw_parts)]
        if relevant_gaps:
            found_gap = True
            lines.append(f"**{d}**：")
            for g in relevant_gaps[:3]:
                lines.append(f"  - {g}")
            lines.append("")
    if not found_gap:
        lines.append("> 知识库中未标记与主题直接相关的研究空白。")
        lines.append("")

    lines.append("---")
    lines.append("**使用建议**：审稿时关注论文的理论定位是否与领域现有理论脉络对齐，")
    lines.append("并判断其研究空白论证是否充分利用了已有文献的缺口分析。")
    return "\n".join(lines)


def gen_stage_4(comments):
    """
    ARS 阶段 4（修订）知识包。
    从审稿意见中提取"理论不足"信号，推荐可用的理论。
    """
    lines = [
        "## 📚 知识库-理论与方法推荐",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 解析审稿意见中的关键词
    # 支持直接输入文本或文件路径
    if os.path.isfile(str(comments)):
        with open(comments, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = comments

    # 提取可能的理论关键词
    signal_kws = ["理论", "概念", "框架", "模型", "方法", "视角", "范式", "mechanism", "theory", "framework"]
    topic_kws = [w.strip() for w in re.split(r'[\s,，。；;:：\n]+', text)
                 if len(w.strip()) > 1 and any(sig in w.lower() for sig in signal_kws)]

    lines.append("### 可考虑借鉴的理论框架")
    lines.append("")
    theories = load_theory_xref()
    found = False
    for t, entries in sorted(theories.items(), key=lambda x: -len(x[1])):
        # 如果审稿意见中提到了相关概念，或者该理论使用广泛
        if any(kw in t.lower() for kw in topic_kws) or len(entries) >= 5:
            lines.append(f"- **{t}**: {len(entries)}篇论文使用")
            for e in entries[:2]:
                lines.append(f"  - {e}")
            found = True
    if not found:
        # 默认推荐高频使用理论
        for t, entries in list(sorted(theories.items(), key=lambda x: -len(x[1])))[:10]:
            lines.append(f"- **{t}**: {len(entries)}篇论文使用")
    lines.append("")

    lines.append("**使用建议**：如果审稿意见中指出理论框架薄弱，从上表中选择 1-2 个与论文主题契合的理论补充到论文的理论框架部分。")
    return "\n".join(lines)


def gen_stage_5(refs):
    """
    ARS 阶段 5（定稿）后知识包。
    引文审计：论文引用了哪些知识库已有精读？漏引了哪些？
    """
    lines = [
    "## 📄 引文审计报告",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 基于知识库 {len(list(RPT_DIR.rglob('*_精读报告.md')))} 篇精读报告",
        "",
    ]

    if not refs:
        lines.append("> 未提供引文列表，无法做引文审计。")
        lines.append("> 你可以把论文的参考文献列表粘贴给我，我会生成对照表。")
        return "\n".join(lines)

    # 引文对照
    if os.path.isfile(str(refs)):
        with open(refs, "r", encoding="utf-8") as f:
            ref_list = [l.strip() for l in f if l.strip()]
    else:
        ref_list = [r.strip() for r in refs.split(",") if r.strip()]

    matches = search_reports_by_refs(ref_list)
    matched_titles = {m["title"] for m in matches}

    lines.append(f"### 论文引文：共 {len(ref_list)} 条")
    lines.append(f"### 知识库匹配：{len(matches)} 篇精读被引用或相关")
    lines.append("")

    if matches:
        lines.append("| 论文引文关键词 | 知识库精读 | 评分 | 方向 |")
        lines.append("|---------------|-----------|:---:|:----:|")
        for m in matches:
            lines.append(f"| {m['ref'][:40]} | {m['title'][:40]} | {m['score']} | {m['area']} |")
        lines.append("")

    # 高评分未引用论文
    lines.append("### 知识库中高评分但论文未引用的相关精读")
    lines.append("")
    papers = search_reports(ref_list[0] if ref_list else "", max_results=20)
    uncited = [p for p in papers if p["title"] not in matched_titles][:10]
    if uncited:
        for p in uncited:
            lines.append(f"- **{p['title']}** ⭐{p['score']} [{p['area']}]")
            if p['finding']:
                lines.append(f"  - {p['finding'][:120]}")
        lines.append("")
        lines.append("**使用建议**：检查上表中高评分论文是否应纳入论文文献综述或引用列表。")
        lines.append("如果是有意不引（如研究方向不同），无需修改；如果是遗漏，建议补充。")
    else:
        lines.append("> 未发现高评分且未引用的相关论文。")
        lines.append("")

    return "\n".join(lines)


# ────────────── CLI ──────────────

def main():
    parser = argparse.ArgumentParser(description="ARS-知识库桥接层：为ARS各阶段生成知识包")
    sub = parser.add_subparsers(dest="stage", required=True)

    p25 = sub.add_parser("stage-25", help="阶段2.5完整性审核 - 知识包")
    p25.add_argument("--topic", "-t", default="", help="论文主题关键词")
    p25.add_argument("--refs", "-r", nargs="*", default=[], help="参考文献关键词列表")

    p3 = sub.add_parser("stage-3", help="阶段3同行评审 - 知识包")
    p3.add_argument("--topic", "-t", required=True, help="论文主题关键词")
    p3.add_argument("--output", "-o", help="输出文件路径（可选，默认打印）")

    p4 = sub.add_parser("stage-4", help="阶段4修订 - 知识包")
    p4.add_argument("--comments", "-c", required=True,
                    help="审稿意见原文或文件路径（包含'理论不足'等信号词）")
    p4.add_argument("--output", "-o", help="输出文件路径（可选）")

    p5 = sub.add_parser("stage-5", help="阶段5定稿 - 引文审计")
    p5.add_argument("--refs", "-r", required=True,
                    help="参考文献列表（逗号分隔或文件路径）")
    p5.add_argument("--output", "-o", help="输出文件路径（可选）")

    # ── 新增：一键准备全部知识包（论文审稿专用） ──
    pp = sub.add_parser("prepare-paper", help="【推荐】一键生成论文审稿所需全部知识包")
    pp.add_argument("--topic", "-t", required=True, help="论文主题关键词")
    pp.add_argument("--refs", "-r", nargs="*", default=[],
                    help="参考文献关键词列表（可选，用于引文审计）")
    pp.add_argument("--paper", "-p", help="论文初稿路径（可选，stage-4会解析审稿信号词）")

    args = parser.parse_args()

    if args.stage == "prepare-paper":
        # 一键生成所有知识包
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"\n{'='*50}")
        print(f"  📚 论文审稿知识包生成")
        print(f"  主题: {args.topic}")
        print(f"{'='*50}\n")

        # Stage-3: 审稿背景包
        p3_out = gen_stage_3(args.topic)
        p3_path = OUTPUT_DIR / f"kb_pack_stage-3_{timestamp}.md"
        p3_path.write_text(p3_out, encoding="utf-8")
        print(f"  ✅ 审稿背景包 → {p3_path.name}")

        # Stage-25: 引文对照包（如果有 refs）
        if args.refs:
            p25_out = gen_stage_25(args.topic, list(args.refs))
            p25_path = OUTPUT_DIR / f"kb_pack_stage-25_{timestamp}.md"
            p25_path.write_text(p25_out, encoding="utf-8")
            print(f"  ✅ 引文对照包 → {p25_path.name}")

        # Stage-5: 引文审计包（如果有 refs）
        if args.refs:
            refs_comma = ",".join(args.refs)
            p5_out = gen_stage_5(refs_comma)
            p5_path = OUTPUT_DIR / f"kb_pack_stage-5_{timestamp}.md"
            p5_path.write_text(p5_out, encoding="utf-8")
            print(f"  ✅ 引文审计包 → {p5_path.name}")

        # Stage-4: 修订包（如果有论文初稿）
        if args.paper:
            p4_out = gen_stage_4(args.paper)
            p4_path = OUTPUT_DIR / f"kb_pack_stage-4_{timestamp}.md"
            p4_path.write_text(p4_out, encoding="utf-8")
            print(f"  ✅ 修订推荐包 → {p4_path.name}")

        print(f"\n{'='*50}")
        print(f"  全部知识包已就绪，路径: {OUTPUT_DIR}")
        print(f"  现在可以在对话中发送审稿请求（见 CLAUDE.md 推荐话术）")
        print(f"{'='*50}\n")
        return

    if args.stage == "stage-25":
        output = gen_stage_25(args.topic or "", args.refs or [])
    elif args.stage == "stage-3":
        output = gen_stage_3(args.topic)
    elif args.stage == "stage-4":
        output = gen_stage_4(args.comments)
    elif args.stage == "stage-5":
        output = gen_stage_5(args.refs)
    else:
        parser.print_help()
        return

    # 输出
    if hasattr(args, 'output') and args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[OK] 知识包已写入: {out_path}")
    else:
        # 默认写入到 ars_output/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUT_DIR / f"kb_pack_{args.stage}_{timestamp}.md"
        out_path.write_text(output, encoding="utf-8")
        print(f"[OK] 知识包已写入: {out_path}")
        print()
        print(output[:500], "...")
        print()


if __name__ == "__main__":
    main()
