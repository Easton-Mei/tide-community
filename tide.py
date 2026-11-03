#!/usr/bin/env python3
"""The same commands serve users, the browser and Hermes."""
import argparse
import json
import sys
from app import core


def main():
    parser = argparse.ArgumentParser(description="潮汐 · 美股情报助手")
    sub = parser.add_subparsers(dest="command", required=True)
    web = sub.add_parser("web", help="打开本地控制台")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")
    report = sub.add_parser("report", help="生成简报")
    report.add_argument("--demo", action="store_true")
    report.add_argument("--ai", action="store_true")
    add = sub.add_parser("add-symbol", help="关注一家公司")
    add.add_argument("symbol")
    source = sub.add_parser("add-source", help="验证并接入来源")
    source.add_argument("url")
    source.add_argument("--name", default="")
    source.add_argument("--symbols", default="")
    discover = sub.add_parser("discover", help="查找网站订阅源，不保存")
    discover.add_argument("url")
    sub.add_parser("status", help="查看配置和最近运行")
    agent = sub.add_parser("agent", help="交给独立 Hermes 执行")
    agent.add_argument("request")
    args = parser.parse_args()
    core.initialize()
    if args.command == "web":
        from app.server import serve
        serve(args.port, not args.no_browser)
        return
    if args.command == "report":
        result = core.generate(demo=args.demo, ai=args.ai, progress=lambda message: print(message, file=sys.stderr))
        result = {"report_id": result["id"], "path": str(core.HOME / "reports" / (result["id"] + ".md")), "warning": result["warning"]}
    elif args.command == "add-symbol":
        result = core.add_symbol(args.symbol)
    elif args.command == "add-source":
        result = core.add_source(args.url, args.name, [s.strip().upper() for s in args.symbols.split(",") if s.strip()])
    elif args.command == "discover":
        result = core.discover(args.url)
    elif args.command == "agent":
        from app.agent_bridge import run
        result = run(args.request)
    else:
        from app.server import snapshot
        result = snapshot()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("操作未完成：" + core.safe_error(exc), file=sys.stderr)
        sys.exit(1)
