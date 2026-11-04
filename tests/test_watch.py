import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app import core, server


def item(n, hours_ago=1, symbol='NVDA', source='NVIDIA Newsroom'):
    published = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    url = f'https://example.com/{n}'
    return {'id': core.hashlib.sha256(url.encode()).hexdigest(), 'source': source, 'title': f'消息 {n}',
            'url': url, 'published': published, 'summary': '', 'symbols': [symbol]}


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(core, 'HOME', Path(self.tmp.name)); self.patch.start(); core.initialize()
        core.save_secrets({'feishu_webhook': 'https://open.feishu.cn/open-apis/bot/v2/hook/test'})
        settings = core.config('settings'); settings['watch'] = {'enabled': True, 'interval': 15, 'push': True, 'move_pct': 0}
        core.save_config('settings', settings)

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def run_watch(self, items):
        with patch.object(core, 'collect_sources', return_value=(items, [])), \
             patch.object(core, 'get_json', return_value={'code': 0}) as push:
            return core.watch_once(), push

    def test_first_pass_only_records_existing_items(self):
        result, push = self.run_watch([item(1), item(2)])
        self.assertTrue(result['baseline'])
        self.assertEqual(result['alerts'], 0)
        self.assertEqual(push.call_count, 0)
        self.assertEqual(core.recent_alerts(), [])

    def test_new_recent_item_alerts_and_pushes_once(self):
        self.run_watch([item(1)])
        result, push = self.run_watch([item(1), item(2)])
        self.assertEqual(result['alerts'], 1)
        self.assertTrue(result['pushed'])
        self.assertEqual(push.call_count, 1)
        text = json.loads(push.call_args.kwargs['payload'])['content']['text']
        self.assertIn('消息 2', text)
        self.assertNotIn('消息 1', text)
        self.assertIn('https://example.com/2', text)
        # Same items again: nothing new, nothing pushed.
        result, push = self.run_watch([item(1), item(2)])
        self.assertEqual(result['alerts'], 0)
        self.assertEqual(push.call_count, 0)
        self.assertEqual(len(core.recent_alerts()), 1)

    def test_old_or_undated_items_are_stored_but_not_alerted(self):
        self.run_watch([])
        old = item(3, hours_ago=72)
        undated = {**item(4), 'published': None}
        result, push = self.run_watch([old, undated])
        self.assertEqual(result['new_items'], 2)
        self.assertEqual(result['alerts'], 0)
        self.assertEqual(push.call_count, 0)

    def test_push_failure_keeps_alerts(self):
        self.run_watch([])
        with patch.object(core, 'collect_sources', return_value=([item(5)], [])), \
             patch.object(core, 'get_json', return_value={'code': 19001}):
            result = core.watch_once()
        self.assertEqual(result['alerts'], 1)
        self.assertFalse(result['pushed'])
        self.assertTrue(result['push_error'])
        self.assertEqual(core.recent_alerts()[0]['title'], '消息 5')

    def test_price_move_alerts_once_per_direction_per_day(self):
        self.run_watch([])
        settings = core.config('settings'); settings['watch'].update(move_pct=5, push=False); core.save_config('settings', settings)
        quote = {'symbol': 'NVDA', 'price': 100, 'currency': 'USD', 'change_pct': -6.2,
                 'quote_time': core.now(), 'stale': False}
        with patch.object(core, 'collect_sources', return_value=([], [])), \
             patch.object(core, 'collect_quote', side_effect=lambda s: {**quote, 'symbol': s, 'change_pct': -6.2 if s == 'NVDA' else 0.5}):
            first = core.watch_once()
            second = core.watch_once()
        moves = [a for a in core.recent_alerts() if a['kind'] == 'move']
        self.assertEqual(len(moves), 1)
        self.assertIn('NVDA 股价下跌 6.20%', moves[0]['title'])
        self.assertEqual(first['alerts'], 1)
        self.assertEqual(second['alerts'], 0)
        # Small or stale moves never alert.
        with patch.object(core, 'collect_sources', return_value=([], [])), \
             patch.object(core, 'collect_quote', side_effect=lambda s: {**quote, 'symbol': s, 'change_pct': 1.0 if s != 'GOOGL' else 9.0, 'stale': s == 'GOOGL'}):
            self.assertEqual(core.watch_once()['alerts'], 0)


    def test_daily_ingestion_cannot_consume_monitor_alerts(self):
        self.run_watch([item(1)])
        core.ingest([item(2)])  # A daily report reaches the source first.
        result, push = self.run_watch([item(1), item(2), item(2)])
        self.assertEqual(result['alerts'], 1)
        self.assertEqual(push.call_count, 1)

    def test_failed_first_collection_does_not_establish_baseline(self):
        with patch.object(core, 'collect_sources', return_value=([], [{'name': 'feed', 'status': 'failed'}])):
            core.watch_once()
        self.assertFalse(core.read_json(core.HOME / 'data' / 'watch.json')['baselined'])
        result, push = self.run_watch([item(1)])
        self.assertTrue(result['baseline'])
        self.assertEqual(push.call_count, 0)

    def test_first_price_pass_is_quiet_and_direction_changes_do_not_repeat(self):
        settings = core.config('settings'); settings['watch'].update(move_pct=5, push=False); core.save_config('settings', settings)
        quote = {'price': 100, 'currency': 'USD', 'quote_time': core.now(), 'stale': False}
        counts = []
        for change in (-6, 6, -6, 6):
            with patch.object(core, 'collect_sources', return_value=([], [])), \
                 patch.object(core, 'collect_quote', side_effect=lambda symbol: {**quote, 'change_pct': change if symbol == 'NVDA' else 0}):
                counts.append(core.watch_once()['alerts'])
        self.assertEqual(counts, [0, 1, 0, 0])

    def test_background_monitor_holds_manual_job_lock(self):
        def check():
            self.assertTrue(server.TASK_LOCK.locked())
            with self.assertRaises(ValueError):
                server.start_job('manual', lambda progress: {})
        with patch.object(server.STOP, 'wait', side_effect=[False, True]), \
             patch.object(core, 'watch_once', side_effect=check) as run:
            server.watcher()
        self.assertEqual(run.call_count, 1)
        self.assertFalse(server.TASK_LOCK.locked())

    def model_reply(self, content, tokens=120):
        return {'choices': [{'message': {'content': content}}], 'usage': {'total_tokens': tokens}}

    def enable_review(self):
        core.save_secrets({'api_key': 'review-test-key'})
        settings = core.config('settings'); settings['watch']['ai_review'] = True; core.save_config('settings', settings)

    def test_quiet_check_never_calls_model(self):
        self.enable_review()
        self.run_watch([item(1)])
        with patch.object(core, 'collect_sources', return_value=([item(1)], [])), \
             patch.object(core, 'get_json') as request:
            result = core.watch_once()
        self.assertEqual(request.call_count, 0)
        self.assertEqual(result['tokens'], 0)

    def test_ai_review_pushes_only_important(self):
        self.enable_review()
        self.run_watch([])
        verdict = '好的：[{"i":0,"level":"important","reason":"发布财报"},{"i":1,"level":"ignore","reason":"营销活动"}]'
        calls = []
        def fake(url, **kwargs):
            calls.append((url, kwargs))
            return self.model_reply(verdict) if url.endswith('/chat/completions') else {'code': 0}
        with patch.object(core, 'collect_sources', return_value=([item(6), item(7)], [])), \
             patch.object(core, 'get_json', side_effect=fake):
            result = core.watch_once()
        model_call, push_call = calls
        self.assertNotIn('review-test-key', model_call[1]['payload'].decode())
        self.assertEqual(model_call[1]['headers']['Authorization'], 'Bearer review-test-key')
        self.assertTrue(result['reviewed'])
        self.assertEqual(result['pushed_count'], 1)
        self.assertEqual(result['tokens'], 120)
        text = json.loads(push_call[1]['payload'])['content']['text']
        self.assertIn('消息 6', text); self.assertIn('AI 判断：发布财报', text); self.assertNotIn('消息 7', text)
        levels = {a['title']: a['importance'] for a in core.recent_alerts()}
        self.assertEqual(levels, {'消息 6': 'important', '消息 7': 'ignore'})
        self.assertEqual(core.read_json(core.HOME / 'data' / 'watch.json')['review_tokens_total'], 120)

    def test_all_ignored_means_no_push(self):
        self.enable_review()
        self.run_watch([])
        def fake(url, **kwargs):
            return self.model_reply('[{"i":0,"level":"normal","reason":"一般"}]') if url.endswith('/chat/completions') else {'code': 0}
        with patch.object(core, 'collect_sources', return_value=([item(8)], [])), \
             patch.object(core, 'get_json', side_effect=fake) as request:
            result = core.watch_once()
        self.assertFalse(result['pushed'])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['alerts'], 1)

    def test_review_failure_falls_back_to_pushing_everything(self):
        self.enable_review()
        self.run_watch([])
        def fake(url, **kwargs):
            if url.endswith('/chat/completions'):
                return self.model_reply('抱歉，我无法判断')
            return {'code': 0}
        pushed = []
        with patch.object(core, 'collect_sources', return_value=([item(9), item(10)], [])), \
             patch.object(core, 'get_json', side_effect=lambda url, **kw: pushed.append(kw) or fake(url, **kw)):
            result = core.watch_once()
        self.assertFalse(result['reviewed'])
        self.assertTrue(result['review_error'])
        text = json.loads(pushed[-1]['payload'])['content']['text']
        self.assertIn('未经 AI 复核', text); self.assertIn('消息 9', text); self.assertIn('消息 10', text)

    def test_review_without_model_config_falls_back(self):
        settings = core.config('settings'); settings['watch']['ai_review'] = True; core.save_config('settings', settings)
        self.run_watch([])
        result, push = self.run_watch([item(11)])
        self.assertTrue(result['review_error'])
        self.assertEqual(push.call_count, 1)

    def test_due_and_settings_validation(self):
        self.assertTrue(core.watch_due({}, 15))
        now = datetime.now(timezone.utc)
        self.assertFalse(core.watch_due({'last_run': (now - timedelta(minutes=5)).isoformat()}, 15, now))
        self.assertTrue(core.watch_due({'last_run': (now - timedelta(minutes=16)).isoformat()}, 15, now))
        with self.assertRaises(ValueError):
            server.update_settings({'watch': {'enabled': True, 'push': False, 'interval': 1, 'move_pct': 0}})
        with self.assertRaises(ValueError):
            server.update_settings({'watch': {'enabled': True, 'push': False, 'interval': 15, 'move_pct': -1}})
        self.assertTrue(server.update_settings({'watch': {'enabled': True, 'push': False, 'interval': 5, 'move_pct': 3}})['saved'])
        self.assertFalse(core.watch_settings()['ai_review'])
        with self.assertRaises(ValueError):
            server.update_settings({'watch': {'enabled': True, 'push': False, 'interval': 5, 'move_pct': 3, 'ai_review': 'yes'}})
        self.assertTrue(server.update_settings({'watch': {'enabled': True, 'push': True, 'interval': 5, 'move_pct': 3, 'ai_review': True}})['saved'])
        self.assertTrue(core.watch_settings()['ai_review'])
        self.assertEqual(core.watch_settings()['interval'], 5)

    def test_old_settings_without_watch_still_work(self):
        settings = core.config('settings'); settings.pop('watch'); core.save_config('settings', settings)
        self.assertFalse(core.watch_settings()['enabled'])
        self.assertIn('watch', server.snapshot())

    def test_watcher_loop_runs_when_due_and_skips_when_disabled(self):
        with patch.object(server.STOP, 'wait', side_effect=[False, True]), \
             patch.object(core, 'watch_once', return_value={}) as run:
            server.watcher()
        self.assertEqual(run.call_count, 1)
        settings = core.config('settings'); settings['watch']['enabled'] = False; core.save_config('settings', settings)
        with patch.object(server.STOP, 'wait', side_effect=[False, True]), \
             patch.object(core, 'watch_once', return_value={}) as run:
            server.watcher()
        self.assertEqual(run.call_count, 0)


if __name__ == '__main__':
    unittest.main()
