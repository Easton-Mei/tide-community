import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import core, server


def fake_feishu(chats=('oc_only',), send_code=0, token_code=0):
    calls = []

    def handler(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith('/tenant_access_token/internal'):
            return {'code': token_code, 'tenant_access_token': 't-test', 'expire': 7200}
        if '/im/v1/chats' in url:
            return {'code': 0, 'data': {'items': [{'name': f'群{i}', 'chat_id': c} for i, c in enumerate(chats)]}}
        if '/im/v1/messages' in url:
            return {'code': send_code}
        raise AssertionError('unexpected url ' + url)
    return handler, calls


class FeishuAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(core, 'HOME', Path(self.tmp.name)); self.patch.start(); core.initialize()
        core._FEISHU_TOKEN.clear()

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def write_env(self, **values):
        lines = [f'{k}={v}' for k, v in values.items()]
        core.feishu_env_path().write_text('# comment\n' + '\n'.join(lines) + '\n', encoding='utf-8')

    def test_template_is_created_once_and_private(self):
        first = core.create_feishu_env()
        self.assertTrue(first['created'])
        path = core.feishu_env_path()
        self.assertTrue(core.is_private(path), (core._windows_sid(), core._windows_acl(path)) if os.name == 'nt' else path.stat().st_mode)
        path.write_text('FEISHU_APP_ID=cli_kept\n', encoding='utf-8')
        second = core.create_feishu_env()
        self.assertFalse(second['created'])
        self.assertEqual(path.read_text(encoding='utf-8'), 'FEISHU_APP_ID=cli_kept\n')
        self.assertTrue(core.is_private(path))

    @unittest.skipUnless(os.name == 'nt', 'Windows ACL only')
    def test_windows_extra_readers_are_removed(self):
        import subprocess
        path = core.feishu_env_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('FEISHU_APP_ID=cli_kept\n', encoding='utf-8')
        subprocess.run(['icacls', str(path), '/grant', '*S-1-5-32-545:R', '*S-1-1-0:R'], check=True, capture_output=True)
        self.assertFalse(core.is_private(path))
        core.create_feishu_env()
        self.assertTrue(core.is_private(path), core._windows_acl(path))
        self.assertEqual(path.read_text(encoding='utf-8'), 'FEISHU_APP_ID=cli_kept\n')

    def test_empty_template_keeps_webhook_mode(self):
        core.create_feishu_env()
        self.assertIsNone(core.feishu_app())
        with self.assertRaises(ValueError):
            core.feishu_ready()

    def test_app_push_auto_targets_single_group(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='"secret-test"')
        handler, calls = fake_feishu()
        with patch.object(core, 'get_json', side_effect=handler):
            core.send_feishu('潮汐测试')
        url, kwargs = calls[-1]
        self.assertIn('receive_id_type=chat_id', url)
        body = json.loads(kwargs['payload'])
        self.assertEqual(body['receive_id'], 'oc_only')
        self.assertEqual(json.loads(body['content'])['text'], '潮汐测试')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer t-test')
        token_body = json.loads(calls[0][1]['payload'])
        self.assertEqual(token_body['app_secret'], 'secret-test')

    def test_app_wins_over_webhook_and_open_id_is_detected(self):
        core.save_secrets({'feishu_webhook': 'https://open.feishu.cn/open-apis/bot/v2/hook/test'})
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s', FEISHU_RECEIVE_ID='ou_me')
        handler, calls = fake_feishu(chats=())
        with patch.object(core, 'get_json', side_effect=handler):
            core.send_feishu('hi')
        self.assertTrue(all('/bot/v2/hook/' not in url for url, _ in calls))
        self.assertIn('receive_id_type=open_id', calls[-1][0])
        self.assertFalse(any('/im/v1/chats' in url for url, _ in calls))

    def test_ambiguous_or_missing_group_explains_next_step(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s')
        for chats, word in (((), '拉进一个群'), (('oc_a', 'oc_b'), 'feishu-check')):
            core._FEISHU_TOKEN.clear()
            handler, _ = fake_feishu(chats=chats)
            with patch.object(core, 'get_json', side_effect=handler), self.assertRaises(ValueError) as ctx:
                core.send_feishu('hi')
            self.assertIn(word, str(ctx.exception))

    def test_bad_credentials_and_rejected_send(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s')
        handler, _ = fake_feishu(token_code=99991663)
        with patch.object(core, 'get_json', side_effect=handler), self.assertRaises(ValueError) as ctx:
            core.send_feishu('hi')
        self.assertIn('App Secret', str(ctx.exception))
        core._FEISHU_TOKEN.clear()
        handler, _ = fake_feishu(send_code=230002)
        with patch.object(core, 'get_json', side_effect=handler), self.assertRaises(ValueError):
            core.send_feishu('hi')

    def test_token_is_cached(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s', FEISHU_RECEIVE_ID='oc_x')
        handler, calls = fake_feishu()
        with patch.object(core, 'get_json', side_effect=handler):
            core.send_feishu('a'); core.send_feishu('b')
        self.assertEqual(sum(url.endswith('/internal') for url, _ in calls), 1)

    def test_lark_domain_and_check_report(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s', FEISHU_DOMAIN='lark')
        handler, calls = fake_feishu(chats=('oc_a', 'oc_b'))
        with patch.object(core, 'get_json', side_effect=handler):
            result = core.feishu_check()
        self.assertTrue(all(url.startswith('https://open.larksuite.com/') for url, _ in calls))
        self.assertEqual(result['mode'], 'app')
        self.assertEqual(len(result['chats']), 2)
        self.assertIn('target_error', result)
        self.assertFalse(any('/im/v1/messages' in url for url, _ in calls))

    def test_secret_never_reaches_state_or_errors(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='very-secret-value')
        state = server.snapshot()
        self.assertTrue(state['configured']['feishu_app'])
        self.assertNotIn('very-secret-value', json.dumps(state, ensure_ascii=False))
        self.assertNotIn('very-secret-value', core.safe_error(ValueError('boom very-secret-value')))

    def test_report_delivery_uses_app(self):
        self.write_env(FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='s')
        handler, calls = fake_feishu()
        with patch.object(core, 'get_json', side_effect=handler):
            first = core.deliver({'id': 'r1', 'markdown': '简报'})
            second = core.deliver({'id': 'r1', 'markdown': '简报'})
        self.assertEqual(first, {'sent': True})
        self.assertEqual(second, {'already_sent': True})


if __name__ == '__main__':
    unittest.main()
