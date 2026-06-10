#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

base = '02_精读报告'
out_base = '03_学术写作素材库'
from collections import defaultdict

theory_index = defaultdict(list)
for d in sorted(os.listdir(base)):
    dp = os.path.join(base, d)
    if not os.path.isdir(dp): continue
    for f in sorted(os.listdir(dp)):
        if not f.endswith('_精读报告.md'): continue
        path = os.path.join(dp, f)
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        for p in ['### 理论框架', '## 理论框架']:
            s = content.find(p)
            if s < 0: continue
            rest = content[s+len(p):]
            end = len(rest)
            for m in ['\n### 研究方法', '\n## ', '\n---\n']:
                pos = rest.find(m, 10)
                if pos > 0 and pos < end: end = pos
            theory_text = rest[:end].strip()
            if not theory_text: continue
            tm = re.search(r"title:\s*['\"](.+?)['\"]", content[:300])
            title = tm.group(1) if tm else f.replace('_精读报告.md','')
            found = re.findall(r'\*\*([^*]{2,20}?)\*\*', theory_text)
            for t in found:
                if len(t) >= 4 and ':' not in t and '\n' not in t and t.strip() not in ('：',) and len(t.strip()) >= 4:
                    theory_index[t.strip()].append((d, f.replace('.md',''), title, theory_text[:120]))
            break

lines = ['# 理论交叉索引', '', '> 从精读报告的理论框架段自动提取 | 更新: 2026-06-09', '', '全库共 ' + str(len(theory_index)) + ' 个理论概念', '']
for theory, entries in sorted(theory_index.items(), key=lambda x: -len(x[1])):
    if len(entries) < 2: continue
    dirs = set(e[0] for e in entries)
    lines.append('## ' + theory)
    lines.append('> 出现 ' + str(len(entries)) + ' 篇 | 方向: ' + '/'.join(sorted(dirs)))
    lines.append('')
    for direction, fn, title, snippet in entries:
        lines.append('- [[' + fn + '|' + title + ']]: ' + snippet)
    lines.append('')

os.makedirs(out_base + '/理论框架', exist_ok=True)
with open(out_base + '/理论框架/00_理论交叉索引.md', 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(lines) + '\n')
print('理论交叉索引: ' + str(len(theory_index)) + '个')

for direction in ['公共管理学', '社会学', '老龄化', '青少年研究', '交叉研究']:
    dp = os.path.join(base, direction)
    if not os.path.isdir(dp): continue
    abstracts = []
    theories = []
    gaps = []

    for f in sorted(os.listdir(dp)):
        if not f.endswith('_精读报告.md'): continue
        path = os.path.join(dp, f)
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()

        # frontmatter
        tm = re.search(r"title:\s*['\"](.+?)['\"]", content[:300])
        title = tm.group(1) if tm else ''
        am = re.search(r"author:\s*['\"](.+?)['\"]", content[:300])
        author = am.group(1) if am else ''

        # 核心发现
        for p in ['### 核心发现', '## 核心发现']:
            s = content.find(p)
            if s >= 0:
                rest = content[s+len(p):]
                end = len(rest)
                for m in ['\n### 关键论点', '\n## ', '\n---\n']:
                    pos = rest.find(m, 10)
                    if pos > 0 and pos < end: end = pos
                finding_text = rest[:end].strip()
                if finding_text:
                    abstracts.append((f, title, author, finding_text))
                break

        # 理论框架
        for p in ['### 理论框架', '## 理论框架']:
            s = content.find(p)
            if s >= 0:
                rest = content[s+len(p):]
                end = len(rest)
                for m in ['\n### 研究方法', '\n## ', '\n---\n']:
                    pos = rest.find(m, 10)
                    if pos > 0 and pos < end: end = pos
                theory_text = rest[:end].strip()
                if theory_text:
                    theories.append((f, title, theory_text))
                break

        # 不足与展望
        for p in ['### 不足与展望', '## 不足与展望']:
            s = content.find(p)
            if s >= 0:
                s += len(p)
                end = len(content)
                for m in ['\n## 我的思考', '\n## 标签', '\n---\n## ']:
                    pos = content.find(m, s)
                    if pos > 0 and pos < end: end = pos
                raw = content[s:end].strip()
                if raw:
                    gaps.append((f, title, raw))
                break

    # Write gaps
    if gaps:
        g_lines = ['# ' + direction + ' 研究空白', '', '> 提取自精读报告的不足与展望段 | 更新: 2026-06-09', '', str(len(gaps)) + ' 篇报告', '']
        for fn, title, raw in gaps:
            fn_clean = fn.replace('.md','')
            g_lines.append('### [[' + fn_clean + '|' + title + ']]')
            g_lines.append('')
            for line in raw.split('\n'):
                if line.strip(): g_lines.append(line)
            g_lines.append('')
        os.makedirs(out_base + '/研究空白', exist_ok=True)
        with open(out_base + '/研究空白/' + direction + '_研究空白.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(g_lines) + '\n')

    # Write abstracts
    if abstracts:
        a_lines = ['# ' + direction + ' 摘要素材', '', '> 从 ' + str(len(abstracts)) + ' 篇精读报告中提取', '']
        for fn, title, author, text in abstracts:
            fn_clean = fn.replace('.md','')
            a_lines.append('## [[' + fn_clean + '|' + title + ']]')
            if author: a_lines.append('> ' + author)
            a_lines.append('')
            points = re.split(r'\d+[.、]', text)
            for pt in points:
                pt = pt.strip()
                if pt and len(pt) > 10: a_lines.append('- ' + pt[:200])
            a_lines.append('')
        os.makedirs(out_base + '/摘要', exist_ok=True)
        with open(out_base + '/摘要/' + direction + '摘要素材.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(a_lines) + '\n')

    # Write theories
    if theories:
        t_lines = ['# ' + direction + ' 理论框架素材', '', '> 从 ' + str(len(theories)) + ' 篇精读报告中提取', '']
        for fn, title, text in theories:
            fn_clean = fn.replace('.md','')
            t_lines.append('## [[' + fn_clean + '|' + title + ']]')
            t_lines.append('')
            for line in text.split('\n'):
                if line.strip(): t_lines.append(line)
            t_lines.append('')
        with open(out_base + '/理论框架/' + direction + '理论框架素材.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(t_lines) + '\n')

    print(direction + ': 摘要=' + str(len(abstracts)) + ' 理论=' + str(len(theories)) + ' 空白=' + str(len(gaps)))

# Claims
all_claims = []
for direction in ['公共管理学', '社会学', '老龄化', '青少年研究', '交叉研究']:
    dp = os.path.join(base, direction)
    if not os.path.isdir(dp): continue
    for f in sorted(os.listdir(dp)):
        if not f.endswith('_精读报告.md'): continue
        path = os.path.join(dp, f)
        with open(path, 'r', encoding='utf-8') as fh:
            content = fh.read()
        claims = re.findall(r'>\s*[""](.+?)[""]', content)
        if claims:
            tm = re.search(r"title:\s*['\"](.+?)['\"]", content[:300])
            title = tm.group(1) if tm else f
            all_claims.append((direction, f.replace('.md',''), title, claims[:5]))

clines = ['# 跨篇关键论点汇编', '', '> 从 ' + str(len(all_claims)) + ' 篇精读报告中提取 | 按方向分组', '']
for direction in ['公共管理学', '社会学', '老龄化', '青少年研究', '交叉研究']:
    dc = [(f, t, c) for d, f, t, c in all_claims if d == direction]
    if not dc: continue
    clines.append('## ' + direction + '（' + str(len(dc)) + '篇）')
    clines.append('')
    for f, title, claims in dc:
        clines.append('### [[' + f + '|' + title + ']]')
        for c in claims:
            clines.append('- ' + c[:100])
        clines.append('')
os.makedirs(out_base + '/关键论点', exist_ok=True)
with open(out_base + '/关键论点/跨篇关键论点汇编.md', 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(clines) + '\n')
print('关键论点汇编: ' + str(len(all_claims)) + '篇')
print('=== 全部重新生成完成 ===')
