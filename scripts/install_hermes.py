#!/usr/bin/env python3
"""Install a pinned upstream Hermes in this project only. No global setup."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.agent_bridge import PIN


def main():
    parser = argparse.ArgumentParser(description="安装独立 Hermes，不修改 ~/.hermes")
    parser.add_argument("--source", type=Path, help="已有官方 Hermes 源码目录，必须是锁定提交")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("安装程序需要 Python 3.11+；将为 Hermes 准备独立 Python 3.14")
    if os.name == "nt":
        raise SystemExit("本版 Hermes 安装请在 WSL 内运行。基础潮汐页面支持 Windows。详见 docs/Agent安装.md")
    git = shutil.which("git")
    if not git:
        raise SystemExit("请先安装 Git：https://git-scm.com/downloads")
    source = args.source.resolve() if args.source else ROOT / ".tools" / "hermes-src"
    if not args.source:
        source.mkdir(parents=True, exist_ok=True)
        if not (source / ".git").exists():
            subprocess.run([git, "init", str(source)], check=True)
            subprocess.run([git, "-C", str(source), "remote", "add", "origin", "https://github.com/NousResearch/hermes-agent.git"], check=True)
        subprocess.run([git, "-C", str(source), "fetch", "--depth", "1", "origin", PIN], check=True)
        subprocess.run([git, "-C", str(source), "checkout", "--detach", PIN], check=True)
    actual = subprocess.check_output([git, "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN:
        raise SystemExit("源码提交与锁定版本不同，停止安装")
    if subprocess.check_output([git, "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise SystemExit("Hermes 源码存在修改，停止安装；请提供干净官方源码")
    target = ROOT / ".tools" / "hermes-venv"
    print("正在创建项目专用环境并安装 Hermes；需要联网下载其依赖。", flush=True)
    bootstrap = ROOT / ".tools" / "installer"
    venv.EnvBuilder(with_pip=True).create(bootstrap)
    bootstrap_python = bootstrap / "bin" / "python"
    subprocess.run([str(bootstrap_python), "-m", "pip", "install", "uv==0.11.16"], check=True)
    uv = bootstrap / "bin" / "uv"
    env = os.environ.copy()
    env.update({"UV_PROJECT_ENVIRONMENT": str(target),
                "UV_PYTHON_INSTALL_DIR": str(ROOT / ".tools" / "python"),
                "UV_CACHE_DIR": str(ROOT / ".tools" / "uv-cache")})
    # Upstream lock includes deliberate dependency overrides. pip install alone
    # cannot resolve those pins. Install the upstream frozen lock with uv.
    subprocess.run([str(uv), "sync", "--project", str(source), "--frozen", "--no-dev", "--python", "3.14"], env=env, check=True)
    (ROOT / ".tools" / "hermes-version.json").write_text(json.dumps({"upstream": "NousResearch/hermes-agent", "commit": PIN}, indent=2))
    print("Hermes 已安装到 .tools。现在启动潮汐，在设置中填写模型并启用 Agent。")


if __name__ == "__main__":
    main()
