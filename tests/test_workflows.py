import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from app import core, server
from scripts.build_release import release_files


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.object(core,'HOME',Path(self.tmp.name));self.patch.start();core.initialize()
    def tearDown(self):
        self.patch.stop();self.tmp.cleanup()

    def test_model_request_and_usage_are_retained(self):
        core.save_secrets({'api_key':'local-test-key'})
        with patch.object(core,'get_json',return_value={'choices':[{'message':{'content':'# 模型测试报告'}}],'usage':{'total_tokens':20}}) as request:
            report=core.generate(demo=True,ai=True)
        body=json.loads(request.call_args.kwargs['payload'])
        self.assertNotIn('local-test-key',json.dumps(body))
        self.assertEqual(report['usage']['total_tokens'],20)
        self.assertIn('演示模式',report['markdown'])
        self.assertIn('模型测试报告',report['markdown'])
        self.assertTrue(request.call_args.args[0].endswith('/chat/completions'))

    def test_daily_scheduler_executes_once_and_records_completion(self):
        settings=core.config('settings');settings['schedule'].update(enabled=True,time='00:00',ai=False,push=False);core.save_config('settings',settings)
        def run_job(kind,function):return function(lambda message:None)
        with patch.object(server.STOP,'wait',side_effect=[False,False,True]), \
             patch.object(server,'local_time',return_value=datetime(2026,1,2,12,tzinfo=timezone.utc)), \
             patch.object(server,'start_job',side_effect=run_job), \
             patch.object(core,'generate',return_value={'id':'test-report'}) as generate:
            server.scheduler()
        self.assertEqual(generate.call_count,1)
        self.assertEqual(core.read_json(core.HOME/'data/schedule.json')['status'],'done')

    def test_failed_schedule_is_not_retried_indefinitely(self):
        settings=core.config('settings');settings['schedule'].update(enabled=True,time='00:00');core.save_config('settings',settings)
        def run_job(kind,function):return function(lambda message:None)
        with patch.object(server.STOP,'wait',side_effect=[False,False,True]), \
             patch.object(server,'local_time',return_value=datetime(2026,1,2,12,tzinfo=timezone.utc)), \
             patch.object(server,'start_job',side_effect=run_job), \
             patch.object(core,'generate',side_effect=ValueError('offline')) as generate:
            server.scheduler()
        self.assertEqual(generate.call_count,1)
        self.assertEqual(core.read_json(core.HOME/'data/schedule.json')['status'],'failed')

    def test_release_allowlist_excludes_personal_state(self):
        paths=[p.relative_to(core.ROOT).as_posix() for p in release_files()]
        self.assertFalse(any(p.startswith(('data/','reports/','.tools/','logs/')) or p=='.env' for p in paths))
        self.assertFalse(any(p.startswith('config/') and p.endswith('.json') for p in paths))
        self.assertIn('examples/settings.json',paths)

if __name__=='__main__':unittest.main()
