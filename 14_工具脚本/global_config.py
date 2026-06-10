#!/usr/bin/env python3
"""单一全局配置 — 所有脚本从此获取路径和配置。

使用方式：
    from global_config import DIRS, AREAS, CONFIG

    # 路径引用
    pdf_dir = DIRS["01_raw"]
    reports_dir = DIRS["02_reports"]

    # 方向名
    for area in AREAS:
        print(area)

路径检测优先级：KNOWLEDGE_ROOT 环境变量 > CWD 检测
"""
import os, sys, json
from pathlib import Path

# ── 项目根检测 ──────────────────────────────────────────
_ENV_ROOT = os.environ.get("KNOWLEDGE_ROOT")
if _ENV_ROOT:
    PROJECT_ROOT = Path(_ENV_ROOT).resolve()
else:
    # 自动检测：从 CWD 向上找，找到包含 config/structure.yaml 的目录
    _cwd = Path.cwd().resolve()
    for _parent in [_cwd] + list(_cwd.parents):
        if (_parent / "config" / "structure.yaml").exists():
            PROJECT_ROOT = _parent
            break
    else:
        PROJECT_ROOT = _cwd  # fallback

sys.path.insert(0, str(PROJECT_ROOT))

# ── 加载 YAML 配置 ──────────────────────────────────────
try:
    import yaml
except ImportError:
    yaml = None

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    if yaml:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # fallback: 无 PyYAML 时用简单 JSON（仅支持部分场景）
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}

# ── 加载各配置项 ───────────────────────────────────────
STRUCTURE = _load_yaml(PROJECT_ROOT / "config" / "structure.yaml")
AREAS_CFG = _load_yaml(PROJECT_ROOT / "config" / "areas.yaml")
METADATA_CFG = _load_yaml(PROJECT_ROOT / "config" / "metadata.yaml")
SOURCES_CFG = _load_yaml(PROJECT_ROOT / "config" / "sources.yaml")
TEMPLATE_CFG = _load_yaml(PROJECT_ROOT / "config" / "template.yaml")

# ── 目录映射 ────────────────────────────────────────────
# 从 structure.yaml 读取，如未配置则用默认中文名
_DEFAULT_DIRS = {
    "01_raw": "01_论文原文",
    "02_reports": "02_精读报告",
    "03_materials": "03_学术写作素材库",
    "04_methods": "04_研究方法",
    "05_reports": "05_报告",
    "10_output": "10_研究输出",
    "skills": "14_工具脚本",
    "obsidian_vault": "ObsidianVault",
    "archive": "99_归档",
    "temp": "00_临时工作区",
}

_dir_config = STRUCTURE.get("directories", {})
DIR_MAP = {k: _dir_config.get(k, _DEFAULT_DIRS[k]) for k in _DEFAULT_DIRS}
DIRS = {k: PROJECT_ROOT / v for k, v in DIR_MAP.items()}

# ── 研究方向名 ──────────────────────────────────────────
_area_names = STRUCTURE.get("area_names", {})
_AREA_DEFAULT = ["公共管理学", "社会学", "老龄化", "青少年研究", "交叉研究"]
AREAS = list(_area_names.values()) if _area_names else _AREA_DEFAULT

# ── 归档后端 ────────────────────────────────────────────
METADATA_BACKEND = METADATA_CFG.get("backend", "filesystem")

# ── Zotero DB 路径（仅 Zotero 后端使用） ────────────────
ZOTERO_DB = METADATA_CFG.get("zotero", {}).get(
    "db_path",
    os.path.expanduser("~/Zotero/zotero.sqlite")
)
ZOTERO_DB = Path(ZOTERO_DB)

# ── 采集源配置 ─────────────────────────────────────────
SOURCES = SOURCES_CFG.get("sources", {})

# ── Edge CDP 配置 ──────────────────────────────────────
EDGE_CDP = SOURCES.get("ncpssd", {}).get("cdp_url", "http://127.0.0.1:9222")


def init_config(backend: str = None, non_interactive: bool = False):
    """首次初始化：交互选后端 → 写 config/metadata.yaml → dedup rebuild

    使用场景：
        python global_config.py init                       # 交互式
        python global_config.py init --backend filesystem   # 非交互
        METADATA_BACKEND=zotero python global_config.py init --non-interactive

    !!! 此函数仅在首次配置缺失时调用，不阻塞常规使用。
    """
    meta_path = PROJECT_ROOT / "config" / "metadata.yaml"
    if meta_path.exists():
        print("[CONFIG] 配置已存在，无需初始化")
        return

    # 非交互模式：通过参数或环境变量
    env_backend = os.environ.get("METADATA_BACKEND", "").strip().lower()
    final_backend = backend or env_backend or ""

    if non_interactive or not sys.stdin.isatty():
        if not final_backend:
            print("[INIT] 非交互模式但未指定后端。使用默认: filesystem", file=sys.stderr)
            final_backend = "filesystem"
        _write_metadata(meta_path, final_backend)
        _rebuild_dedup()
        return

    # 交互模式
    print("\n检测到可用的归档后端：")
    backends = []
    if _detect_filesystem():
        backends.append(("filesystem", "纯文件系统（默认，零依赖）"))
    if _detect_zotero():
        backends.append(("zotero", f"Zotero（检测到 {ZOTERO_DB}）"))
    backends.append(("feishu", "飞书云文档（需额外配置）"))
    backends.append(("notion", "Notion（需额外配置）"))

    for i, (key, desc) in enumerate(backends, 1):
        default = " [默认]" if key == "filesystem" else ""
        print(f"  [{i}] {desc}{default}")

    try:
        choice = input("请选择 [1]: ").strip() or "1"
        idx = int(choice) - 1
        final_backend = backends[idx][0] if 0 <= idx < len(backends) else "filesystem"
    except (ValueError, IndexError):
        final_backend = "filesystem"

    _write_metadata(meta_path, final_backend)
    _rebuild_dedup()


def _write_metadata(path: Path, backend: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"backend": backend}, f, allow_unicode=True, default_flow_style=False)
    print(f"[INIT] 归档后端已设为: {backend}")


def _rebuild_dedup():
    """尝试重建 dedup 索引"""
    dedup_script = DIRS["skills"] / "metadata" / "dedup.py"
    if dedup_script.exists():
        import subprocess
        subprocess.run([sys.executable, str(dedup_script), "rebuild", "--dir", str(PROJECT_ROOT)])
    else:
        print("[INIT] 提示: metadata/dedup.py 尚未创建，后续运行 init 将重建索引")


def _detect_filesystem() -> bool:
    return True  # filesystem 总是可用


def _detect_zotero() -> bool:
    return ZOTERO_DB.exists()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="知识库全局配置")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="首次初始化")
    p_init.add_argument("--backend", choices=["filesystem", "zotero", "feishu", "notion"])
    p_init.add_argument("--non-interactive", action="store_true", help="非交互模式")

    args = parser.parse_args()
    if args.cmd == "init":
        init_config(backend=args.backend, non_interactive=args.non_interactive)
    else:
        parser.print_help()
