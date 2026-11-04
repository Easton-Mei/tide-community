from __future__ import annotations
import json
import re
import secrets as random_secrets
import threading
import time
import uuid
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from . import core, agent_bridge

TOKEN = random_secrets.token_urlsafe(32)
TASK_LOCK = threading.Lock()
TASK = {"status": "idle", "message": "等待开始"}
STOP = threading.Event()


def start_job(kind, function):
    if not TASK_LOCK.acquire(blocking=False):
        raise ValueError("已有任务运行中，请等待完成")
    TASK.clear()
    TASK.update({"status": "running", "kind": kind, "message": "任务开始", "started_at": core.now(), "id": uuid.uuid4().hex})
    def progress(message):
        TASK["message"] = message
    def worker():
        try:
            result = function(progress)
            TASK.update({"status": "done", "message": "任务完成", "result": result})
        except Exception as exc:
            TASK.update({"status": "failed", "message": core.safe_error(exc)})
        finally:
            TASK["finished_at"] = core.now()
            TASK_LOCK.release()
    threading.Thread(target=worker, daemon=True).start()
    return dict(TASK)


def local_time(schedule):
    if schedule["timezone"] == "local":
        return datetime.now().astimezone()
    return datetime.now(ZoneInfo(schedule["timezone"]))


def next_run():
    cfg = core.config("settings")["schedule"]
    if not cfg["enabled"]:
        return None
    try:
        current = local_time(cfg)
        hour, minute = map(int, cfg["time"].split(":"))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current:
            target += timedelta(days=1)
        return target.isoformat()
    except Exception:
        return "时区不可用，请选择系统时区"


def scheduler():
    while not STOP.wait(10):
        try:
            settings = core.config("settings")
            cfg = settings["schedule"]
            if not cfg["enabled"]:
                continue
            current = local_time(cfg)
            day = current.strftime("%Y-%m-%d")
            state = core.read_json(core.HOME / "data" / "schedule.json", {})
            if current.strftime("%H:%M") < cfg["time"] or state.get("day") == day or TASK_LOCK.locked():
                continue
            def job(progress, day=day, cfg=cfg):
                core.write_json(core.HOME / "data" / "schedule.json", {"day": day, "status": "running"})
                try:
                    report = core.generate(ai=cfg["ai"], progress=progress)
                    if cfg["push"]:
                        core.deliver(report)
                    core.write_json(core.HOME / "data" / "schedule.json", {"day": day, "status": "done", "report_id": report["id"]})
                    return {"report_id": report["id"]}
                except Exception as exc:
                    core.write_json(core.HOME / "data" / "schedule.json", {"day": day, "status": "failed", "error": core.safe_error(exc)})
                    raise
            start_job("定时简报", job)
        except Exception as exc:
            core.write_json(core.HOME / "data" / "scheduler_error.json", {"at": core.now(), "error": core.safe_error(exc)})


def watcher():
    """Monitoring loop. Runs only while this program is open and the computer is awake."""
    while not STOP.wait(30):
        try:
            cfg = core.watch_settings()
            if not cfg["enabled"] or TASK_LOCK.locked():
                continue  # yield to manual jobs; keep the SEC request rate polite
            state = core.read_json(core.HOME / "data" / "watch.json", {})
            if not core.watch_due(state, cfg["interval"]):
                continue
            if not TASK_LOCK.acquire(blocking=False):
                continue
            try:
                core.watch_once()
            finally:
                TASK_LOCK.release()
        except Exception as exc:
            core.write_json(core.HOME / "data" / "watch_error.json", {"at": core.now(), "error": core.safe_error(exc)})


def next_watch():
    cfg = core.watch_settings()
    if not cfg["enabled"]:
        return None
    last = core.parse_time(core.read_json(core.HOME / "data" / "watch.json", {}).get("last_run"))
    if not last:
        return "即将开始"
    return (last + timedelta(minutes=cfg["interval"])).isoformat()


def update_settings(body):
    current = core.config("settings")
    for key in ("quotes", "agent_enabled"):
        if key in body:
            if not isinstance(body[key], bool):
                raise ValueError("开关必须为布尔值")
            current[key] = body[key]
    if "model" in body:
        model = body["model"]
        url = str(model.get("base_url", "")).rstrip("/")
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("模型地址须使用 HTTPS，或本机 HTTP 地址")
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("模型地址格式不正确")
        current["model"] = {"base_url": url, "name": str(model.get("name", ""))[:200]}
    if "schedule" in body:
        cfg = body["schedule"]
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cfg.get("time", "")):
            raise ValueError("时间格式应为 HH:MM")
        for key in ("enabled", "ai", "push"):
            if not isinstance(cfg.get(key), bool):
                raise ValueError("调度开关必须为布尔值")
        zone = str(cfg.get("timezone", "local"))
        if zone != "local":
            try:
                ZoneInfo(zone)
            except ZoneInfoNotFoundError:
                raise ValueError("系统没有该时区数据库，请选择系统时区 local")
        current["schedule"] = {k: cfg[k] for k in ("enabled", "time", "timezone", "ai", "push")}
    if "watch" in body:
        cfg = body["watch"]
        if not isinstance(cfg, dict):
            raise ValueError("突发提醒设置格式不正确")
        cfg = {"ai_review": False, **cfg}
        for key in ("enabled", "push", "ai_review"):
            if not isinstance(cfg.get(key), bool):
                raise ValueError("突发提醒开关必须为布尔值")
        if cfg.get("interval") not in core.WATCH_INTERVALS:
            raise ValueError("检查间隔只能选 5、10、15、30 或 60 分钟")
        move = cfg.get("move_pct", 0)
        if isinstance(move, bool) or not isinstance(move, (int, float)) or not 0 <= move <= 50:
            raise ValueError("股价异动阈值应在 0～50 之间，0 表示关闭")
        current["watch"] = {"enabled": cfg["enabled"], "interval": cfg["interval"], "push": cfg["push"], "move_pct": move,
                            "ai_review": cfg["ai_review"]}
    if "hermes_executable" in body:
        current["hermes_executable"] = str(body["hermes_executable"])[:500]
    if "secrets" in body:
        core.save_secrets(body["secrets"])
    core.save_config("settings", current)
    return {"saved": True}


def snapshot():
    hidden = core.secrets()
    reports = sorted((core.HOME / "reports").glob("*.json"), reverse=True)[:30]
    return {"version": core.VERSION, "settings": core.config("settings"), "watchlist": core.config("watchlist"),
            "sources": core.config("sources"), "task": dict(TASK), "next_run": next_run(),
            "latest": core.read_json(core.HOME / "data" / "latest.json"),
            "reports": [{"id": p.stem} for p in reports],
            "configured": {k: bool(hidden.get(k)) for k in ("api_key", "feishu_webhook", "sec_user_agent")},
            "hermes_available": bool(agent_bridge.executable()),
            "schedule_state": core.read_json(core.HOME / "data" / "schedule.json", {}),
            "watch": core.watch_settings(), "next_watch": next_watch(), "alerts": core.recent_alerts(),
            "watch_state": core.read_json(core.HOME / "data" / "watch.json", {}).get("last_result"),
            "review_tokens_total": core.read_json(core.HOME / "data" / "watch.json", {}).get("review_tokens_total", 0)}


class Handler(BaseHTTPRequestHandler):
    server_version = "TideLocal/0.2"

    def log_message(self, fmt, *args):
        # Do not log URLs (model/webhook credentials can otherwise leak).
        return

    def respond(self, value, status=200, content_type="application/json; charset=utf-8"):
        data = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, (dict, list)) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def local_request(self):
        host = self.headers.get("Host", "")
        valid = (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")
        return host in valid and self.headers.get("Sec-Fetch-Site", "same-origin") not in ("cross-site",)

    def do_GET(self):
        if not self.local_request():
            return self.respond({"error": "仅允许本机页面访问"}, 403)
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/api/session":
                return self.respond({"token": TOKEN})
            if path == "/api/state":
                return self.respond(snapshot())
            if path.startswith("/api/report/"):
                identifier = path.removeprefix("/api/report/")
                if not re.fullmatch(r"[0-9T\-a-z]+", identifier):
                    raise ValueError("报告编号错误")
                report = core.read_json(core.HOME / "reports" / f"{identifier}.json")
                if not report:
                    return self.respond({"error": "报告不存在"}, 404)
                return self.respond(report)
            if path == "/guide/":
                return self.respond((core.ROOT / "docs" / "开始阅读.html").read_bytes(), content_type="text/html; charset=utf-8")
            if path == "/guide/guide.css":
                return self.respond((core.ROOT / "docs" / "guide.css").read_bytes(), content_type="text/css; charset=utf-8")
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in files:
                filename, mime = files[path]
                return self.respond((core.ROOT / "app" / "web" / filename).read_bytes(), content_type=mime)
            return self.respond({"error": "不存在"}, 404)
        except Exception as exc:
            self.respond({"error": core.safe_error(exc)}, 400)

    def do_POST(self):
        if not self.local_request() or not random_secrets.compare_digest(self.headers.get("X-Tide-Token", ""), TOKEN):
            return self.respond({"error": "请刷新本地页面后重试"}, 403)
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return self.respond({"error": "来源不受信任"}, 403)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 64000:
                raise ValueError("请求过大")
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("请求必须是 JSON 对象")
            result = self.route(self.path, body)
            self.respond(result)
        except Exception as exc:
            self.respond({"error": core.safe_error(exc)}, 400)

    def route(self, path, body):
        if path == "/api/report":
            return start_job("生成报告", lambda progress: {"report_id": core.generate(
                demo=bool(body.get("demo")), ai=bool(body.get("ai")), progress=progress)["id"]})
        if path == "/api/agent":
            request = str(body.get("request", "")).strip()
            if not 1 <= len(request) <= 4000:
                raise ValueError("请输入 1～4000 字任务")
            return start_job("Agent", lambda progress: agent_bridge.run(request, progress))
        if path == "/api/source/discover":
            return start_job("检测来源", lambda progress: core.discover(str(body.get("url", ""))))
        if path == "/api/source/add":
            return start_job("接入来源", lambda progress: core.add_source(str(body.get("url", "")), str(body.get("name", "")), body.get("symbols", [])))
        if path == "/api/watchlist/add":
            return start_job("添加公司", lambda progress: core.add_symbol(str(body.get("symbol", ""))))
        if path == "/api/watch":
            return start_job("检查突发", core.watch_once)
        if path == "/api/push":
            identifier = body.get("report_id", "")
            if not re.fullmatch(r"[0-9T\-a-z]+", identifier):
                raise ValueError("请先选择报告")
            report = core.read_json(core.HOME / "reports" / f"{identifier}.json")
            if not report:
                raise ValueError("请先生成报告")
            return start_job("发送飞书", lambda progress: core.deliver(report))
        if TASK_LOCK.locked():
            raise ValueError("请等待当前任务完成后修改设置")
        if path == "/api/settings":
            return update_settings(body)
        if path == "/api/watchlist/remove":
            core.save_config("watchlist", [x for x in core.config("watchlist") if x["symbol"] != body.get("symbol")])
            return {"removed": True}
        if path == "/api/source/toggle":
            sources = core.config("sources")
            for source in sources:
                if source["id"] == body.get("id"):
                    source["enabled"] = not source["enabled"]
            core.save_config("sources", sources)
            return {"saved": True}
        if path == "/api/source/remove":
            core.save_config("sources", [x for x in core.config("sources") if x["id"] != body.get("id")])
            return {"removed": True}
        if path == "/api/doctor":
            return {"python": __import__("sys").version.split()[0], "database": "已初始化",
                    "hermes": "可用" if agent_bridge.executable() else "未安装（基础功能可用）",
                    "model": "已填写，尚未验证" if core.secrets().get("api_key") else "未配置",
                    "network": "真实采集会逐项检测；演示模式不访问网络"}
        raise ValueError("未知操作")


def serve(port=8765, browser=True):
    core.initialize()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=watcher, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"潮汐已启动：{url}\n关闭本终端会停止定时运行。按 Ctrl+C 退出。", flush=True)
    if browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP.set()
        server.server_close()
