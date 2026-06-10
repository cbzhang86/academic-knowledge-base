#!/usr/bin/env python3
"""批量更新精读报告中的入库路径，从旧文件名指向新标准化文件名

用法:
    python fix_report_paths.py scan         # 预览需修复的报告
    python fix_report_paths.py fix          # 执行修复
"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

_ENV_ROOT = None
import os
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
    REPORT_DIR = DIRS["02_reports"]
    PDF_DIR = DIRS["01_raw"]
except ImportError:
    REPORT_DIR = PROJECT_ROOT / "02_精读报告"
    PDF_DIR = PROJECT_ROOT / "01_论文原文"

import fitz


def extract_pdf_title(pdf_path: Path) -> str:
    """从 PDF 第一页提取论文标题（用于确认匹配正确）"""
    try:
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text()[:500]
        doc.close()
        for l in text.split('\n'):
            l = l.strip()
            if len(l) > 20 and not re.match(r'^[\d\s\-:arxivXiv.科技文献]+$', l):
                return l[:60]
    except:
        pass
    return None


def find_pdf_by_old_ref(ref: str) -> Path:
    """根据旧文件引用的部分文件名模糊匹配实际PDF"""
    # 去掉目录前缀和扩展名
    fname = ref.replace('\\', '/').split('/')[-1]
    stem = Path(fname).stem

    # 去掉年份和作者前缀（如果是标准格式）
    search_key = stem.lower()[:30]

    # 模糊匹配（同时匹配文件名和去掉特殊字符后的版本）
    for f in sorted(PDF_DIR.rglob('*.pdf')):
        if search_key in f.stem.lower():
            return f
    # 第二次尝试：去掉特殊字符再匹配
    clean_key = re.sub(r'[“”‘’"\'：，–—]', '', search_key)
    if clean_key != search_key:
        for f in sorted(PDF_DIR.rglob('*.pdf')):
            f_clean = re.sub(r'[“”‘’"\'：，–—]', '', f.stem.lower())
            if clean_key in f_clean:
                return f
    return None


def fix_report_file(report_path: Path):
    """修复单个精读报告中的入库路径"""
    text = report_path.read_text(encoding='utf-8')
    original = text
    changes = []

    # 找所有入库路径行
    pattern = r'(入库路径.*?`)(01_论文原文[^`]+\.pdf)(`)'
    for m in re.finditer(pattern, text):
        old_ref = m.group(2)
        old_fname = old_ref.replace('\\', '/').split('/')[-1]
        old_stem = Path(old_fname).stem

        # 检查实际文件是否存在
        actual = list(PDF_DIR.rglob(old_fname))
        if actual:
            continue  # 路径正确，跳过

        # 模糊匹配
        pdf = find_pdf_by_old_ref(old_ref)
        if pdf:
            new_ref = str(pdf.relative_to(PROJECT_ROOT)).replace('\\', '/')
            text = text.replace(f'`{old_ref}`', f'`{new_ref}`')
            changes.append((old_fname, new_ref))
        else:
            changes.append((old_fname, f'未找到: {old_stem[:30]}'))

    if original != text:
        report_path.write_text(text, encoding='utf-8')
    return changes


def cmd_scan():
    """扫描所有需修复的报告"""
    total_issues = 0
    for area_dir in sorted(REPORT_DIR.iterdir()):
        if not area_dir.is_dir(): continue
        for f in sorted(area_dir.glob('*.md')):
            if f.name == '00_精读索引.md': continue
            text = f.read_text(encoding='utf-8')
            for m in re.finditer(r'入库路径.*?`(01_论文原文[^`]+\.pdf)`', text):
                old_ref = m.group(1)
                fname = old_ref.replace('\\', '/').split('/')[-1]
                actual = list(PDF_DIR.rglob(fname))
                if not actual:
                    total_issues += 1
                    print(f'  [{area_dir.name}] {f.stem[:40]}')
                    print(f'    引用: {fname}')
                    find = find_pdf_by_old_ref(old_ref)
                    if find:
                        print(f'    修正: {find.relative_to(PDF_DIR)}')
                    else:
                        print(f'    无匹配')
                    print()
    if total_issues == 0:
        print('✅ 所有入库路径正确')
    else:
        print(f'共 {total_issues} 处需修复')


def cmd_fix():
    """执行修复"""
    total = 0
    fixed = 0
    for area_dir in sorted(REPORT_DIR.iterdir()):
        if not area_dir.is_dir(): continue
        for f in sorted(area_dir.glob('*.md')):
            if f.name == '00_精读索引.md': continue
            changes = fix_report_file(f)
            if changes:
                total += len(changes)
                for old, new in changes:
                    status = '✅' if '未找到' not in new else '❌'
                    print(f'  {status} {f.parent.name}/{f.stem[:40]}')
                    print(f'    旧: {old}')
                    print(f'    新: {new}')
                    print()
                    if '未找到' not in new:
                        fixed += 1
    print(f'\n修复: {fixed}/{total}')


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')
    sub.add_parser('scan', help='扫描需修复的报告')
    sub.add_parser('fix', help='执行修复')

    args = parser.parse_args()
    if args.cmd == 'scan':
        cmd_scan()
    elif args.cmd == 'fix':
        cmd_fix()
    else:
        parser.print_help()
