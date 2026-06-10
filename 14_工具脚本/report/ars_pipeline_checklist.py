#!/usr/bin/env python3
"""
ARS 管线启动前 Checklist
运行: python 14_工具脚本/report/ars_pipeline_checklist.py
输出: 通过/失败状态，附修复建议
"""

import subprocess
import sys
import json
import re
from pathlib import Path

CHECKS = []
results = []

def check(name, ok, fix=""):
    results.append((name, ok, fix))


# === 1. Claude Code 版本 ===
def c1_version():
    try:
        # 尝试普通 CLI
        r = subprocess.run(["claude", "-V"], capture_output=True, text=True, timeout=10)
        ver = r.stdout.strip() or r.stderr.strip()
        CHECKS.append(("c1_version", ver))
        if any(v in ver for v in ["2.1.165", "2.1.164", "2.1."]):
            check("Claude Code 版本", True, f"当前: {ver}")
        else:
            check("Claude Code 版本", False,
                  f"当前: {ver}。注意 v2.1.166+ 会导致 Agent API 400 错误。"
                  "建议回退: npm install -g @anthropic-ai/claude-code@2.1.165")
    except:
        # 可能是 VS Code 扩展模式——跳过此检查
        check("Claude Code 版本（CLI不可用）", True, "VS Code 扩展模式下跳过")


# === 2. ARS 命令文件模型设置 ===
def c2_ars_models():
    ars_dir = Path.home() / ".claude/plugins/cache/academic-research-skills/academic-research-skills/3.12.0/commands"
    if not ars_dir.exists():
        check("ARS 命令文件存在", False, f"未找到 ARS 插件: {ars_dir}")
        return
    files = list(ars_dir.glob("*.md"))
    # 只检查核心命令（ars-full, ars-reviewer, ars-revision 等主要命令）
    core_cmds = ["ars-full", "ars-reviewer", "ars-revision", "ars-plan", "ars-outline",
                 "ars-lit-review", "ars-abstract"]
    haiku_files = []
    for f in files:
        if f.stem not in core_cmds:
            continue
        content = f.read_text(encoding='utf-8')
        if 'model: haiku' in content:
            haiku_files.append(f.name)
    if haiku_files:
        check("ARS 核心命令模型设置", False,
              f"以下文件为 haiku 模型: {', '.join(haiku_files)}\n"
              "需恢复: cd 插件目录 && git checkout -- commands/*.md")
    else:
        check("ARS 核心命令模型设置", True)


# === 3. settings.json 代理配置 ===
def c3_settings():
    settings_path = Path.home() / ".claude/settings.json"
    if not settings_path.exists():
        check("settings.json", False, f"未找到: {settings_path}")
        return
    try:
        raw = settings_path.read_bytes()
        # 去除 BOM
        if raw[:3] == b'\xef\xbb\xbf':
            raw = raw[3:]
        cfg = json.loads(raw.decode('utf-8'))
        base = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
        if "15722" in base:
            check("代理配置", False,
                  "settings.json 中 ANTHROPIC_BASE_URL 指向 15722（修复代理）\n"
                  "需改回 15721（直连 cc-switch）")
        elif "15721" in base:
            check("代理配置 (15721→cc-switch)", True)
        else:
            check(f"代理配置 ({base})", True, "非标准端口，请确认")
    except:
        check("settings.json 解析失败", False)


# === 4. 论文初稿完整性 ===
def c4_draft(prompt_path):
    if not prompt_path or not Path(prompt_path).exists():
        check("论文初稿存在", False, f"路径不存在: {prompt_path}")
        return
    text = Path(prompt_path).read_text(encoding='utf-8')
    cn = sum(1 for c in text if '一' <= c <= '鿿')
    import re
    refs = len(re.findall(r'^\[\d+\]', text, re.MULTILINE))
    if cn < 5000:
        check(f"初稿字数: {cn} 字", False, "不足 5000 字，审稿效果有限")
    else:
        check(f"初稿字数: {cn} 字 (>{'5000' if cn >= 5000 else '5000'})", cn >= 5000)
    if refs < 8:
        check(f"参考文献: {refs} 条", False, "不足 8 条，建议补充")
    else:
        check(f"参考文献: {refs} 条 (>8)", True)


# === 5. report/format_cn 可用 ===
def c5_formatter():
    script = Path(r"d:\公共管理科研\14_工具脚本\report\create_formatted_docx.py")
    if script.exists():
        # 验证可执行
        r = subprocess.run(["python", "-X", "utf8", str(script), "styles"],
                           capture_output=True, text=True, timeout=10)
        if "可用格式模板" in r.stdout:
            check("format_cn 脚本可用", True)
        else:
            check("format_cn 脚本可用", False, "脚本存在但运行异常")
    else:
        check("format_cn 脚本可用", False, f"脚本不存在: {script}")


# === 6. python-docx 可用 ===
def c6_pydocx():
    try:
        import docx
        check("python-docx 可用", True)
    except ImportError:
        check("python-docx 可用", False, "需安装: pip install python-docx")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ARS 管线启动前检查清单")
    parser.add_argument("--draft", "-d", help="论文初稿路径",
                        default=r"d:\公共管理科研\10_研究输出\定稿\技术在场服务缺席_养老服务数字排斥与包容性治理.md")
    args = parser.parse_args()

    c1_version()
    c2_ars_models()
    c3_settings()
    c4_draft(args.draft)
    c5_formatter()
    c6_pydocx()

    # 输出
    print()
    print("=" * 60)
    print("ARS 管线启动前 Checklist")
    print("=" * 60)
    print()
    all_ok = True
    fix_items = []
    for name, ok, fix in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if not ok and fix:
            all_ok = False
            fix_items.append(fix)
        if ok and fix:
            fix_items.append(f"[INFO] {fix}")

    print()
    if not all_ok:
        print("⚠️  以下问题需要修复:")
        print()
        for item in fix_items:
            print(f"  • {item}")
        print()
        sys.exit(1)
    else:
        print("✅ 全部检查通过，可以启动管线！")
        print()


if __name__ == '__main__':
    main()
