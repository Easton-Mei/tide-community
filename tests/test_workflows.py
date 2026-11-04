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

    def run_scheduler_at(self, clock, ticks=1):
        def run_job(kind,function):return function(lambda message:None)
        hour,minute=map(int,clock.split(':'))
        with patch.object(server.STOP,'wait',side_effect=[False]*ticks+[True]), \
             patch.object(server,'local_time',return_value=datetime(2026,1,2,hour,minute,tzinfo=timezone.utc)), \
             patch.object(server,'start_job',side_effect=run_job), \
             patch.object(core,'generate',return_value={'id':'r'}) as generate:
            server.scheduler()
        return generate.call_count

    def test_two_daily_times_each_run_once(self):
        settings=core.config('settings');settings['schedule'].update(enabled=True,times=['08:00','20:00'],time='08:00',ai=False,push=False);core.save_config('settings',settings)
        self.assertEqual(self.run_scheduler_at('07:59'),0)
        self.assertEqual(self.run_scheduler_at('08:01',ticks=3),1)
        self.assertEqual(self.run_scheduler_at('12:00'),0)
        self.assertEqual(self.run_scheduler_at('20:00',ticks=2),1)
        self.assertEqual(core.read_json(core.HOME/'data/schedule.json')['done'],['08:00','20:00'])

    def test_late_start_runs_only_once_for_missed_times(self):
        settings=core.config('settings');settings['schedule'].update(enabled=True,times=['08:00','20:00'],ai=False,push=False);core.save_config('settings',settings)
        self.assertEqual(self.run_scheduler_at('21:00',ticks=3),1)
        self.assertEqual(core.read_json(core.HOME/'data/schedule.json')['slot'],'20:00')

    def test_old_single_time_settings_and_state_still_work(self):
        settings=core.config('settings');settings['schedule'].pop('times',None);settings['schedule'].update(enabled=True,time='08:00',ai=False,push=False);core.save_config('settings',settings)
        core.write_json(core.HOME/'data/schedule.json',{'day':'2026-01-02','status':'done','report_id':'old'})
        self.assertEqual(self.run_scheduler_at('09:00'),0)
        self.assertEqual(server.schedule_times(core.config('settings')['schedule']),['08:00'])

    def test_old_state_migration_keeps_future_slot_runnable(self):
        settings=core.config('settings');settings['schedule'].update(enabled=True,times=['08:00','20:00'],ai=False,push=False);core.save_config('settings',settings)
        core.write_json(core.HOME/'data/schedule.json',{'day':'2026-01-02','status':'done','report_id':'old'})
        self.assertEqual(self.run_scheduler_at('09:00',ticks=2),0)
        self.assertEqual(core.read_json(core.HOME/'data/schedule.json')['done'],['08:00'])
        self.assertEqual(self.run_scheduler_at('20:00',ticks=2),1)

    def test_empty_model_reply_falls_back_even_with_usage(self):
        with patch.object(core,'model_report',return_value=('   ',{'total_tokens':9})):
            report=core.generate(demo=True,ai=True)
        self.assertEqual(report['mode'],'规则报告')
        self.assertEqual(report['draft'],'')
        self.assertTrue(report['warning'])
        self.assertIn('来源覆盖与限制',report['markdown'])

    def test_schedule_times_validation(self):
        base={'enabled':True,'timezone':'local','ai':False,'push':False}
        with self.assertRaises(ValueError):server.update_settings({'schedule':{**base,'times':['08:00','25:00']}})
        with self.assertRaises(ValueError):server.update_settings({'schedule':{**base,'times':[],'time':'08:00'}})
        with self.assertRaises(ValueError):server.update_settings({'schedule':{**base,'times':False,'time':'08:00'}})
        with self.assertRaises(ValueError):server.update_settings({'schedule':{**base,'times':['01:00','02:00','03:00','04:00','05:00']}})
        server.update_settings({'schedule':{**base,'times':['20:00','08:00','08:00']}})
        cfg=core.config('settings')['schedule']
        self.assertEqual(cfg['times'],['08:00','20:00']);self.assertEqual(cfg['time'],'08:00')
        server.update_settings({'schedule':{**base,'time':'09:30'}})
        self.assertEqual(core.config('settings')['schedule']['times'],['09:30'])

    def test_ai_brief_is_readable_and_draft_kept_separately(self):
        core.save_secrets({'api_key':'k'})
        with patch.object(core,'get_json',return_value={'choices':[{'message':{'content':'# 潮汐 · 11月4日\n\n今早海面平静。'}}],'usage':{'total_tokens':9}}) as request:
            report=core.generate(demo=True,ai=True)
        system=json.loads(request.call_args.kwargs['payload'])['messages'][0]['content']
        self.assertIn('先给结论',system); self.assertIn('[原文](URL)',system)
        self.assertIn('今早海面平静',report['markdown'])
        self.assertNotIn('来源覆盖与限制',report['markdown'])
        self.assertIn('来源覆盖与限制',report['draft'])
        self.assertTrue((core.HOME/'reports'/f'{report["id"]}-底稿.md').exists())
        self.assertEqual(report['mode'],'AI 简报')

    def test_rule_report_has_no_separate_draft(self):
        report=core.generate(demo=True)
        self.assertEqual(report['draft'],'')
        self.assertFalse((core.HOME/'reports'/f'{report["id"]}-底稿.md').exists())

    def test_release_allowlist_excludes_personal_state(self):
        paths=[p.relative_to(core.ROOT).as_posix() for p in release_files()]
        self.assertFalse(any(p.startswith(('data/','reports/','.tools/','logs/')) or p=='.env' for p in paths))
        self.assertFalse(any(p.startswith('config/') and p.endswith('.json') for p in paths))
        self.assertIn('examples/settings.json',paths)

if __name__=='__main__':unittest.main()
