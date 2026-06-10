#!/usr/bin/env python3
"""
报告 → ARS 桥接工具 (report/ars_bridge.py)
功能：将研究报告原料包传递给 ARS（academic-research-skills）写作插件

流程：
  1. 检查 ARS 是否已安装
  2. 读取原料包内容
  3. 格式化为 ARS 可用的输入
  4. 输出运行指令（供 AI Agent 或人工执行）

用法：
    python report/ars_bridge.py check                           # 检查 ARS 安装状态
    python report/ars_bridge.py send --input 原料包路径          # 发送原料包到 ARS
    python report/ars_bridge.py send --last                      # 使用最新的原料包
    python report/ars_bridge.py list                            # 列出所有原料包
"""

import sys, os, json, shutil, subprocess
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

ARS_OUTPUT_DIR = DIRS["10_output"] / "ars_output"
FINAL_DIR = DIRS["10_output"] / "定稿"
STARTER_DIR = DIRS["10_output"] / "原料包"


def check_ars_installed() -> bool:
    """检查 ARS 插件是否已安装。

    检测方式（v2 兼容）：
      1. 新版插件系统：~/.claude/plugins/marketplaces/academic-research-skills/
      2. 旧版 skills 系统：~/.claude/skills/
      3. 项目级 skills
    """
    claude_dir = Path.home() / ".claude"

    # 检测 1：新版插件系统（installed_plugins.json）
    plugin_db = claude_dir / "plugins" / "installed_plugins.json"
    if plugin_db.exists():
        try:
            import json
            data = json.loads(plugin_db.read_text(encoding="utf-8"))
            plugins = data if isinstance(data, list) else [data]
            for p in plugins:
                if isinstance(p, dict) and p.get("name") == "academic-research-skills":
                    if p.get("scope") == "user":
                        return True
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # 检测 2：新版插件系统（目录标记）
    plugin_dir = claude_dir / "plugins" / "marketplaces" / "academic-research-skills"
    if plugin_dir.exists():
        # 检查关键文件存在以确认完整安装
        if (plugin_dir / ".claude-plugin" / "plugin.json").exists():
            return True

    # 检测 3：旧版 skills 系统
    skills_dir = claude_dir / "skills"
    ars_markers = [
        skills_dir / "academic-research-skills",
        skills_dir / "ars-plan",
        skills_dir / "ars-full",
        skills_dir / "ars-abstract",
        skills_dir / "ars-outline",
        skills_dir / "ars-lit-review",
    ]
    for marker in ars_markers:
        if marker.exists():
            return True

    # 检测 4：项目级 .claude/skills
    project_skills = PROJECT_ROOT / ".claude" / "skills"
    if project_skills.exists():
        for name in ["academic-research-skills", "ars-plan"]:
            if (project_skills / name).exists():
                return True

    return False


def get_install_guide() -> str:
    """获取 ARS 安装指引"""
    return """## 📦 ARS (academic-research-skills) 安装指引

ARS 是一个 Claude Code 插件，用于全流程论文写作支持。

### 安装方法

在 Claude Code 中执行以下命令：

```
/plugin marketplace add Imbad0202/academic-research-skills
/plugin install academic-research-skills
```

### 验证安装

安装后，在 Claude Code 中输入 `/ars-` 并按 Tab，应能看到以下命令：
  - /ars-plan      — 规划论文结构
  - /ars-full      — 全流程写作
  - /ars-outline   — 生成大纲
  - /ars-abstract  — 写摘要
  - /ars-lit-review — 文献综述

### 使用流程

完成安装后，重新运行本工具发送原料包即可。
"""


def list_starter_packs() -> list:
    """列出所有原料包"""
    if not STARTER_DIR.exists():
        return []
    packs = []
    for f in sorted(STARTER_DIR.glob("研究启动_*.md")):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = f.stat().st_size
        packs.append({
            "name": f.name,
            "path": str(f),
            "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
            "size": f"{size / 1024:.0f} KB",
        })
    return packs


def get_latest_pack() -> Path:
    """获取最新原料包"""
    packs = list(STARTER_DIR.glob("研究启动_*.md"))
    if not packs:
        return None
    return max(packs, key=lambda p: p.stat().st_mtime)


def format_ars_prompt(pack_path: Path, mode: str = "plan") -> str:
    """将原料包格式化为 ARS 输入。

    Args:
        pack_path: 原料包路径
        mode: ARS 模式 — plan / full / outline / lit-review

    Returns:
        格式化的提示文本
    """
    content = pack_path.read_text(encoding="utf-8", errors="replace")

    # 提取研究想法（文件名中的想法部分）
    idea_name = pack_path.stem.replace("研究启动_", "")

    mode_descriptions = {
        "plan": "规划论文结构（Socratic 对话式）",
        "full": "全流程写作（研究→草稿→审稿→修订→定稿）",
        "outline": "生成论文大纲",
        "lit-review": "生成文献综述",
        "abstract": "写摘要",
    }

    desc = mode_descriptions.get(mode, mode)

    prompt = f"""# ARS 输入包：{idea_name}

## 使用模式
建议使用 `/ars-{mode}` — {desc}

## 原料包内容

{content}

---

## 下一步

1. 将以上内容复制到 Claude Code 对话中
2. 先运行 `/ars-plan` 进行结构规划
3. 或直接运行 `/ars-full` 进行全流程写作
4. ARS 产出将保存在: {ARS_OUTPUT_DIR}
5. 定稿后移入: {FINAL_DIR}
"""
    return prompt


def cmd_check():
    """检查 ARS 安装状态"""
    print("=" * 60)
    print("  ARS (academic-research-skills) 状态检查")
    print("=" * 60)

    installed = check_ars_installed()

    if installed:
        print("\n  ✅ ARS 已安装")
        print("\n  可用命令:")
        print("    /ars-plan         — 规划论文结构")
        print("    /ars-full         — 全流程写作")
        print("    /ars-outline      — 生成论文大纲")
        print("    /ars-abstract     — 写摘要")
        print("    /ars-lit-review   — 文献综述")
        print("    /ars-reviewer     — 模拟同行评审")
        print("\n  发送原料包:")
        print(f"    python 14_工具脚本/report/ars_bridge.py send --last")
    else:
        print("\n  ❌ ARS 未安装")
        print(get_install_guide())

    # 列出已有原料包
    packs = list_starter_packs()
    if packs:
        print(f"\n  已有原料包 ({len(packs)} 个):")
        for p in packs:
            print(f"    [{p['mtime']}] {p['name']} ({p['size']})")
    else:
        print(f"\n  暂无原料包。先运行研究启动器：")
        print(f"    python 14_工具脚本/report/starter.py \"研究想法\" --direction 方向")


def cmd_send(pack_path: str = None, mode: str = "plan"):
    """发送原料包到 ARS"""
    # 确定原料包路径
    input_path = None
    if pack_path:
        input_path = Path(pack_path)
    else:
        input_path = get_latest_pack()

    if not input_path or not input_path.exists():
        print("[ERROR] 未找到原料包。请指定路径或先生成原料包。")
        print(f"  用法: python 14_工具脚本/report/ars_bridge.py send --input 路径")
        print(f"  或:  python 14_工具脚本/report/starter.py \"研究想法\" --direction 方向")
        return 1

    # 检查 ARS
    installed = check_ars_installed()
    if not installed:
        print("\n  ⚠️  ARS 未安装，请先安装：")
        print(get_install_guide())
        print("\n  ⚠️  即使未安装 ARS，原料包内容已准备好，可手动复制给其他 AI 工具使用。\n")

    # 格式化提示
    prompt = format_ars_prompt(input_path, mode)

    # 输出
    print(prompt)

    # 保存到 ars_output 以便参考
    ARS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = ARS_OUTPUT_DIR / f"ARS_输入_{input_path.stem.replace('研究启动_', '')}_{mode}.md"
    output_file.write_text(prompt, encoding="utf-8")
    print(f"\n---")
    print(f"ARS 输入已保存: {output_file}")

    if installed:
        print(f"\n在 Claude Code 中运行以下命令启动写作:")
        print(f"  /ars-{mode}")
        print(f"然后将上述内容粘贴到对话中。")
    else:
        print(f"\n安装 ARS 后，在 Claude Code 中运行：")
        print(f"  /ars-{mode}")
        print(f"然后将上述内容粘贴到对话中。")

    # 如果安装了 ARS，直接自动调用
    if installed:
        print(f"\n✅ ARS 已安装，准备自动调用...")
        print(f"   请运行: /ars-{mode}")
        print(f"   本脚本已为你准备好输入内容，直接粘贴即可。")

    return 0


def cmd_list():
    """列出所有原料包"""
    packs = list_starter_packs()
    if not packs:
        print("暂无原料包。")
        print(f"先运行: python 14_工具脚本/report/starter.py \"研究想法\" --direction 方向")
        return

    print(f"原料包 ({len(packs)} 个):")
    print(f"{'时间':20s} {'大小':8s} {'文件名':50s}")
    print("-" * 80)
    for p in packs:
        print(f"{p['mtime']:20s} {p['size']:8s} {p['name']:50s}")
    print()
    print(f"发送最新包: python 14_工具脚本/report/ars_bridge.py send --last")
    print(f"发送指定包: python 14_工具脚本/report/ars_bridge.py send --input 路径")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="报告 → ARS 桥接工具")
    sub = parser.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="检查 ARS 安装状态")

    p_send = sub.add_parser("send", help="发送原料包到 ARS")
    p_send.add_argument("--input", help="原料包路径（不指定则用最新）")
    p_send.add_argument("--last", action="store_true", help="使用最新的原料包")
    p_send.add_argument("--mode", default="plan",
                        choices=["plan", "full", "outline", "lit-review", "abstract"],
                        help="ARS 模式（默认 plan）")

    p_list = sub.add_parser("list", help="列出所有原料包")

    args = parser.parse_args()

    if args.cmd == "check":
        cmd_check()
    elif args.cmd == "send":
        pack_path = args.input
        if args.last and not pack_path:
            pack_path = str(get_latest_pack()) if get_latest_pack() else None
        cmd_send(pack_path, args.mode)
    elif args.cmd == "list":
        cmd_list()
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main() or 0)
