# -*- coding: utf-8 -*-
"""批量「自动补正文」的离线单测：不连库、不抓外网、不启进程。

背景（2026-11-16 生产）：批量只分析已有 detail_content 的记录，用户没先点
「抓取详情正文」，任务 0 秒完成、成功 0。改为批量自动先抓再分析，这些用例
把「抓取被调用/失败不阻塞/0 候选有明确提示」钉住。
"""
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))
os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')   # config 导入即校验

from app.services import ai_analyzer_service as ai  # noqa: E402
from app.services import ai_task_store as store  # noqa: E402


def _fake_fdc(per_table=None, exc_tables=()):
    """构造一个假的 fetch_detail_content 模块。"""
    fake = types.ModuleType('fetch_detail_content')
    calls = []

    class _Conn(object):
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    conns = []

    def _get_conn():
        c = _Conn()
        conns.append(c)
        return c

    def _process_table(conn, table, days, limit, workers, force, dry_run,
                       today_only=False, keywords=None):
        calls.append(dict(table=table, days=days, limit=limit, workers=workers,
                          force=force, dry_run=dry_run,
                          today_only=today_only, keywords=keywords))
        if table in exc_tables:
            raise RuntimeError('站点超时')
        return per_table.get(table, {'total': 0, 'ok': 0, 'fail': 0})

    fake.get_conn = _get_conn
    fake.process_table = _process_table
    fake.calls = calls
    fake.conns = conns
    return fake


class AutoFetchTests(unittest.TestCase):
    def test_aggregates_counts_and_passes_filters(self):
        fake = _fake_fdc({'bidding_info': {'total': 3, 'ok': 2, 'fail': 1},
                          'jiangsu_bidding_info': {'total': 1, 'ok': 1, 'fail': 0}})
        with mock.patch.dict(sys.modules, {'fetch_detail_content': fake}):
            stat = ai.auto_fetch_contents(['bidding_info', 'jiangsu_bidding_info'],
                                          1, True, 20, ['信号灯'])
        self.assertEqual(stat, {'total': 4, 'ok': 3, 'fail': 1})
        self.assertEqual([c['table'] for c in fake.calls],
                         ['bidding_info', 'jiangsu_bidding_info'])
        first = fake.calls[0]
        self.assertTrue(first['today_only'], '批量口径是当日发布')
        self.assertEqual(first['keywords'], ['信号灯'], '只抓标题命中关键词的，省附件解析')
        self.assertEqual(first['limit'], 20)
        self.assertFalse(first['dry_run'], '线上不允许 dry-run')
        self.assertFalse(first['force'], '不能强制重抓，否则每批都重抓一遍')
        self.assertTrue(all(c.closed for c in fake.conns), '连接必须关闭')

    def test_one_table_failure_does_not_block_others(self):
        fake = _fake_fdc({'jiangsu_bidding_info': {'total': 2, 'ok': 2, 'fail': 0}},
                         exc_tables=('bidding_info',))
        with mock.patch.dict(sys.modules, {'fetch_detail_content': fake}):
            stat = ai.auto_fetch_contents(['bidding_info', 'jiangsu_bidding_info'],
                                          1, True, 20, ['交通'])
        self.assertEqual(stat, {'total': 2, 'ok': 2, 'fail': 0})

    def test_missing_tool_returns_zero_without_raising(self):
        with mock.patch.dict(sys.modules, {'fetch_detail_content': None}):
            stat = ai.auto_fetch_contents(['bidding_info'], 1, True, 20, [])
        self.assertEqual(stat, {'total': 0, 'ok': 0, 'fail': 0})


class RunBatchAutoFetchTests(unittest.TestCase):
    def setUp(self):
        self.captured = []
        ai.set_progress_sink(lambda payload: self.captured.append(payload))

    def tearDown(self):
        ai.set_progress_sink(None)

    def _patch_common(self, rows=None, pick=None):
        picker = (mock.patch.object(ai, 'pick_rows', side_effect=pick) if pick
                  else mock.patch.object(ai, 'pick_rows', return_value=rows or []))
        return [
            mock.patch.object(ai, 'check_model_health', return_value={'reachable': True}),
            mock.patch.object(ai, 'ensure_columns'),
            mock.patch.object(ai, 'load_keywords', return_value=['信号灯']),
            mock.patch.object(ai, 'load_company_profile', return_value={}),
            picker,
            mock.patch.object(ai, 'analyze_text', return_value=({'summary': 'x'}, None)),
            mock.patch.object(ai, 'save_analysis'),
            # 循环里每条会查一次「是否请求停止」，单测不连库
            mock.patch.object(ai, '_stop_requested', return_value=False),
        ]

    def _run(self, patches, **kw):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return ai.run_batch(['bidding_info'], 1, 20, 'has_content', False,
                            today_only=True, keywords_only=True, **kw)

    def test_fetch_runs_before_pick_rows(self):
        order = []
        patches = self._patch_common(rows=[])
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(ai, 'auto_fetch_contents',
                               side_effect=lambda *a, **k: order.append('fetch') or
                               {'total': 2, 'ok': 2, 'fail': 0}):
            orig_pick = ai.pick_rows
            ai.pick_rows = lambda *a, **k: order.append('pick') or []
            try:
                ai.run_batch(['bidding_info'], 1, 20, 'has_content', False,
                             today_only=True, keywords_only=True)
            finally:
                ai.pick_rows = orig_pick
        self.assertEqual(order, ['fetch', 'pick'])

    def test_zero_candidates_explains_why(self):
        patches = self._patch_common(rows=[])
        with mock.patch.object(ai, 'auto_fetch_contents',
                               return_value={'total': 5, 'ok': 4, 'fail': 1}):
            n = self._run(patches)
        self.assertEqual(n, 0)
        msg = self.captured[-1]['message']
        self.assertIn('没有需要分析的记录', msg)
        self.assertIn('自动抓取正文 4 条', msg)

    def test_disabled_skips_fetch(self):
        patches = self._patch_common(rows=[])
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(ai, 'auto_fetch_contents') as fetch:
            ai.run_batch(['bidding_info'], 1, 20, 'has_content', False,
                         today_only=True, keywords_only=True, auto_fetch=False)
        fetch.assert_not_called()

    def test_success_message_carries_fetch_note(self):
        rows = [{'id': 1, 'project_name': '交通信号灯采购', 'detail_content': '正文',
                 'ai_analysis_status': None}]
        # 第二轮没候选就收工（循环版：不返回空列表会一直续跑）
        patches = self._patch_common(pick=[rows, [], []])
        with mock.patch.object(ai, 'auto_fetch_contents',
                               return_value={'total': 1, 'ok': 1, 'fail': 0}):
            n = self._run(patches)
        self.assertEqual(n, 1)
        # 循环版可能补抓多次，消息里的抓取数是累计值，这里只钉住"带上了抓取说明"
        self.assertIn('自动抓取正文', self.captured[-1]['message'])


class RunnerFlagTests(unittest.TestCase):
    def test_default_spawns_with_auto_fetch(self):
        with mock.patch.object(store, 'try_start', return_value=(True, 9, '')), \
                mock.patch('subprocess.Popen') as popen:
            ok = ai.start_batch_async(['bidding_info'], 1, 5, 'has_content', False)
        self.assertTrue(ok)
        cmd = popen.call_args[0][0]
        self.assertNotIn('--no-auto-fetch', cmd)

    def test_can_disable_auto_fetch(self):
        with mock.patch.object(store, 'try_start', return_value=(True, 9, '')), \
                mock.patch('subprocess.Popen') as popen:
            ok = ai.start_batch_async(['bidding_info'], 1, 5, 'has_content', False,
                                      auto_fetch=False)
        self.assertTrue(ok)
        cmd = popen.call_args[0][0]
        self.assertIn('--no-auto-fetch', cmd)


if __name__ == '__main__':
    unittest.main()
