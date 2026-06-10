#!/usr/bin/env python3
"""filesystem 归档后端 — 默认，零依赖。

特性：
- 对于已在 01_raw/ 下的 PDF：no-op（不做复制），只触发 dedup register
- 对于不在 01_raw/ 下的 PDF：复制到 01_raw/{direction}/
- 不依赖任何外部软件
"""

import sys, os, shutil
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from .. import ArchiveBackend


class FilesystemBackend(ArchiveBackend):
    """纯文件系统归档后端。"""

    def _do_archive(self, pdf_path: Path, paper_info: dict) -> dict:
        dirs = {}
        try:
            from global_config import DIRS
            dirs = DIRS
        except ImportError:
            pass

        raw_dir = dirs.get("01_raw") if dirs else (self.project_root / "01_raw")
        direction = paper_info.get("direction", "交叉研究")
        target_dir = raw_dir / direction if raw_dir else self.project_root / direction
        target_path = target_dir / pdf_path.name

        # 检查是否已在 01_raw/ 下
        if raw_dir and raw_dir in pdf_path.parents:
            # 已在目标位置，no-op
            rel = pdf_path.relative_to(raw_dir) if raw_dir else pdf_path.name
            return {
                "status": "ok",
                "message": f"已在 01_raw/ 下: {rel}",
                "dest": str(pdf_path),
            }

        # 不在 01_raw/ 下，需要复制
        target_dir.mkdir(parents=True, exist_ok=True)

        # 检查是否重复（同名文件已存在）
        if target_path.exists():
            if target_path.stat().st_size == pdf_path.stat().st_size:
                return {
                    "status": "skipped",
                    "message": f"目标文件已存在且大小一致: {target_path.name}",
                    "dest": str(target_path),
                }

        shutil.copy2(str(pdf_path), str(target_path))
        return {
            "status": "ok",
            "message": f"已复制到 {direction}/: {pdf_path.name}",
            "dest": str(target_path),
        }

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        """filesystem 总是可用。"""
        return True
