import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app import core, server, agent_bridge

RSS = b'''<rss version="2.0"><channel><item><title>A &amp; B</title><link>https://example.com/a</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><description>&lt;b&gt;News&lt;/b&gt;</description></item></channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title><link href="https://example.com/b"/><updated>2026-11-01T12:00:00Z</updated><summary>Summary</summary></entry></feed>'''


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(core, 'HOME', Path(self.tmp.name))
        self.patcher.start()
        core.initialize()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_feed_and_atom_parse(self):
        source = {'name': 'Test', 'url': 'https://example.com/feed', 'symbols': ['NVDA']}
        rss = core.parse_feed(RSS, source)[0]
        self.assertEqual(rss['title'], 'A & B')
        self.assertEqual(rss['summary'], 'News')
        self.assertEqual(core.parse_feed(ATOM, source)[0]['url'], 'https://example.com/b')
        with self.assertRaises(ValueError):
            core.parse_feed(b'<!DOCTYPE rss><rss/>', source)

    def test_demo_never_enters_live_history(self):
        report = core.generate(demo=True)
        self.assertTrue(report['demo'])
        with core.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM items').fetchone()[0], 0)
        self.assertFalse((core.HOME / 'data/latest_live.json').exists())
        self.assertIn('演示', report['markdown'])

    def test_dedup_and_window_exclude_undated_future_old(self):
        base = {'source':'x','title':'x','url':'https://example.com','summary':'','symbols':[]}
        time = datetime.now(timezone.utc)
        items = [{**base,'id':str(i),'published':dt} for i, dt in enumerate([
            time.isoformat(), (time-timedelta(days=3)).isoformat(), None,
            (time+timedelta(days=3)).isoformat()])]
        self.assertEqual(core.ingest(items), 4)
        self.assertEqual(core.ingest(items), 0)
        self.assertEqual(len(core.recent_items()), 1)

    def test_add_company_idempotent_and_source_matching(self):
        core.add_symbol('aapl')
        core.add_symbol('AAPL')
        self.assertEqual(len([c for c in core.config('watchlist') if c['symbol']=='AAPL']),1)
        self.assertTrue(any('AAPL' in s['symbols'] for s in core.config('sources')))
        with self.assertRaises(ValueError):
            core.add_symbol('ZZZZUNKNOWN')

    def test_discover_html_and_add_source_idempotent(self):
        html = b'<html><link type="application/rss+xml" href="/feed" title="News"></html>'
        def fetched(url, **kwargs):
            return (RSS if url.endswith('/feed') else html), url
        with patch.object(core, 'fetch', side_effect=fetched):
            self.assertEqual(core.discover('https://example.com')['url'], 'https://example.com/feed')
            core.add_source('https://example.com', symbols=['NVDA'])
            result = core.add_source('https://example.com')
            self.assertTrue(result['existing'])

    def test_source_failure_model_fallback_preserves_report(self):
        with patch.object(core, 'collect_feed', side_effect=ValueError('source down')), \
             patch.object(core, 'collect_quote', side_effect=ValueError('quote down')):
            report = core.generate(ai=True)
        self.assertTrue(report['warning'])
        self.assertTrue((core.HOME/'reports'/f'{report["id"]}.md').exists())
        self.assertTrue(any(h['status']=='failed' for h in report['health']))
        self.assertIn('不代表没有事件',report['markdown'])

    def test_public_url_blocks_loopback_and_private(self):
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch('socket.getaddrinfo', return_value=[(2,1,6,'',(ip,443))]):
                with self.assertRaises(ValueError):
                    core.public_url('https://example.com')
        for url in ('file:///etc/passwd','https://user:pass@example.com','http://example.com:8765'):
            with self.assertRaises(ValueError):
                core.public_url(url)

    def test_secret_redaction_and_private_permissions(self):
        core.save_secrets({'api_key':'secret-example'})
        self.assertNotIn('secret-example',core.safe_error(ValueError('failed secret-example')))
        self.assertNotIn('secret-example',json.dumps(server.snapshot()))

    def test_delivery_dedup_and_rejection(self):
        core.save_secrets({'feishu_webhook':'https://open.feishu.cn/open-apis/bot/v2/hook/test'})
        report = core.generate(demo=True)
        with patch.object(core,'get_json',return_value={'code':0}) as request:
            self.assertTrue(core.deliver(report)['sent'])
            self.assertTrue(core.deliver(report)['already_sent'])
            self.assertEqual(request.call_count,1)
        report['id'] += '-retry'
        with patch.object(core,'get_json',return_value={'code':100}):
            with self.assertRaises(ValueError):
                core.deliver(report)
        with core.db() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM deliveries WHERE report_id=?',(report['id'],)).fetchone())

    def test_agent_home_and_environment_isolation(self):
        core.save_secrets({'api_key':'tide-test-key'})
        with patch.dict('os.environ',{'ANTHROPIC_API_KEY':'private','HERMES_HOME':'/other/private','OPENAI_API_KEY':'old'}):
            env = agent_bridge.prepare()
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertEqual(env['OPENAI_API_KEY'],'tide-test-key')
        self.assertEqual(Path(env['HERMES_HOME']).parent.name,'profiles')
        self.assertTrue(Path(env['HERMES_HOME']).is_relative_to(core.HOME))

    def test_settings_validation(self):
        with self.assertRaises(ValueError):
            server.update_settings({'model':{'base_url':'http://evil.example/v1','name':'x'}})
        with self.assertRaises(ValueError):
            server.update_settings({'schedule':{'time':'29:90'}})
        self.assertTrue(server.update_settings({'model':{'base_url':'http://127.0.0.1:1234/v1','name':'local'}})['saved'])

    def test_latest_timestamp_wins_quote(self):
        with patch.object(core,'get_json',return_value={'chart':{'result':[{'meta':{'regularMarketTime':100,'regularMarketPrice':90,'preMarketTime':50,'preMarketPrice':70,'chartPreviousClose':80,'currency':'USD'},'timestamp':[200,300],'indicators':{'quote':[{'close':[100,None]}]}}]}}):
            quote = core.collect_quote('NVDA')
        self.assertEqual(quote['price'],100)
        self.assertEqual(quote['change_pct'],25)
        self.assertTrue(quote['stale'])


if __name__ == '__main__':
    unittest.main()
