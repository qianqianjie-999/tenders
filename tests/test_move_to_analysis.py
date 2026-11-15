# -*- coding: utf-8 -*-
"""G1 转单接口离线测试：真实路由函数 + mock 数据库连接，不写业务库。

运行：python3 -m unittest discover -s tests -v
"""
import datetime
import json
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))

from flask import Flask  # noqa: E402
from app.routes import focus as focus_routes  # noqa: E402

_AI_JSON = json.dumps({
    'summary': '项目简介一段话',
    'purchaser': '华东革命烈士陵园管理服务中心',
    'agency': '某某招标代理有限公司',
    'budget': '20万元',
    'deadline': '2026-11-26 09:30',
    'risk': [], 'compliance': [], 'scoring': [],
}, ensure_ascii=False)

_FOCUS_ROW = {
    'project_name': '某智能交通项目公开招标',
    'publish_date': datetime.date(2026, 11, 12),
    'project_source': '省本级',
    'project_category': '智能交通',
    'detail_url': 'https://www.ccgp-shandong.gov.cn/detail?id=ABC',
}


class FakeCursor(object):
    def __init__(self, conn):
        self.conn = conn
        self._row = None
        self.lastrowid = 9001

    def execute(self, sql, params=None):
        s = ' '.join(sql.strip().split()).upper()
        self.conn.calls.append((s, params))
        if s.startswith('SAVEPOINT') or s.startswith('RELEASE') or s.startswith('ROLLBACK TO'):
            self.conn.savepoints.append(s.split()[0])
            self._row = None
            return
        if s.startswith('SELECT PROJECT_NAME'):
            self._row = self.conn.focus_row
        elif s.startswith('SELECT ID FROM ANALYSIS_PROJECTS'):
            self._row = self.conn.duplicate
        elif s.startswith('SELECT ANALYSIS_CONTENT'):
            if self.conn.fail_ai:
                raise RuntimeError('simulated AI fill failure')
            self._row = {'analysis_content': None}
        elif 'AI_ANALYSIS_STATUS' in s and s.startswith('SELECT ID'):
            self._row = self.conn.ai_row
        elif s.startswith('UPDATE ANALYSIS_PROJECTS'):
            self.conn.updates.append(params)
            self._row = None
        elif s.startswith('INSERT INTO ANALYSIS_PROJECTS'):
            self._row = None
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def close(self):
        self.conn.closed_cursor = True


class FakeConn(object):
    def __init__(self, ai_row=None, fail_ai=False, duplicate=None, focus_row=_FOCUS_ROW):
        self.ai_row = ai_row
        self.fail_ai = fail_ai
        self.duplicate = duplicate
        self.focus_row = focus_row
        self.calls = []
        self.updates = []
        self.savepoints = []
        self.commits = 0
        self.closed = False
        self.closed_cursor = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _ai_row():
    return {'id': 403, 'ai_analysis': _AI_JSON,
            'ai_analyzed_at': datetime.datetime(2026, 11, 12, 21, 18)}


class MoveToAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.config['ANALYSIS_ACCESS_CODE'] = 'kwd12345'

    def _call(self, conn, payload=None):
        with mock.patch.object(focus_routes, 'get_db_connection', return_value=conn), \
             mock.patch.object(focus_routes.ai_service, 'requests') as mreq, \
             mock.patch.object(focus_routes.ai_service, 'ai_config',
                               return_value={'model': 'qwen3.8:27b'}):
            with self.app.test_request_context(
                    method='POST', json=payload or {'focus_id': 42}):
                resp = focus_routes.api_move_to_analysis.__wrapped__()
        data = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
        status = resp[1] if isinstance(resp, tuple) else resp.status_code
        return data, status, mreq

    def test_transfer_succeeds_and_fills_ai(self):
        """A1/A2：转单成功、唯一金额回填、请求内不调用模型。"""
        conn = FakeConn(ai_row=_ai_row())
        data, status, mreq = self._call(conn)
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertTrue(data['ai_fill']['filled'])
        self.assertEqual(data['analysis_id'], 9001)
        self.assertEqual(mreq.post.call_count, 0)
        self.assertIn('SAVEPOINT', conn.savepoints)
        self.assertIn('RELEASE', conn.savepoints)
        self.assertEqual(conn.commits, 1)
        self.assertTrue(conn.closed and conn.closed_cursor)
        update_params = conn.updates[0]
        self.assertEqual(str(update_params[0]), '200000.00')
        self.assertEqual(update_params[1], '2026-11-26')
        self.assertEqual(update_params[2], '华东革命烈士陵园管理服务中心')

    def test_ai_fill_failure_does_not_break_transfer(self):
        """回填异常 -> ROLLBACK TO SAVEPOINT，转单仍成功。"""
        conn = FakeConn(ai_row=_ai_row(), fail_ai=True)
        data, status, _ = self._call(conn)
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['ai_fill']['reason'], 'fill_error')
        self.assertIn('ROLLBACK', conn.savepoints)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.updates, [])

    def test_no_ai_result_still_succeeds(self):
        """A1：查不到 AI 结果时转单照常成功，显式返回原因。"""
        conn = FakeConn(ai_row=None)
        data, status, mreq = self._call(conn)
        self.assertEqual(status, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['ai_fill']['reason'], 'no_ai_result')
        self.assertEqual(mreq.post.call_count, 0)
        self.assertEqual(conn.commits, 1)

    def test_duplicate_rejected_without_commit(self):
        conn = FakeConn(duplicate={'id': 1})
        data, status, _ = self._call(conn)
        self.assertEqual(status, 400)
        self.assertFalse(data['success'])
        self.assertEqual(conn.commits, 0)

    def test_missing_focus_id(self):
        conn = FakeConn()
        data, status, _ = self._call(conn, {'remove_from_focus': False})
        self.assertEqual(status, 400)

    def test_missing_focus_record(self):
        conn = FakeConn(focus_row=None)
        data, status, _ = self._call(conn)
        self.assertEqual(status, 404)

    def test_auth_required(self):
        """A6：未带访问口令直接 401，且不触碰数据库。"""
        from app.decorators import require_auth_write
        from flask_login import LoginManager
        lm = LoginManager()
        lm.init_app(self.app)
        lm.user_loader(lambda uid: None)

        @require_auth_write
        def probe():
            from flask import jsonify
            return jsonify({'success': True})

        with self.app.test_request_context('/x', method='POST'):
            resp = probe()
            self.assertEqual(resp[1], 401)


if __name__ == '__main__':
    unittest.main()
