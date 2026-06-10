#!/usr/bin/env python3
"""
review/watcher.py v1（过渡版）
手动存入PDF的监控器 — 自动触发精读→沉淀→日报

功能同 manual_watch.py，但路径从 DIRS 读取，不再硬编码。
调用方式不变（subprocess 调旧脚本），Phase 4 再升级为调标准化 CLI。

用法：
    python review/watcher.py --daemon          # 后台持续监控
    python review/watcher.py --once            # 单次扫描（不驻留）
    python review/watcher.py --stop            # 停止后台进程
"""

import sys, os, time, re, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from datetime import datetime

try:
    from _config import PROJECT_ROOT, DIRS
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from global_config import PROJECT_ROOT, DIRS

# 导入 watchdog（延迟导入，仅在 daemon 模式需要）
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

PDF_DIR = DIRS["01_raw"]
REPORT_DIR = DIRS["02_reports"]
SCRIPT_REGEN = str(DIRS["14_tools"] / "提取/regenerate_all.py")
SCRIPT_DAILY = str(DIRS["14_tools"] / "报告/daily_weekly_monthly.py")

PID_FILE = PROJECT_ROOT / "config" / "watcher.pid"

# 记录已处理的文件，避免重复触发
processed = set()


def trigger_pipeline():
    """新增精读报告后触发的后续流程"""
    print("\n=== 触发跨篇沉淀 ===")
    subprocess.run([sys.executable, SCRIPT_REGEN], cwd=str(PROJECT_ROOT))
    print("\n=== 触发日报更新 ===")
    subprocess.run([sys.executable, SCRIPT_DAILY, "daily"], cwd=str(PROJECT_ROOT))
    print("\n=== 全部完成 ===")


def generate_draft_report(pdf_path: str, area: str, report_path: Path):
    """从 PDF 自动生成精读报告初稿（v10 模板，内容标（待补充））"""
    fname = os.path.basename(pdf_path)
    print(f"\n📄 检测到新PDF: {fname}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        print(f"   精读报告已存在，跳过")
        return

    # 提取PDF文本
    text = ""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        print(f"   已提取文本: {len(text)}字符")
    except ImportError:
        print("   ⚠️ 未安装 PyMuPDF，无法提取文本")
    except Exception:
        print("   ⚠️ 扫描版PDF，将标记为待OCR")

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
    print(f"   ✅ 精读报告初稿已生成: {report_path.name}")
    print(f"   ⚠️ 请用 analysis_template.md 模板补充7维评分和我的思考")


def scan_new_pdfs():
    """扫描所有方向的新 PDF，生成精读报告初稿"""
    count = 0
    for area_dir in sorted(PDF_DIR.iterdir()):
        if not area_dir.is_dir():
            continue
        area = area_dir.name
        for pdf_path in sorted(area_dir.glob("*.pdf")):
            fname = pdf_path.name
            if fname in processed:
                continue
            processed.add(fname)

            stem = pdf_path.stem
            report_path = REPORT_DIR / area / (stem + "_精读报告.md")
            if report_path.exists():
                continue

            generate_draft_report(str(pdf_path), area, report_path)
            count += 1
    return count


def scan_new_reports():
    """扫描是否有新增的精读报告需要触发沉淀+日报"""
    for area_dir in sorted(REPORT_DIR.iterdir()):
        if not area_dir.is_dir():
            continue
        area = area_dir.name
        for f in sorted(area_dir.glob("*_精读报告.md")):
            fname = f.name
            if fname in processed:
                continue
            processed.add(fname)

            # 检查是否已有对应的素材文件（判断是否已触发过）
            gap_dir = DIRS["03_materials"] / "研究空白"
            gap_file = gap_dir / f"{area}_研究空白.md"
            if gap_file.exists():
                # 如果精读报告比素材新超过60秒，说明是新增
                if f.stat().st_mtime > gap_file.stat().st_mtime + 60:
                    print(f"📝 检测到新精读报告: {fname}")
                    trigger_pipeline()
                    return True
            else:
                # 素材还不存在，肯定是新增
                print(f"📝 检测到精读报告（尚未沉淀）: {fname}")
                trigger_pipeline()
                return True
    return False


def write_pid():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def read_pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None
    return None


def stop_watcher():
    pid = read_pid()
    if pid:
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            print(f"[WATCHER] 停止进程 {pid}")
            PID_FILE.unlink(missing_ok=True)
        except ProcessLookupError:
            print("[WATCHER] 进程不存在，清理 PID 文件")
            PID_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"[WATCHER] 停止失败: {e}")
    else:
        print("[WATCHER] 没有运行中的监控进程")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="论文监控器 — 自动处理新PDF和精读报告")
    parser.add_argument("--daemon", action="store_true", help="后台持续监控")
    parser.add_argument("--once", action="store_true", help="单次扫描")
    parser.add_argument("--stop", action="store_true", help="停止后台进程")
    args = parser.parse_args()

    if args.stop:
        stop_watcher()
        return

    if args.daemon:
        if not HAS_WATCHDOG:
            print("[ERROR] --daemon 模式需要安装 watchdog: pip install watchdog")
            sys.exit(1)

        # 先扫描已有的
        print("=== 检查未触发的精读报告 ===")
        scan_new_reports()

        print("\n=== 启动监控 (Ctrl+C 停止) ===")
        write_pid()
        observer = Observer()

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
                try:
                    from base import detect_area
                except ImportError:
                    detect_area = lambda fname: "交叉研究"
                fname = os.path.basename(pdf_path)
                area = detect_area(fname)
                stem = Path(pdf_path).stem
                report_path = REPORT_DIR / area / (stem + "_精读报告.md")
                generate_draft_report(pdf_path, area, report_path)

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
                trigger_pipeline()

        observer.schedule(PdfHandler(), str(PDF_DIR), recursive=True)
        observer.schedule(ReportHandler(), str(REPORT_DIR), recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        if PID_FILE.exists():
            PID_FILE.unlink()

    elif args.once:
        print("=== 单次扫描 ===")
        n = scan_new_pdfs()
        if n > 0:
            print(f"  生成了 {n} 篇精读报告初稿")
        scan_new_reports()
        print("=== 扫描完成 ===")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
