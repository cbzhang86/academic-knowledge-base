#!/usr/bin/env python3
"""PDF文件名学术标准化 — 统一为 年份_作者_原标题.pdf

策略:
  - 标题永远用原始文件名（原文就已正确）
  - 年份和作者从 PDF 提取，但作者提取不可靠时跳过
  - 已符合格式的跳过

用法:
    python standardize_filenames.py scan           # 预览
    python standardize_filenames.py fix            # 执行
    python standardize_filenames.py fix --dry-run  # 试运行
"""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# ── 项目根 ──────────────────────────────────────────────
_ENV_ROOT = os.environ.get("KNOWLEDGE_ROOT")
if _ENV_ROOT:
    PROJECT_ROOT = Path(_ENV_ROOT).resolve()
else:
    _cwd = Path.cwd().resolve()
    for _parent in [_cwd] + list(_cwd.parents):
        if (_parent / "config" / "structure.yaml").exists():
            PROJECT_ROOT = _parent
            break
    else:
        PROJECT_ROOT = _cwd

sys.path.insert(0, str(PROJECT_ROOT))
try:
    from global_config import DIRS
    PDF_DIR = DIRS["01_raw"]
except ImportError:
    PDF_DIR = PROJECT_ROOT / "01_论文原文"

import fitz

# ── arXiv ID → 标题的映射（测试时下载的已知） ──
_ARXIV_MAP = {
    "2108.09960": "The_Moderating_Effect_of_Gender_on_Adopting_Digital_Government_Services",
    "2108.09783": "From_Digital_Divide_to_Digital_Justice_in_the_Global_South",
}


def is_standard(stem: str) -> bool:
    """检查是否已是 年份_[作者_]标题 格式"""
    # arXiv_YYYY 前缀已识别
    if re.match(r'^\d{4}_arXiv_\d', stem):
        return True
    # 以年份开头 → 已标准（无论第二段是什么）
    if re.match(r'^\d{4}_', stem):
        return True
    return False


def extract_data(text: str, meta: dict) -> dict:
    """从 PDF 第一页提取年份和作者"""
    result = {"year": None, "author": None}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # ═══ 年份 ═══
    # arXiv
    m = re.search(r'arXiv:(\d{2})\d{2}\.\d+', text)
    if m:
        pre = m.group(1)
        result["year"] = f"20{pre}" if int(pre) <= 30 else f"19{pre}"
    # 中文期刊 "2026年第"
    if not result["year"]:
        m = re.search(r'(\d{4})\s*年\s*(第|\()', text)
        if m: result["year"] = m.group(1)
    # 元数据
    if not result["year"] and meta.get("creationDate"):
        m = re.search(r'D:(\d{4})', meta["creationDate"])
        if m: result["year"] = m.group(1)
    # 前几行找 20xx
    if not result["year"]:
        for l in lines[:8]:
            if re.search(r'\b(20\d{2})\b', l) and not re.search(r'arXiv', l):
                result["year"] = re.search(r'(20\d{2})', l).group(1)
                break

    # ═══ 作者 ═══
    # 策略1：中文 "作者名[数字]" 或 "作者名；作者名[数字]"
    for l in lines[:25]:
        m = re.search(r'^([一-鿿]{2,4})[；;]\s*([一-鿿]{2,4})[（(（(]?\d', l)
        if m and len(l) < 60:
            result["author"] = m.group(1)
            break
        m = re.search(r'^([一-鿿]{2,4})[[（(（(]\d', l)
        if m and len(l) < 60:
            result["author"] = m.group(1)
            break

    # 策略2：英文 "John Gastil" 等
    if not result["author"]:
        for l in lines[:15]:
            if re.match(r'arXiv:', l):
                continue
            m = re.match(r'^([A-Z][a-zéë]+)\s+([A-Z][a-zéë.,\' ]+)$', l.strip('* '))
            if m and len(l) < 60 and not re.search(r'\b(Abstract|Department|University|Institute|Research|Laboratory|School|College)\b', l):
                name = l.split(',')[0].split(' and ')[0].strip()
                name = re.sub(r'\s*\d.*', '', name).strip()
                parts = name.split()
                if len(parts) >= 2:
                    result["author"] = parts[-1].rstrip('.,; ')
                break

    # 策略3：中文 "作者简介" 后的第一个名字
    if not result["author"]:
        for l in lines:
            if '作者简介' in l:
                m = re.search(r'作者简介[：:]\s*([一-鿿]{2,4})', l)
                if m:
                    result["author"] = m.group(1)
                    break

    # 策略4："作者名　作者名" 两个中文名全角空格
    if not result["author"]:
        for l in lines[:15]:
            pair = re.match(r'^([一-鿿]{2,4})[　 ]+([一-鿿]{2,4})$', l)
            if pair and len(l) < 25:
                result["author"] = pair.group(1)
                break

    # 策略5：引文格式中的第一作者
    if not result["author"]:
        for l in lines:
            m = re.search(r'引文格式[：:].*?([一-鿿]{2,4})[，,]\s*([一-鿿]{2,4})\.', l)
            if m:
                result["author"] = m.group(1)
                break

    # 策略6：单独一行 2-4 字中文，紧跟在标题后
    if not result["author"]:
        title = None
        for l in lines[:10]:
            cn = sum(1 for c in l if '一' <= c <= '鿿')
            if cn > 8 and len(l) > 10:
                title = l
                break
        if title and title in lines:
            idx = lines.index(title)
            for l in lines[idx+1:idx+5]:
                m = re.match(r'^([一-鿿]{2,4})$', l)
                if m:
                    result["author"] = m.group(1)
                    break

    return result


def build_new_name(f: Path):
    """生成新文件名，返回 (old_path, new_name) 或 None"""
    stem = f.stem
    orig_name = f.name

    # 清理 _page 后缀
    stem_clean = re.sub(r'_page$', '', stem, flags=re.IGNORECASE)

    # 跳过已标准的
    if is_standard(stem_clean):
        if stem_clean + ".pdf" != orig_name:
            return (f, stem_clean + ".pdf")
        return None

    # 打开 PDF
    try:
        doc = fitz.open(str(f))
        text = doc[0].get_text()
        meta = doc.metadata or {}
        doc.close()
    except Exception:
        text, meta = "", {}

    data = extract_data(text, meta)

    # 构建文件名
    title = stem_clean

    # arXiv：标题用提取的或映射表
    if re.match(r'^\d+\.\d+', stem_clean):
        arxiv_id = re.match(r'^(\d+\.\d+)', stem_clean).group(1)
        if arxiv_id in _ARXIV_MAP:
            title = _ARXIV_MAP[arxiv_id]
        else:
            # 从 PDF 文本提取
            for l in text.split('\n'):
                if len(l.strip()) > 20 and not re.match(r'^[\d\s\-:\wXiv.]+$', l.strip()):
                    title = l.strip()
                    break

    parts = []
    if data["year"]:
        parts.append(data["year"])
    if data["author"]:
        parts.append(data["author"])
    if title:
        # 安全化（仅标题部分，不砍字太多）
        safe = re.sub(r'[\\/:*?"<>|]', '_', title)
        safe = re.sub(r'\s+', '_', safe).strip('_. ')
        if len(safe) > 80:
            # 按词截断
            safe = safe[:80].rstrip('_-. ')
            last_u = safe.rfind('_')
            if last_u > 50:
                safe = safe[:last_u]
        parts.append(safe)

    if not parts:
        return None

    new_name = "_".join(parts) + ".pdf"
    if new_name == orig_name:
        return None

    return (f, new_name)


def cmd_scan():
    changes = [r for f in sorted(PDF_DIR.rglob("*.pdf")) if (r := build_new_name(f))]
    if not changes:
        print("✅ 所有文件名已符合标准")
        return
    print(f"需修改 {len(changes)} 个文件:\n")
    for old, new in changes:
        print(f"  [{old.parent.name}]")
        print(f"    原: {old.name}")
        print(f"    新: {new}")
        print()


def cmd_fix(dry_run=False):
    changes = [r for f in sorted(PDF_DIR.rglob("*.pdf")) if (r := build_new_name(f))]
    if not changes:
        print("✅ 所有文件名已符合标准")
        return

    ok, errs = 0, []
    for old, new_name in changes:
        new_path = old.parent / new_name
        if new_path.exists():
            c = 1
            while new_path.exists():
                new_path = old.parent / f"{new_path.stem}_{c}.pdf"
                c += 1
        if dry_run:
            print(f"  [{old.parent.name}] {old.name} → {new_path.name}")
            continue
        try:
            old.rename(new_path)
            ok += 1
            print(f"  ✅ {old.parent.name}/ {old.name}")
            print(f"     → {new_path.name}")
        except Exception as e:
            errs.append((old.name, str(e)))
            print(f"  ❌ {old.name}: {e}")

    if dry_run:
        print(f"\n试运行完成，将修改 {len(changes)} 个文件")
    else:
        print(f"\n改名 {ok} 个" + (f"，失败 {len(errs)} 个" if errs else ""))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PDF文件名学术标准化")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("scan", help="扫描预览")
    p_fix = sub.add_parser("fix", help="执行改名")
    p_fix.add_argument("--dry-run", action="store_true", help="试运行")

    args = parser.parse_args()
    if args.cmd == "scan":
        cmd_scan()
    elif args.cmd == "fix":
        cmd_fix(dry_run=args.dry_run)
    else:
        parser.print_help()
