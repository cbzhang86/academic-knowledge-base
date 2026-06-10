#!/usr/bin/env python3
"""知识库主控 (pipeline.py) — 统一仲裁器

用法：
    python pipeline.py status              # 查看知识库状态
    python pipeline.py run                 # 全流程运行
    python pipeline.py run --from collect  # 从指定阶段开始
    python pipeline.py run --to report     # 执行到指定阶段
    python pipeline.py run --from extract --to report  # 局部执行
    python pipeline.py collect             # 快捷：仅采集
    python pipeline.py extract             # 快捷：仅提取
    python pipeline.py report              # 快捷：仅报告

阶段依赖图：
    config (stage0) ← 检查配置文件
      │
      ▼
    collect (stage1) ← 采集新论文
      │
      ▼
    dedup (stage2) ← 去重检查
      │
      ▼
    archive (stage3) ← 归档到后端
      │
      ▼
    review (stage4) ← 精读分析
      │
      ▼
    extract (stage5) ← 跨篇沉淀
      │
      ▼
    report (stage6) ← 生成日报/周报/月报
"""

import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from global_config import PROJECT_ROOT, DIRS

AREAS = ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]

# ── 阶段定义 ────────────────────────────────────────────
STAGES = {
    "config":   {"desc": "检查配置文件",         "deps": [],                "script": None},  # 内置检查
    "collect":  {"desc": "采集新论文",            "deps": ["config"],        "script": "采集/ncpssd_cdp.py"},
    "dedup":    {"desc": "去重检查",              "deps": ["collect"],       "script": "metadata/dedup.py"},
    "archive":  {"desc": "归档到后端",            "deps": ["dedup"],         "script": "metadata/archive.py"},
    "review":   {"desc": "精读分析（需人工）",     "deps": ["archive"],       "script": None},  # 人工流程
    "extract":  {"desc": "跨篇沉淀再生",           "deps": ["review"],        "script": "提取/regenerate_all.py"},
    "report":   {"desc": "生成日报/周报/月报",      "deps": ["extract"],       "script": "报告/daily_weekly_monthly.py"},
}

STAGE_ORDER = ["config", "collect", "dedup", "archive", "review", "extract", "report"]


# ── 阶段执行函数 ─────────────────────────────────────────
def run_skill(skill_rel: str, args: list = None):
    """运行一个 Skill 脚本"""
    script_path = DIRS["14_tools"] / skill_rel
    if not script_path.exists():
        print(f"  ⚠️  脚本不存在: {skill_rel}")
        return False
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    print(f"  ▶ {skill_rel} {' '.join(args or [])}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"  ⚠️  脚本返回非0: {result.returncode}")
    return result.returncode == 0


def check_stage(stage: str) -> bool:
    """检查某个阶段的输入条件是否满足"""
    s = STAGES.get(stage)
    if not s:
        return False

    # config 检查
    if stage == "config":
        configs = ["structure.yaml", "areas.yaml", "template.yaml"]
        missing = [c for c in configs if not (PROJECT_ROOT / "config" / c).exists()]
        if missing:
            print(f"  ⚠️  配置缺失: {', '.join(missing)}")
            print(f"  运行: python {DIRS['14_tools'] / 'global_config.py'} init")
            return False
        return True

    # 原始目录检查
    if stage == "collect":
        raw_dir = DIRS["01_raw"]
        if not raw_dir.exists():
            print(f"  ⚠️  原始论文目录不存在: {raw_dir}")
            return False
        return True

    # 精读报告检查（review 的产出）
    if stage == "extract":
        rpt_dir = DIRS["02_reports"]
        if not rpt_dir.exists():
            print(f"  ⚠️  精读报告目录不存在: {rpt_dir}")
            return False
        return True

    return True


def execute_stage(stage: str) -> bool:
    """执行单个阶段"""
    s = STAGES.get(stage)
    if not s:
        print(f"  ❌ 未知阶段: {stage}")
        return False

    print(f"\n── [{stage}] {s['desc']} ──")

    if not check_stage(stage):
        print(f"  ⏭ 条件不满足，跳过")
        return True  # 不是执行失败，是条件不满足

    if stage == "config":
        # 内置配置检查
        return True

    if stage == "review":
        print(f"  ℹ️  本阶段需要人工操作：按 analysis_template.md 模板写精读报告")
        print(f"  ℹ️  完成后运行: python pipeline.py run --from extract")
        return True

    if s["script"]:
        return run_skill(s["script"])
    return True


# ── CLI 命令 ────────────────────────────────────────────
def cmd_status():
    """查看知识库状态"""
    print("=" * 60)
    print("  Knowledge Base Status")
    print("=" * 60)
    total_pdfs = 0
    total_rpts = 0
    for area in AREAS:
        pdf_dir = DIRS["01_raw"] / area
        rpt_dir = DIRS["02_reports"] / area
        pdfs = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
        rpts = len(list(rpt_dir.glob("*_精读报告.md"))) if rpt_dir.exists() else 0
        total_pdfs += pdfs
        total_rpts += rpts
        print(f"  {area:12s}: {rpts} 精读 / {pdfs} PDF")
    print(f"  {'总计':12s}: {total_rpts} 精读 / {total_pdfs} PDF")

    # 阶段状态
    print(f"\n  阶段状态:")
    for stage in STAGE_ORDER:
        s = STAGES[stage]
        ok = check_stage(stage)
        icon = "✅" if ok else "⏭"
        print(f"    {icon} {stage:12s} {s['desc']}")
    print("=" * 60)


def cmd_run(from_stage: str = None, to_stage: str = None):
    """运行流水线"""
    start = STAGE_ORDER.index(from_stage) if from_stage else 0
    end = STAGE_ORDER.index(to_stage) + 1 if to_stage else len(STAGE_ORDER)

    stages_to_run = STAGE_ORDER[start:end]

    print(f"Pipeline: {stages_to_run[0]} → {stages_to_run[-1]}")
    print("=" * 60)

    all_ok = True
    for stage in stages_to_run:
        if not execute_stage(stage):
            s = STAGES[stage]
            print(f"\n  ❌ [{stage}] {s['desc']} 失败")
            all_ok = False
            break

    if all_ok:
        print(f"\n✅ Pipeline 完成: {stages_to_run[0]} → {stages_to_run[-1]}")
    else:
        print(f"\n⚠️  Pipeline 中止")
    return all_ok


def main():
    import argparse
    parser = argparse.ArgumentParser(description="知识库统一仲裁器")

    # subcommands
    sub = parser.add_subparsers(dest="cmd")

    # status
    sub.add_parser("status", help="查看知识库状态")

    # run
    p_run = sub.add_parser("run", help="运行流水线")
    p_run.add_argument("--from", dest="from_stage", choices=STAGE_ORDER, help="起始阶段")
    p_run.add_argument("--to", dest="to_stage", choices=STAGE_ORDER, help="结束阶段")

    # 快捷命令
    sub.add_parser("collect", help="仅采集（快捷）")
    sub.add_parser("extract", help="仅跨篇沉淀（快捷）")
    sub.add_parser("report", help="仅生成报告（快捷）")

    args = parser.parse_args()

    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "run":
        cmd_run(args.from_stage, args.to_stage)
    elif args.cmd == "collect":
        execute_stage("collect")
    elif args.cmd == "extract":
        execute_stage("extract")
    elif args.cmd == "report":
        execute_stage("report")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
