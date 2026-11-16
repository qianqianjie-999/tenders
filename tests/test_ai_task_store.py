# -*- coding: utf-8 -*-
"""ai_task_store 与"批量任务改独立进程"的离线单测（不连真实库、不启进程）。"""
import datetime
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))
os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')   # config 导入即校验

from app.services import ai_task_store as store  # noqa: E402
from app.services import ai_analyzer_service as ai  # noqa: E402


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.lastrowid = conn.default_lastrowid
        self.rowcount = 0
        self._last = None

    def execute(self, sql, args=None):
        self.conn.executed.append((' '.join(str(sql).split()), args))
        self._last = self.conn.pop()
        if isinstance(self._last, dict) and '__lastrowid__' in self._last:
            self.lastrowid = self._last['__lastrowid__']
            self._last = None

    def fetchone(self):
        return self._last

    def close(self):
        pass


class _FakeConn:
    def __init__(self, results=(), default_lastrowid=77):
        self._queue = list(results)
        self.executed = []
        self.default_lastrowid = default_lastrowid
        self.commits = 0
        self.closed = False

    def pop(self):
        return self._queue.pop(0) if self._queue else None

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def sql_list(self):
        return [s for s, _ in self.executed]


def _row(**kw):
    base = dict(id=1, status='running', params='', total=0, done=0, ok=0, failed=0,
                deep_ok=0, current='', message='', model_status='unknown', pid=None,
                started_at=datetime.datetime(2026, 11, 16, 20, 0, 0), finished_at=None,
                heartbeat_at=datetime.datetime(2026, 11, 16, 20, 5, 0), age=3)
    base.update(kw)
    return base


class TaskStoreAcquireTests(unittest.TestCase):
    def setUp(self):
        store.reset_table_cache()
        store._table_ready = True   # 跳过 DDL
        self.conn = None

    def _patch(self, results, **kw):
        self.conn = _FakeConn(results, **kw)
        patcher = mock.patch.object(store, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.conn

    def test_fresh_running_blocks_start(self):
        conn = self._patch([{'got': 1}, {'id': 7, 'age': 12}])
        ok, task_id, why = store.try_start('p')
        self.assertFalse(ok)
        self.assertEqual(task_id, 7)
        self.assertIn('已有分析任务在运行', why)
        self.assertFalse(any('INSERT' in s.upper() for s in conn.sql_list()))
        self.assertTrue(any('RELEASE_LOCK' in s for s in conn.sql_list()),
                        '命名锁必须显式释放，否则连接回池后锁会残留')

    def test_stale_running_is_taken_over(self):
        conn = self._patch([{'got': 1}, {'id': 7, 'age': 400},
                            None, {'__lastrowid__': 8}])
        ok, task_id, why = store.try_start('p')
        self.assertTrue(ok, why)
        self.assertEqual(task_id, 8)
        sqls = conn.sql_list()
        self.assertTrue(any("status='aborted'" in s for s in sqls),
                        '过期任务要标记 aborted，避免僵尸 running 卡住入口')
        self.assertTrue(any('INSERT INTO' in s.upper() for s in sqls))

    def test_lock_busy_returns_false(self):
        self._patch([{'got': 0}])
        ok, task_id, why = store.try_start('p')
        self.assertFalse(ok)
        self.assertIsNone(task_id)
        self.assertIn('锁', why)

    def test_touch_filters_unknown_fields(self):
        conn = self._patch([])
        store.touch(5, done=3, running=True, evil='x')
        sql = conn.sql_list()[0]
        self.assertIn('done', sql)
        self.assertNotIn('evil', sql)
        self.assertNotIn('running', sql, 'running 是前端字段，库里是 status')


class TaskStoreReadTests(unittest.TestCase):
    def setUp(self):
        store.reset_table_cache()
        store._table_ready = True

    def _patch(self, results):
        conn = _FakeConn(results)
        patcher = mock.patch.object(store, 'get_db_connection', return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        return conn

    def test_none_when_no_row(self):
        self._patch([None])
        self.assertIsNone(store.get_latest())

    def test_fresh_row_is_running(self):
        self._patch([_row(id=3, total=10, done=4, current='bidding_info#1 项目')])
        state = store.get_latest()
        self.assertTrue(state['running'])
        self.assertEqual(state['task_id'], 3)
        self.assertEqual((state['total'], state['done']), (10, 4))
        self.assertEqual(state['started_at'], '2026-11-16 20:00:00')
        self.assertFalse(state['stale'])

    def test_stale_row_not_running_and_explains(self):
        self._patch([_row(id=3, age=400, message='开始分析')])
        state = store.get_latest()
        self.assertFalse(state['running'], '心跳过期不能仍报 running，否则页面永远停在任务中')
        self.assertTrue(state['stale'])
        self.assertIn('中断', state['message'])
        self.assertEqual(state['status'], 'running')

    def test_string_timestamps_pass_through(self):
        self._patch([_row(started_at='2026-11-16 20:00:00', finished_at='2026-11-16 20:09:00')])
        state = store.get_latest()
        self.assertEqual(state['finished_at'], '2026-11-16 20:09:00')


class StartBatchSpawnsProcessTests(unittest.TestCase):
    def setUp(self):
        ai.set_progress_sink(None)
        self.tmp = tempfile.mkdtemp(prefix='ai_runner_')
        (Path(self.tmp) / 'tools').mkdir()
        (Path(self.tmp) / 'tools' / 'ai_batch_runner.py').write_text('# stub\n')
        patcher = mock.patch.object(ai, 'ROOT_DIR', Path(self.tmp))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patch_start(self, result):
        p = mock.patch.object(store, 'try_start', return_value=result)
        p.start()
        self.addCleanup(p.stop)

    def test_spawns_detached_process(self):
        self._patch_start((True, 42, ''))
        with mock.patch('subprocess.Popen') as popen:
            popen.return_value = mock.Mock(pid=12345)
            ok = ai.start_batch_async(['bidding_info'], 1, 5, 'has_content', False,
                                      today_only=True, keywords_only=True)
        self.assertTrue(ok)
        args, kwargs = popen.call_args
        cmd = args[0]
        self.assertIn('ai_batch_runner.py', ' '.join(cmd))
        self.assertIn('--task-id', cmd)
        self.assertIn('42', cmd)
        self.assertIn('--today-only', cmd)
        self.assertIn('--keywords-only', cmd)
        self.assertTrue(kwargs.get('start_new_session'),
                        '必须脱离 worker 的会话，否则 worker 回收会连带杀死任务')

    def test_busy_does_not_spawn(self):
        self._patch_start((False, 7, '已有分析任务在运行（10 秒前刚有心跳）'))
        with mock.patch('subprocess.Popen') as popen:
            ok = ai.start_batch_async(['bidding_info'], 1, 5, 'has_content', False)
        self.assertFalse(ok)
        popen.assert_not_called()

    def test_popen_failure_marks_task_failed(self):
        self._patch_start((True, 42, ''))
        with mock.patch('subprocess.Popen', side_effect=OSError('boom')), \
                mock.patch.object(store, 'finish') as finish:
            ok = ai.start_batch_async(['bidding_info'], 1, 5, 'has_content', False)
        self.assertFalse(ok)
        finish.assert_called_once()
        self.assertEqual(finish.call_args[0][1], 'failed')


class ProgressSinkTests(unittest.TestCase):
    def setUp(self):
        self.captured = []
        ai.set_progress_sink(lambda payload: self.captured.append(payload))

    def tearDown(self):
        ai.set_progress_sink(None)

    def test_running_false_maps_to_done(self):
        ai._set_state(running=False, message='完成：成功 1')
        payload = self.captured[-1]
        self.assertEqual(payload['status'], 'done')
        self.assertNotIn('running', payload)

    def test_explicit_status_wins(self):
        ai._set_state(running=False, status='aborted', message='已中止')
        self.assertEqual(self.captured[-1]['status'], 'aborted')

    def test_sink_error_never_breaks_analysis(self):
        ai.set_progress_sink(lambda payload: (_ for _ in ()).throw(RuntimeError('db down')))
        ai._set_state(running=True, total=3)   # 不应抛出
        with mock.patch.object(store, 'get_latest', return_value=None):
            self.assertEqual(ai.get_task_state()['total'], 3)


if __name__ == '__main__':
    unittest.main()
