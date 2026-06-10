#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
"""一键同步到 Obsidian Vault — 项目目录 → ObsidianVault"""

import sys, os, shutil
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

PROJECT = Path("D:/公共管理科研")
VAULT = PROJECT / "ObsidianVault"

def sync(src_rel, dst_rel=None):
    """同步文件或目录，src_rel 相对项目根，dst_rel 相对 ObsidianVault"""
    src = PROJECT / src_rel
    dst = VAULT / (dst_rel or src_rel)
    if not src.exists():
        print(f"  ⚠️ 源不存在: {src_rel}")
        return False
    try:
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(dst.parent, exist_ok=True)
            shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"  ❌ {src_rel}: {e}")
        return False

print("=== 同步到 Obsidian Vault ===")
print()

count = 0

# 1. 精读报告
print("[01_论文精读]")
for d in ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]:
    if sync(f"02_精读报告/{d}", f"01_论文精读/{d}"):
        count += 1
        print(f"  ✅ {d}")

# 2. 写作素材
print("\n[03_写作素材]")
if sync("03_学术写作素材库", "03_写作素材"):
    print("  ✅ 全部素材")
    count += 1

# 3. 研究方法
print("\n[04_研究方法]")
if sync("04_研究方法", "04_研究方法"):
    print("  ✅ 全部方法笔记")
    count += 1

# 4. 报告
print("\n[05_报告]")
for sub in ["日报", "周报", "月报"]:
    if sync(f"05_报告/{sub}", f"05_报告/{sub}"):
        count += 1
        print(f"  ✅ {sub}")

# 5. 研究输出
print("\n[10_研究输出]")
for sub in ["原料包", "ars_output", "定稿"]:
    p = f"10_研究输出/{sub}"
    if (PROJECT / p).exists() and (PROJECT / p).is_dir():
        if sync(p, p):
            count += 1
            print(f"  ✅ {sub}")

# 6. 工具文档
print("\n[14_工具脚本]")
for f in ["进度看板.md", "检索日志.md"]:
    if sync(f"14_工具脚本/{f}", f"14_工具脚本/{f}"):
        print(f"  ✅ {f}")
        count += 1

# 7. CLAUDE.md + README.md
print("\n[根目录文档]")
for f in ["CLAUDE.md", "README.md"]:
    if sync(f, f):
        print(f"  ✅ {f}")
        count += 1

# 8. 研究启动器脚本
print("\n[脚本同步]")
if sync("14_工具脚本/报告/research_starter.py", "14_工具脚本/报告/research_starter.py"):
    print("  ✅ research_starter.py")
    count += 1

print(f"\n=== 同步完成: {count} 项 ===")
