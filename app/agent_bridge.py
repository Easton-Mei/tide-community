"""Explicitly isolated Hermes integration. Never reads existing user credentials."""
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from . import core

PIN = "c4b2beea778ceca1462b91282589338b5e80781f"


def executable():
    local = core.ROOT / ".tools" / "hermes-venv" / ("Scripts/hermes.exe" if os.name == "nt" else "bin/hermes")
    if local.exists():
        return str(local)
    configured = core.config("settings").get("hermes_executable", "")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    return shutil.which("hermes")


def home():
    # Hermes honors explicit homes whose immediate parent is named profiles.
    return core.HOME / "data" / "hermes" / "profiles" / "tide-community"


def prepare():
    target = home()
    target.mkdir(parents=True, exist_ok=True)
    model = core.config("settings")["model"]
    # JSON is also valid YAML. This config belongs exclusively to this app.
    core.write_json(target / "config.yaml", {
        "model": {"default": model["name"], "provider": "custom", "base_url": model["base_url"]},
        "agent": {"max_turns": 8},
        "terminal": {"backend": "local", "cwd": str(core.ROOT), "timeout": 60},
    })
    skill = target / "skills" / "tide-operations"
    skill.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(core.ROOT / "agent" / "skills" / "tide-operations" / "SKILL.md", skill / "SKILL.md")
    shutil.copyfile(core.ROOT / "agent" / "SOUL.md", target / "SOUL.md")
    env = {k: v for k, v in os.environ.items() if k in (
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR")}
    shell_home = target / "home"
    shell_home.mkdir(exist_ok=True)
    env.update({"HOME": str(shell_home), "USERPROFILE": str(shell_home), "HERMES_HOME": str(target), "OPENAI_API_KEY": core.secrets().get("api_key", ""),
                "OPENAI_BASE_URL": model["base_url"], "TIDE_HOME": str(core.HOME),
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    return env


def run(request, progress=lambda value: None):
    settings = core.config("settings")
    if not settings.get("agent_enabled"):
        raise ValueError("请先在设置中启用 Agent 工具权限")
    if not core.secrets().get("api_key") or not settings["model"].get("name"):
        raise ValueError("请先配置模型和 API Key")
    command = executable()
    if not command:
        raise ValueError("未找到 Hermes。请运行安装 Hermes.command 或阅读 Agent 安装教程")
    env = prepare()
    instructions = (core.ROOT / "agent" / "AGENT.md").read_text(encoding="utf-8")
    prompt = (instructions + f"\n项目目录：{core.ROOT}\n运行数据目录：{core.HOME}\n"
              f"调用工具用 Python：{sys.executable}\n用户请求：\n{request}\n"
              "完成后报告执行证据。不要读取 data/secrets.json，不修改其他项目。")
    progress("Hermes 正在执行；最多 8 轮，5 分钟超时")
    kwargs = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    proc = subprocess.Popen([command, "chat", "-Q", "-q", prompt, "--provider", "custom", "--toolsets", "terminal,file", "--max-turns", "8"],
                            cwd=core.ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise ValueError("Agent 超时，已终止本次任务。请检查来源和配置后重试")
    output = core.safe_error(stdout[-18000:]) if proc.returncode else stdout[-18000:]
    for value in core.secrets().values():
        if value:
            output = output.replace(value, "[已隐藏]")
    if proc.returncode:
        raise ValueError("Hermes 运行失败：" + (output or core.safe_error(stderr[-1000:])))
    if not output.strip():
        raise ValueError("Hermes 没有返回结果，请检查模型配置")
    return {"output": output, "completed_at": core.now()}
