#!/usr/bin/env python3
"""
推送前一致性检查（pre-push hook）。
在 git push 前自动检查 README.md、CLAUDE.md、进度看板.md 的数字是否与实际一致。
不通过时拦截推送。

安装：将其软链接或复制到 .git/hooks/pre-push
  或 git config core.hooksPath 指向本脚本所在目录

用法（手动运行）：
  python 14_工具脚本/check_push.py

返回码：
  0 = 通过
  1 = 有问题（输出红色错误）
"""
import os, re, sys, subprocess
from pathlib import Path

# ── 颜色 ──
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

PROJECT = Path(__file__).resolve().parent.parent  # 知识库根目录
ERR = 0

def e(msg):
    global ERR
    ERR = 1
    msg_clean = msg.encode('ascii', 'ignore').decode('ascii') if sys.platform == 'win32' else msg
    print(f"  {RED}[FAIL]{RESET} {msg_clean}")

def ok(msg):
    msg_clean = msg.encode('ascii', 'ignore').decode('ascii') if sys.platform == 'win32' else msg
    print(f"  {GREEN}[PASS]{RESET} {msg_clean}")

class Checker:
    def __init__(self):
        self.actual = {}   # {方向: {"pdf": N, "report": N}}
        self.total_pdf = 0
        self.total_report = 0
        self._collect_actual()

    def _collect_actual(self):
        """从文件系统获取真实数字"""
        report_dir = PROJECT / "02_精读报告"
        pdf_dir = PROJECT / "01_论文原文"
        for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
            pdf_dir_d = pdf_dir / d
            reports_dir_d = report_dir / d
            pc = len(list(pdf_dir_d.glob("*.pdf"))) if pdf_dir_d.exists() else 0
            rc = len(list(reports_dir_d.glob("*_精读报告.md"))) if reports_dir_d.exists() else 0
            self.actual[d] = {"pdf": pc, "report": rc}
            self.total_pdf += pc
            self.total_report += rc

    # ────────────── 检查项 ──────────────

    def check_readme_version(self):
        """README.md 版本号"""
        readme = PROJECT / "README.md"
        if not readme.exists():
            e("README.md 不存在"); return
        text = readme.read_text("utf-8")
        m = re.search(r"版本[：:]\s*v?([\d.]+)", text)
        if m:
            v = m.group(1)
            if v == "10.5" or v == "v10.5":
                ok(f"README 版本号 = v{v}")
            else:
                e(f"README 版本号是 v{v}，应为 v10.5")
        else:
            e("README 找不到版本号")

    def check_readme_counts(self):
        """README.md 中的方向表格数字"""
        readme = PROJECT / "README.md"
        text = readme.read_text("utf-8")
        for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
            a = self.actual.get(d, {})
            p_actual = a.get("pdf", 0)
            r_actual = a.get("report", 0)
            # 模糊匹配方向行
            lines = [l for l in text.split("\n") if d[:2] in l and "|" in l]
            if not lines:
                e(f"README 中找不到 {d} 的行")
                continue
            tokens = lines[0].split("|")
            # tokens: ['', '公共管理学', ' 31 ', ' 31 ', ' check', ' -', '']
            if len(tokens) >= 5:
                p_readme = tokens[2].strip()
                r_readme = tokens[3].strip()
                if p_readme.isdigit() and int(p_readme) != p_actual:
                    e(f"README {d} PDF数={p_readme}，实际={p_actual}")
                elif r_readme.isdigit() and int(r_readme) != r_actual:
                    e(f"README {d} 精读数={r_readme}，实际={r_actual}")
                else:
                    ok(f"README {d} PDF={p_actual} 精读={r_actual}")

    def check_claude_md(self):
        """CLAUDE.md 中的 5 方向表格"""
        claude = PROJECT / "CLAUDE.md"
        if not claude.exists():
            e("CLAUDE.md 不存在"); return
        text = claude.read_text("utf-8")
        for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
            a = self.actual.get(d, {})
            p_actual = a.get("pdf", 0)
            r_actual = a.get("report", 0)
            lines = [l for l in text.split("\n") if d[:2] in l and "|" in l and "PDF" not in l]
            if not lines:
                e(f"CLAUDE.md 中找不到 {d} 的行")
                continue
            tokens = lines[0].split("|")
            if len(tokens) >= 4:
                p = tokens[1].strip()
                r = tokens[2].strip()
                if p.isdigit() and int(p) != p_actual:
                    e(f"CLAUDE.md {d} PDF数={p}，实际={p_actual}")
                elif r.isdigit() and int(r) != r_actual:
                    e(f"CLAUDE.md {d} 精读数={r}，实际={r_actual}")
                else:
                    ok(f"CLAUDE.md {d} PDF={p_actual} 精读={r_actual}")

    def check_board(self):
        """进度看板中的方向数字"""
        board = PROJECT / "14_工具脚本" / "进度看板.md"
        if not board.exists():
            e("进度看板.md 不存在"); return
        text = board.read_text("utf-8")
        for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
            a = self.actual.get(d, {})
            p_actual = a.get("pdf", 0)
            # 在进度看板中找 "PDF原文 | 数字" 模式
            section = text.split(f"## {d[:2]}")[-1] if f"## {d[:2]}" in text else ""
            section = section.split("##")[0]
            m = re.search(r"\|\s*PDF原文\s*\|\s*(\d+)", section)
            if m:
                p = int(m.group(1))
                if p != p_actual:
                    e(f"进度看板 {d} PDF数={p}，实际={p_actual}")
                else:
                    ok(f"进度看板 {d} PDF={p_actual}")
            else:
                # 可能在全局汇总表里
                pass

    def check_total_row(self):
        """总计行：总PDF = 总精读"""
        if self.total_pdf != self.total_report:
            e(f"Total PDF({self.total_pdf}) != Total Reports({self.total_report})")
        else:
            ok(f"Total PDF({self.total_pdf}) == Total Reports({self.total_report})")

    def check_all(self):
        print(f"\n{'='*50}")
        print("  推送前一致性检查")
        print(f"{'='*50}\n")
        self.check_readme_version()
        self.check_readme_counts()
        self.check_claude_md()
        self.check_board()
        self.check_total_row()
        print()
        if ERR:
            print(f"{RED}  有 {ERR} 项检查未通过，请修复后重试。{RESET}")
            print(f"  README.md / CLAUDE.md / 进度看板.md 中的数字需要与实际对齐。\n")
        else:
            print(f"{GREEN}  All passed (全部通过)\n{RESET}")
        return ERR

def install_hook():
    """将本脚本安装为 git pre-push hook"""
    hook_dir = PROJECT / ".git" / "hooks"
    hook_path = hook_dir / "pre-push"
    # 检测是否在 git 仓库中
    if not hook_dir.exists():
        print("错误：不在 git 仓库中，无法安装 hook")
        return False
    # 生成 hook 脚本
    script = f"""#!/bin/bash
# pre-push hook — 推送前自动执行一致性检查
# 由 check_push.py 自动生成
echo "=== 推送前一致性检查 ==="
python3 "{__file__}"
if [ $? -ne 0 ]; then
    echo ""
    echo "推送被拦截：请修复上述错误后重新推送。"
    echo "（如确需强制推送，使用 --no-verify 跳过）"
    exit 1
fi
exit 0
"""
    hook_path.write_text(script)
    hook_path.chmod(0o755)
    print(f"[OK] hook installed at {hook_path}")
    return True


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_hook()
        return
    checker = Checker()
    rc = checker.check_all()
    sys.exit(rc)


if __name__ == "__main__":
    main()
