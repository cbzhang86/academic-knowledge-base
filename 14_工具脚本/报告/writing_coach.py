#!/usr/bin/env python3
"""
论文写作全流程支撑 (writing_coach.py)
选题 -> 提纲 -> 草稿 -> 修订 -> 完稿

用法:
    python writing_coach.py init "论文标题" --area 公共管理学
    python writing_coach.py outline "论文标题"
    python writing_coach.py draft "论文标题"
    python writing_coach.py revise "论文标题"
    python writing_coach.py status
"""

import json, sys
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

PROJECTS_DIR = PROJECT_ROOT / "output" / "写作项目"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def load_project(name):
    path = PROJECTS_DIR / f"{name.replace(' ', '_')}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_project(name, data):
    safe_name = name.replace(' ', '_')
    (PROJECTS_DIR / f"{safe_name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def search_knowledge_base(area, keywords):
    """从知识库搜索相关精读报告"""
    results = []
    report_dir = DIRS["02_reports"] / area
    if not report_dir.exists():
        return results

    for f in report_dir.glob("*.md"):
        if "索引" in f.name or f.name.endswith(".summary.md"):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                # Extract title
                title_match = re.search(r'\*\*标题\*\*[:：]\s*(.+?)(?:\n|$)', content)
                title = title_match.group(1).strip()[:50] if title_match else f.stem[:50]
                results.append({
                    "file": f.name,
                    "title": title,
                    "score": score,
                })
        except Exception:
            pass

    return sorted(results, key=lambda x: -x["score"])[:10]


def cmd_init(args):
    """初始化写作项目"""
    if load_project(args.title):
        print(f"[WARN] 项目已存在: {args.title}")
        return

    data = {
        "title": args.title,
        "area": args.area,
        "stage": "选题",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "progress": 0,
        "notes": [],
        "sections": {
            "选题": "已完成",
            "文献综述": "待完成",
            "研究方法": "待完成",
            "数据分析": "待完成",
            "结论": "待完成",
        }
    }
    save_project(args.title, data)
    print(f"[OK] 项目创建: {args.title}")
    print(f"       方向: {args.area}")
    print(f"       下一步: python writing_coach.py outline \"{args.title}\"")


def cmd_outline(args):
    """生成论文大纲"""
    project = load_project(args.name)
    if not project:
        print(f"[ERROR] 项目不存在: {args.name}")
        return

    # 搜索相关精读报告
    keywords = project["title"].split()[:3]
    related = search_knowledge_base(project["area"], keywords)

    outline = f"""# {project["title"]} - 论文大纲

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> 研究方向: {project["area"]}

## 1. 引言
- 研究背景与问题提出
- 研究意义（理论+实践）
- 研究框架概述

## 2. 文献综述
- 核心概念界定
- 理论基础
- 相关研究回顾
- 研究空白与本研究定位

## 3. 研究方法
- 数据来源与样本描述
- 变量设计与测量
- 分析方法
- 稳健性检验设计

## 4. 实证分析
- 描述性统计
- 主效应检验
- 机制检验（如有）
- 稳健性检验

## 5. 结论与讨论
- 主要发现
- 理论贡献
- 政策建议
- 研究局限与未来方向

## 参考精读报告
"""
    if related:
        for r in related[:8]:
            outline += f"- [{r['file']}] {r['title']}\n"
    else:
        outline += "- (暂无匹配精读报告，建议补充阅读)\n"

    out_path = PROJECTS_DIR / f"{project['title'].replace(' ', '_')}_大纲.md"
    out_path.write_text(outline, encoding="utf-8")

    project["stage"] = "提纲"
    project["progress"] = 20
    project["notes"].append(f"大纲生成: {out_path.name}")
    save_project(project["title"], project)

    print(f"[OK] 大纲生成: {out_path}")
    print(f"[OK] 找到 {len(related)} 篇相关精读报告")


def cmd_draft(args):
    """生成草稿模板"""
    project = load_project(args.name)
    if not project:
        print(f"[ERROR] 项目不存在: {args.name}")
        return

    draft = f"""# {project["title"]} - 草稿

## 1. 引言
（约1000字）
[ ] 研究背景描述
[ ] 核心问题提出
[ ] 研究意义阐述

## 2. 文献综述
（约3000字）
[ ] 核心概念界定
[ ] 理论框架构建
[ ] 文献回顾与评述

## 3. 研究方法
（约1500字）
[ ] 数据来源说明
[ ] 变量设计
[ ] 分析方法

## 4. 实证分析
（约3000字）
[ ] 描述性统计
[ ] 主效应检验
[ ] 机制/稳健性

## 5. 结论
（约1000字）
[ ] 主要发现
[ ] 理论贡献
[ ] 政策建议
[ ] 研究局限

---
写作进度: {project['progress']}%
当前阶段: {project['stage']}
"""

    out_path = PROJECTS_DIR / f"{project['title'].replace(' ', '_')}_草稿.md"
    out_path.write_text(draft, encoding="utf-8")

    project["stage"] = "草稿"
    project["progress"] = 50
    project["notes"].append(f"草稿模板: {out_path.name}")
    save_project(project["title"], project)

    print(f"[OK] 草稿模板: {out_path}")
    print("[HINT] 建议: 使用 06_学术写作素材库/ 中的素材填充")


def cmd_revise(args):
    """生成修订清单"""
    project = load_project(args.name)
    if not project:
        print(f"[ERROR] 项目不存在: {args.name}")
        return

    checklist = f"""# {project['title']} - 修订清单

## 结构与逻辑
- [ ] 引言是否清晰提出研究问题？
- [ ] 文献综述是否覆盖关键文献？
- [ ] 理论框架是否自洽？
- [ ] 假设推导是否有逻辑跳跃？
- [ ] 方法部分是否可复现？
- [ ] 结果报告是否完整？
- [ ] 结论是否回应研究问题？

## 格式与规范
- [ ] 引用格式统一（GB/T 7714）
- [ ] 表格/图表规范
- [ ] 字体、行距符合期刊要求
- [ ] 摘要字数控制（300字以内）
- [ ] 关键词3-5个

## 学术规范
- [ ] 避免自我抄袭
- [ ] 数据来源标注清晰
- [ ] 利益冲突声明
- [ ] 致谢完整

---
建议对照: 10_审稿常见问题
"""

    out_path = PROJECTS_DIR / f"{project['title'].replace(' ', '_')}_修订清单.md"
    out_path.write_text(checklist, encoding="utf-8")

    project["stage"] = "修订"
    project["progress"] = 80
    project["notes"].append(f"修订清单: {out_path.name}")
    save_project(project["title"], project)

    print(f"[OK] 修订清单: {out_path}")


def cmd_status(args):
    """查看所有项目状态"""
    print("=" * 60)
    print("论文写作项目状态")
    print("=" * 60)

    projects = list(PROJECTS_DIR.glob("*.json"))
    # 过滤掉大纲等副文件
    projects = [p for p in projects if not p.name.endswith("_大纲.json")]

    if not projects:
        print("\n暂无写作项目。")
        print("创建: python writing_coach.py init \"论文标题\" --area 公共管理学")
        return

    for p in sorted(projects):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            progress = data.get("progress", 0)
            bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
            print(f"\n{data['title']}")
            print(f"  阶段: {data['stage']}")
            print(f"  进度: [{bar}] {progress}%")
            print(f"  方向: {data.get('area', '未指定')}")
        except Exception:
            pass

    print("\n" + "=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="论文写作全流程支撑")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="初始化项目")
    p_init.add_argument("title", help="论文标题")
    p_init.add_argument("--area", required=True, help="研究方向")

    p_outline = sub.add_parser("outline", help="生成大纲")
    p_outline.add_argument("name", help="项目标题")

    p_draft = sub.add_parser("draft", help="生成草稿")
    p_draft.add_argument("name", help="项目标题")

    p_revise = sub.add_parser("revise", help="生成修订清单")
    p_revise.add_argument("name", help="项目标题")

    sub.add_parser("status", help="查看状态")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "outline": cmd_outline,
        "draft": cmd_draft,
        "revise": cmd_revise,
        "status": cmd_status,
    }

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()
        print("\n示例:")
        print('  python writing_coach.py init "数字政府治理研究" --area 公共管理学')
        print('  python writing_coach.py outline "数字政府治理研究"')


if __name__ == "__main__":
    main()
