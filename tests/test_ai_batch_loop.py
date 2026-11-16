# -*- coding: utf-8 -*-
"""批量「跑完为止」循环的离线单测：不连库、不抓外网、不启进程。

背景（2026-11-16）：原实现一次只取 limit 条就结束，用户得反复点按钮；
且 ai_analysis_status='failed' 不会被排除，一批稳定失败的记录每次都被重新选中，
正常记录永远排不进来（表现成「反复跑、成功 0」）。
这里把 4 个行为钉住：多轮续跑 / 失败不重挑 / 总闸截断 / 软停止。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))
os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')

from app.services import ai_analyzer_service as ai  # noqa: E402


def _row(rid, name='交通信号灯采购', content='正文内容足够长'):
    return {'id': rid, 'project_name': name, 'detail_content': content,
            'ai_analysis_status': None}


class BatchLoopTests(unittest.TestCase):
    def setUp(self):
        self.captured = []
        ai.set_progress_sink(self.captured.append)
        self.patches = [
            mock.patch.object(ai, 'check_model_health', return_value={'reachable': True}),
            mock.patch.object(ai, 'ensure_columns'),
            mock.patch.object(ai, 'load_keywords', return_value=[]),
            mock.patch.object(ai, 'load_company_profile', return_value={}),
            mock.patch.object(ai, 'save_analysis'),
            mock.patch.object(ai, '_stop_requested', return_value=False),
            mock.patch.object(ai, 'auto_fetch_contents',
                              return_value={'total': 0, 'ok': 0, 'fail': 0}),
            # 省掉每条 0.3s 的喘息，单测别把时间花在 sleep 上
            mock.patch('time.sleep'),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        ai.set_progress_sink(None)

    def _run(self, **kw):
        kw.setdefault('auto_fetch', False)
        # 关键词过滤在 test_ai_auto_fetch 里单独覆盖，这里聚焦循环本身
        return ai.run_batch(['bidding_info'], 1, 20, 'has_content', False,
                            today_only=True, keywords_only=False, **kw)

    def test_keeps_running_until_no_candidates(self):
        batches = [[_row(1)], [_row(2)], []]

        def fake_pick(*a, **k):
            return batches.pop(0) if batches else []

        with mock.patch.object(ai, 'pick_rows', side_effect=fake_pick), \
                mock.patch.object(ai, 'analyze_text',
                                  return_value=({'summary': 'x'}, None)):
            n = self._run()
        self.assertEqual(n, 2, '两批都要跑完，不能只跑第一批')
        self.assertIn('完成：2 轮', self.captured[-1]['message'])
        self.assertIn('成功 2', self.captured[-1]['message'])

    def test_failed_ids_are_excluded_from_later_rounds(self):
        seen_excludes = []

        def fake_pick(table, days, limit, status, force, today_only=False,
                      exclude_ids=None):
            seen_excludes.append(set(exclude_ids or ()))
            return [_row(7)] if len(seen_excludes) == 1 else []

        with mock.patch.object(ai, 'pick_rows', side_effect=fake_pick), \
                mock.patch.object(ai, 'analyze_text', return_value=(None, 'timeout')):
            n = self._run()
        self.assertEqual(n, 0)
        self.assertEqual(seen_excludes[0], set(), '首轮不该带排除')
        self.assertIn(7, seen_excludes[1], '失败记录必须排除，否则永远占名额')

    def test_exclusions_are_per_table(self):
        """id 跨表会重复，A 表失败的 id=7 不能把 B 表的 id=7 一起排除掉。"""
        seen = []
        calls = {}

        def fake_pick(table, days, limit, status, force, today_only=False,
                      exclude_ids=None):
            calls[table] = calls.get(table, 0) + 1
            seen.append((table, calls[table], set(exclude_ids or ())))
            if calls[table] == 1:
                bad = table == 'bidding_info'
                return [_row(7, content='bad' if bad else 'good')]
            return []

        def fake_analyze(name, content):
            return (None, 'timeout') if content == 'bad' else ({'summary': 'x'}, None)

        with mock.patch.object(ai, 'pick_rows', side_effect=fake_pick), \
                mock.patch.object(ai, 'analyze_text', side_effect=fake_analyze):
            n = ai.run_batch(['bidding_info', 'jiangsu_bidding_info'], 1, 20,
                             'has_content', False, today_only=True,
                             keywords_only=False, auto_fetch=False)
        self.assertEqual(n, 1, 'B 表那条应该成功')
        second_b = [s for s in seen if s[0] == 'jiangsu_bidding_info'][1]
        self.assertEqual(second_b[2], set(), 'B 表不该继承 A 表的失败 id')

    def test_max_total_caps_the_loop(self):
        rows = [_row(11), _row(12)]
        with mock.patch.object(ai, 'pick_rows', return_value=rows), \
                mock.patch.object(ai, 'analyze_text',
                                  return_value=({'summary': 'x'}, None)):
            n = self._run(max_total=2)
        self.assertEqual(n, 2)
        self.assertIn('已达本次上限 2 条', self.captured[-1]['message'])

    def test_stop_request_ends_politely(self):
        with mock.patch.object(ai, '_stop_requested', side_effect=[False, True]), \
                mock.patch.object(ai, 'pick_rows', return_value=[_row(3)]), \
                mock.patch.object(ai, 'analyze_text',
                                  return_value=({'summary': 'x'}, None)):
            n = self._run()
        self.assertEqual(n, 0, '第一条之前就收到停止，不应该分析')
        self.assertIn('已手动停止', self.captured[-1]['message'])


class PickRowsSqlTests(unittest.TestCase):
    """has_content 必须排除空串，否则空正文记录长期占候选名额。"""

    def test_empty_content_is_not_has_content(self):
        captured = {}

        class _Cur(object):
            def execute(self, sql, params=None):
                captured['sql'] = sql
                captured['params'] = params

            def fetchall(self):
                return []

            def close(self):
                pass

        class _Conn(object):
            def cursor(self):
                return _Cur()

            def close(self):
                pass

        with mock.patch.object(ai, 'get_db_connection', return_value=_Conn()):
            ai.pick_rows('bidding_info', 1, 20, 'has_content', False,
                         today_only=True, exclude_ids={7, 9})

        sql = captured['sql']
        self.assertIn('detail_content IS NOT NULL AND detail_content <> %s', sql)
        self.assertIn('id NOT IN (%s,%s)', sql)
        self.assertEqual(captured['params'], ['', 7, 9, 20],
                         '参数顺序：空串 → 排除 id → limit')


class StartBatchFlagTests(unittest.TestCase):
    def test_max_total_passed_to_runner(self):
        from app.services import ai_task_store as store
        with mock.patch.object(store, 'try_start', return_value=(True, 5, '')), \
                mock.patch('subprocess.Popen') as popen:
            ok = ai.start_batch_async(['bidding_info'], 1, 20, 'has_content', False,
                                      today_only=True, keywords_only=True,
                                      max_total=200)
        self.assertTrue(ok)
        cmd = popen.call_args[0][0]
        self.assertIn('--max-total', cmd)
        self.assertEqual(cmd[cmd.index('--max-total') + 1], '200')

    def test_no_max_total_keeps_cmd_clean(self):
        from app.services import ai_task_store as store
        with mock.patch.object(store, 'try_start', return_value=(True, 5, '')), \
                mock.patch('subprocess.Popen') as popen:
            ai.start_batch_async(['bidding_info'], 1, 20, 'has_content', False)
        self.assertNotIn('--max-total', popen.call_args[0][0])


if __name__ == '__main__':
    unittest.main()
