#!/c/Users/Administrator/AppData/Local/Programs/Python/Python311 python
"""手动存入PDF的监控器 — 自动触发精读→沉淀→日报"""

import sys, os, time, re, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

KNOWLEDGE = Path("D:/公共管理科研")
PDF_DIR = KNOWLEDGE / "01_论文原文"
REPORT_DIR = KNOWLEDGE / "02_精读报告"
SCRIPT_REGEN = str(KNOWLEDGE / "14_工具脚本/提取/regenerate_all.py")
SCRIPT_DAILY = str(KNOWLEDGE / "14_工具脚本/报告/daily_weekly_monthly.py")

# 记录已处理的文件，避免重复触发
processed = set()

def trigger_pipeline():
    """新增精读报告后触发的后续流程"""
    print("\n=== 触发跨篇沉淀 ===")
    subprocess.run([sys.executable, SCRIPT_REGEN], cwd=str(KNOWLEDGE))
    print("\n=== 触发日报更新 ===")
    subprocess.run([sys.executable, SCRIPT_DAILY, "daily"], cwd=str(KNOWLEDGE))
    print("\n=== 全部完成 ===")

class PdfHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            self.handle_pdf(event.src_path)
    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            self.handle_pdf(event.src_path)

    def handle_pdf(self, pdf_path):
        if pdf_path in processed:
            return
        processed.add(pdf_path)
        fname = os.path.basename(pdf_path)
        print(f"\n📄 检测到新PDF: {fname}")

        # 判断方向
        from base import detect_area
        area = detect_area(fname)
        print(f"   方向: {area}")

        # 检查是否已有精读报告
        area_dir = REPORT_DIR / area
        area_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(pdf_path).stem
        if stem.endswith(".pdf"):
            stem = stem[:-4]
        report_path = area_dir / (stem + "_精读报告.md")
        if report_path.exists():
            print("   精读报告已存在，跳过")
            return

        # 提取PDF文本
        text = ""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            text = "".join(page.get_text() for page in doc)
            doc.close()
            print(f"   已提取文本: {len(text)}字符")
        except:
            print("   ⚠️ 扫描版PDF，将标记为待OCR")

        # 自动生成精读报告初稿
        print("   🔄 正在生成精读报告初稿...")

        # 从文件名推断元数据
        year = ""
        author = ""
        base_name = Path(pdf_path).stem
        parts = base_name.split("_")
        if parts and parts[0].isdigit() and len(parts[0]) == 4:
            year = parts[0]
            author = parts[1] if len(parts) > 1 else ""

        title = base_name
        first_para = text[:500].replace('\n', ' ') if text else "（PDF文本不可用）"

        report_lines = [
            '---',
            f"title: '{title}'",
            "tags:",
            "  - literature-note",
            "  - reading-note",
            f"created: '{datetime.now().strftime('%Y-%m-%d')}'",
            f"author: '{author}'",
            f"year: '{year}'" if year else "year: ''",
            "journal: ''",
            "cssci: false",
            "score: '0'",
            f"theme: '（待补充）'",
            f"study_area: '（待补充）'",
            f"data_source: '（待补充）'",
            f"methodology: '（待补充）'",
            f"key_finding: '（待补充）'",
            f"relevance: '（待补充）'",
            '---',
            '',
            '# 精读分析报告（AI初稿）',
            '',
            '> ⚠️ 本文由AI自动生成初稿，请人工补充完整后再确认',
            '',
            '## 论文信息',
            '',
            '| 字段 | 内容 |',
            '|------|------|',
            f'| **标题** | {title} |',
            f'| **作者** | {author} |',
            f'| **年份** | {year} |',
            '| **入库路径** | `' + str(pdf_path) + '` |',
            '',
            '---',
            '',
            '## 研究概述',
            '',
            '### 一句话定位',
            '> （待补充）',
            '',
            '### 核心内容',
            '',
            first_para[:1000],
            '',
            '---',
            '',
            '## 质量评分（7 维）',
            '',
            '| 维度 | 评分(1-5) | 理由 |',
            '|------|:---------:|------|',
            '| 研究问题质量 | | （待补充） |',
            '| 理论框架 | | （待补充） |',
            '| 研究设计 | | （待补充） |',
            '| 实证证据 | | （待补充） |',
            '| 分析深度 | | （待补充） |',
            '| 写作质量 | | （待补充） |',
            '| 创新性 | | （待补充） |',
            '| **总分** | **/5** | |',
            '',
            '---',
            '',
            '## 内容拆解',
            '',
            '### 核心发现',
            '（待补充）',
            '',
            '### 关键论点',
            '（待补充）',
            '',
            '### 创新贡献',
            '（待补充）',
            '',
            '### 不足与展望',
            '（待补充）',
            '',
            '---',
            '',
            '## 我的思考',
            '',
            '### 最有启发的点',
            '（待补充）',
            '',
            '### 可借鉴之处',
            '（待补充）',
            '',
            '### 待验证/存疑点',
            '（待补充）',
            '',
            '### 与我的研究关联',
            '（待补充）',
            '',
            '---',
            '',
            '## 标签',
            '',
            '| 维度 | 标签 |',
            '|------|------|',
            '| 主标签 | （待补充） |',
            '| 方法标签 | （待补充） |',
            '',
            '## 元信息',
            '',
            '| 字段 | 内容 |',
            '|------|------|',
            f"| 分析日期 | {datetime.now().strftime('%Y-%m-%d')} |",
            '| 分析者 | AI初稿（待人工审核） |',
            '| 工作流版本 | v10 |',
        ]

        with open(str(report_path), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(report_lines) + '\n')
        print(f"   ✅ 精读报告初稿已生成: {report_path.relative_to(KNOWLEDGE)}")
        print(f"   ⚠️ 请用 analysis_template.md 模板补充7维评分和我的思考")
        print(f"   ⚠️ 完成后精读报告会自动触发沉淀+日报更新")

        # 触发后续流程
        trigger_pipeline()


class ReportHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith("_精读报告.md"):
            self.handle_report(event.src_path)
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("_精读报告.md"):
            self.handle_report(event.src_path)

    def handle_report(self, report_path):
        if report_path in processed:
            return
        processed.add(report_path)
        print(f"\n📝 检测到新精读报告: {os.path.basename(report_path)}")
        trigger_pipeline()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="论文监控器 — 自动处理新PDF和精读报告")
    parser.add_argument("--daemon", action="store_true", help="后台持续监控")
    args = parser.parse_args()

    # 立即检查已有未触发的精读报告
    print("=== 检查未触发的精读报告 ===")
    for d in sorted(os.listdir(str(REPORT_DIR))):
        dp = REPORT_DIR / d
        if not dp.is_dir(): continue
        for f in dp.glob("*_精读报告.md"):
            report_mtime = f.stat().st_mtime
            regen_mtime = 0
            gap_file = KNOWLEDGE / "03_学术写作素材库/研究空白" / f"{d}_研究空白.md"
            if gap_file.exists():
                regen_mtime = gap_file.stat().st_mtime
            if report_mtime > regen_mtime + 60:
                print(f"  ⏳ 精读报告 {f.name} 未触发沉淀")
                trigger_pipeline()
                return

    if args.daemon:
        print("\n=== 启动监控 (Ctrl+C 停止) ===")
        observer = Observer()
        observer.schedule(PdfHandler(), str(PDF_DIR), recursive=True)
        observer.schedule(ReportHandler(), str(REPORT_DIR), recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        print("\n使用 --daemon 启动后台监控，或手动运行 pipeline")

if __name__ == "__main__":
    main()
