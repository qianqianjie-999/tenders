# -*- coding: utf-8 -*-
"""G3 停机可见与降级离线测试（A8）：不连库、不调真实模型。

运行：python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))

from flask import Flask  # noqa: E402
from app.services import ai_analyzer_service as ai  # noqa: E402
from app.routes import ai_analysis as routes  # noqa: E402


def _down_health():
    return {'reachable': False, 'status': 'unavailable',
            'message': '模型主机关机或服务不可达（ConnectTimeout）',
            'url': 'http://127.0.0.1:11434/api/tags',
            'model': 'qwen3.8:27b', 'checked_at': '2026-11-15 10:00:00'}


def _up_health():
    h = _down_health()
    h.update(reachable=True, status='ok', message='模型服务在线')
    return h


class ClassifyErrorTests(unittest.TestCase):
    def test_network_errors_are_unavailable(self):
        for e in ('ConnectionError: refused', 'ReadTimeout: x',
                  'HTTPConnectionPool: Max retries exceeded',
                  'requests.exceptions.ConnectTimeout'):
            self.assertEqual(ai.classify_error(e), 'unavailable', e)

    def test_4xx_is_bad_request(self):
        self.assertEqual(ai.classify_error('400 Client Error: Bad Request'), 'bad_request')

    def test_5xx_and_parse_are_failed(self):
        self.assertEqual(ai.classify_error('500 Server Error'), 'failed')
        self.assertEqual(ai.classify_error('模型输出不是合法 JSON'), 'failed')
        self.assertEqual(ai.classify_error(None), 'failed')


class HealthProbeTests(unittest.TestCase):
    def test_unreachable_result(self):
        with mock.patch.object(ai.requests, 'get', side_effect=Exception('down')):
            h = ai.check_model_health(force=True, timeout=0.1)
        self.assertFalse(h['reachable'])
        self.assertEqual(h['status'], 'unavailable')
        self.assertIn('不可达', h['message'])
        self.assertEqual(ai.get_task_state()['model_status'], 'unavailable')

    def test_reachable_result_and_cache(self):
        class Resp(object):
            status_code = 200
        with mock.patch.object(ai.requests, 'get', return_value=Resp()) as m:
            h = ai.check_model_health(force=True, timeout=0.1)
            ai.check_model_health(timeout=0.1)  # 命中缓存，不应再次请求
        self.assertTrue(h['reachable'])
        self.assertEqual(h['status'], 'ok')
        self.assertEqual(m.call_count, 1)

    def test_health_url_strips_v1(self):
        self.assertTrue(ai._health_url().endswith('/api/tags'))
        self.assertNotIn('/v1/api/tags', ai._health_url())


class BatchSkipTests(unittest.TestCase):
    """A8：接口不可用时批量任务保持 pending、不写 failed。"""

    def test_down_host_skips_whole_batch(self):
        with mock.patch.object(ai.requests, 'get', side_effect=Exception('down')), \
             mock.patch.object(ai, 'save_analysis') as save, \
             mock.patch.object(ai, 'ensure_columns') as cols:
            n = ai.run_batch(['bidding_info'], 1, 20, '', False, True, True)
        self.assertEqual(n, 0)
        save.assert_not_called()
        cols.assert_not_called()
        state = ai.get_task_state()
        self.assertIn('pending', state['message'])
        self.assertEqual(state['model_status'], 'unavailable')

    def test_mid_batch_unavailable_aborts_without_failed(self):
        row = {'id': 7, 'project_name': '某项目', 'detail_content': '正文'}
        with mock.patch.object(ai, 'check_model_health', return_value=_up_health()), \
             mock.patch.object(ai, 'ensure_columns'), \
             mock.patch.object(ai, 'load_keywords', return_value=[]), \
             mock.patch.object(ai, 'load_company_profile', return_value={}), \
             mock.patch.object(ai, 'pick_rows', return_value=[row]), \
             mock.patch.object(ai, 'analyze_text',
                               return_value=(None, 'ReadTimeout: model host down')), \
             mock.patch.object(ai, 'save_analysis') as save, \
             mock.patch.object(ai.time, 'sleep'):
            n = ai.run_batch(['bidding_info'], 1, 20, '', False, False, False)
        self.assertEqual(n, 0)
        save.assert_not_called()
        state = ai.get_task_state()
        self.assertIn('pending', state['message'])
        self.assertFalse(state['running'])


class RouteDowngradeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'

    def test_batch_endpoint_returns_503_when_down(self):
        with mock.patch.object(ai, 'check_model_health', return_value=_down_health()), \
             mock.patch.object(ai, 'start_batch_async') as start:
            with self.app.test_request_context(method='POST', json={'table': 'bidding_info'}):
                resp = routes.api_analyze.__wrapped__()
        self.assertEqual(resp[1], 503)
        self.assertIn('pending', resp[0].get_json()['message'])
        start.assert_not_called()

    def test_single_endpoint_returns_503_when_down(self):
        class FakeCur(object):
            def execute(self, sql, params=None): pass
            def fetchone(self): return {'detail_content': '正文'}
            def close(self): pass
        class FakeConn(object):
            def cursor(self): return FakeCur()
            def close(self): pass
        with mock.patch.object(ai, 'check_model_health', return_value=_down_health()), \
             mock.patch.object(routes, 'get_db_connection', return_value=FakeConn()), \
             mock.patch.object(ai, 'analyze_and_save') as analyze:
            with self.app.test_request_context(method='POST'):
                resp = routes.api_analyze_one.__wrapped__('bidding_info', 7)
        self.assertEqual(resp[1], 503)
        analyze.assert_not_called()

    def test_model_health_endpoint(self):
        with mock.patch.object(ai, 'check_model_health', return_value=_down_health()) as chk:
            with self.app.test_request_context('/api/model-health?force=1'):
                resp = routes.api_model_health.__wrapped__()
        self.assertTrue(resp.get_json()['success'])
        self.assertEqual(resp.get_json()['health']['status'], 'unavailable')
        chk.assert_called_once_with(force=True)


if __name__ == '__main__':
    unittest.main()
