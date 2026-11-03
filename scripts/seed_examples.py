"""Maintainer utility: regenerate public starter fixtures, never copy private state."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def write(name, data):
    (ROOT / "examples" / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

companies = {
    "NVDA": ("NVIDIA · 英伟达", "0001045810", "NVIDIA Newsroom", "https://nvidianews.nvidia.com/rss.xml"),
    "MSFT": ("Microsoft · 微软", "0000789019", "Microsoft Official Blog", "https://blogs.microsoft.com/feed/"),
    "GOOGL": ("Alphabet · 谷歌", "0001652044", "Google Blog", "https://blog.google/rss/"),
    "AMZN": ("Amazon · 亚马逊", "0001018724", "AWS News Blog", "https://aws.amazon.com/blogs/aws/feed/"),
    "AAPL": ("Apple · 苹果", "0000320193", "Apple Newsroom", "https://www.apple.com/newsroom/rss-feed.rss"),
    "META": ("Meta Platforms", "0001326801", "Meta Newsroom", "https://about.fb.com/news/feed/"),
    "TSLA": ("Tesla · 特斯拉", "0001318605", "", ""),
    "AMD": ("Advanced Micro Devices", "0000002488", "", ""),
    "MU": ("Micron · 美光", "0000723125", "", ""),
    "AVGO": ("Broadcom · 博通", "0001730168", "", ""),
    "ORCL": ("Oracle · 甲骨文", "0001341439", "", ""),
    "IBM": ("IBM", "0000051143", "IBM Newsroom", "https://newsroom.ibm.com/announcements?pagetemplate=rss"),
    "COIN": ("Coinbase", "0001679788", "", ""),
    "PLTR": ("Palantir", "0001321655", "", ""),
    "BRK-B": ("Berkshire Hathaway · 伯克希尔 B 类", "0001067983", "", ""),
}
catalog = {symbol: {"name": name, "cik": cik, "feeds": [{"name": feed_name, "url": url}] if url else []}
           for symbol, (name, cik, feed_name, url) in companies.items()}
write("catalog.json", catalog)
write("watchlist.json", [{"symbol": symbol, "name": catalog[symbol]["name"], "cik": catalog[symbol]["cik"]} for symbol in ("NVDA", "MSFT", "GOOGL")])
write("sources.json", [{"id": hashlib.sha256(feed["url"].encode()).hexdigest()[:12], **feed, "symbols": [symbol], "enabled": True, "kind": "rss"}
                       for symbol in ("NVDA", "MSFT", "GOOGL") for feed in catalog[symbol]["feeds"]])
write("settings.json", {"quotes": True, "agent_enabled": False, "hermes_executable": "", "model": {"base_url": "https://api.deepseek.com/v1", "name": "deepseek-chat"},
                       "schedule": {"enabled": False, "time": "20:00", "timezone": "local", "ai": False, "push": False}})
write("demo.json", {"items": [{"id": "demo-1", "source": "演示资料 · 非新闻", "title": "[演示] 关注公司的新产品公告", "url": "https://example.com/tide-demo/product",
                              "published": "2026-01-02T09:00:00+00:00", "summary": "这是一条虚构样例，用于展示来源与报告排版。", "symbols": ["NVDA"]},
                             {"id": "demo-2", "source": "演示资料 · 非新闻", "title": "[演示] 公司季度报告待复核", "url": "https://example.com/tide-demo/filing",
                              "published": "2026-01-02T08:00:00+00:00", "summary": "示例：打开原文检查数据，不根据标题生成买卖结论。", "symbols": ["MSFT"]}],
                    "quotes": [{"symbol": "DEMO", "price": 100, "currency": "USD", "change_pct": 1.25, "quote_time": "2026-01-02T09:00:00+00:00", "stale": True}]})
