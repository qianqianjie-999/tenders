# -*- coding: utf-8 -*-
"""AI 覆盖率工具与模型请求代理修复的离线测试。

不写数据库、不调真实模型：模型相关验证用本机临时 HTTP 服务。
运行：python -m unittest discover -s tests -v
"""
import argparse
import contextlib
import json
import os
import sys
import threading
import http.server
import socketserver
import unittest
from unittest import mock

os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))
sys.path.insert(0, os.path.join(_ROOT, 'tools'))

import requests  # noqa: E402
import ai_coverage as cov  # noqa: E402
from app.services import ai_analyzer_service as ai  # noqa: E402

VALID_AI = {
    'project_name': '测试项目', 'purchaser': '某单位', 'budget': '20万元',
    'deadline': '2026-12-03 09:00', 'summary': '摘要', 'relevance': 7,
}
SOURCE_ONLY = {'source': {'title': '采购意向', 'agency': '某单位',
                          'pub_date': '2026-11-12', 'column_type': '2500'}}


class ClassifyPayloadTests(unittest.TestCase):
    def test_valid_result(self):
        self.assertEqual(cov.classify_ai_payload(VALID_AI), 'valid')

    def test_valid_result_keeps_source(self):
        """save_analysis 会把抓取元数据合并进真结论，不能因此被判成占位。"""
        obj = dict(VALID_AI, source=SOURCE_ONLY['source'])
        self.assertEqual(cov.classify_ai_payload(obj), 'valid')

    def test_source_only_is_not_a_result(self):
        self.assertEqual(cov.classify_ai_payload(SOURCE_ONLY), 'source_only')

    def test_error_and_empty(self):
        self.assertEqual(cov.classify_ai_payload({'error': 'timeout'}), 'error')
        self.assertEqual(cov.classify_ai_payload({'error': 'x', 'source': {}}), 'error')
        self.assertEqual(cov.classify_ai_payload(None), 'empty')
        self.assertEqual(cov.classify_ai_payload(''), 'empty')
        self.assertEqual(cov.classify_ai_payload('not-json'), 'empty')
        self.assertEqual(cov.classify_ai_payload('{"foo":1}'), 'unknown')

    def test_json_string_and_bytes(self):
        self.assertEqual(cov.classify_ai_payload(json.dumps(VALID_AI)), 'valid')
        self.assertEqual(
            cov.classify_ai_payload(json.dumps(SOURCE_ONLY).encode('utf-8')),
            'source_only')


class SummarizeRowsTests(unittest.TestCase):
    def test_counts_do_not_inflate_coverage(self):
        rows = [
            {'payload': VALID_AI, 'status': 'ok', 'has_content': True},
            {'payload': SOURCE_ONLY, 'status': 'pending', 'has_content': True},
            {'payload': {'error': 'x'}, 'status': 'failed', 'has_content': True},
            {'payload': None, 'status': 'pending', 'has_content': False},
        ]
        s = cov.summarize_rows(rows)
        self.assertEqual(s['total'], 4)
        self.assertEqual(s['has_content'], 3)
        self.assertEqual(s['valid'], 1)
        self.assertEqual(s['ok_valid'], 1)
        self.assertEqual(s['source_only'], 1)
        self.assertEqual(s['error'], 1)
        self.assertEqual(s['empty'], 1)
        self.assertEqual(s['pending_with_content'], 2)

    def test_ok_status_without_valid_payload_is_not_counted(self):
        s = cov.summarize_rows([
            {'payload': SOURCE_ONLY, 'status': 'ok', 'has_content': True},
        ])
        self.assertEqual(s['valid'], 0)
        self.assertEqual(s['ok_valid'], 0)


class _ModelHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"models":[]}')

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            self.rfile.read(length)
        inner = json.dumps(VALID_AI, ensure_ascii=False)
        body = json.dumps({
            'choices': [{'message': {'content': inner}, 'finish_reason': 'stop'}]
        }).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def local_model_server():
    srv = socketserver.TCPServer(('127.0.0.1', 0), _ModelHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield 'http://127.0.0.1:%d/v1' % port
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


@contextlib.contextmanager
def dead_proxy():
    keys = ('http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY',
            'no_proxy', 'NO_PROXY')
    saved = {k: os.environ.get(k) for k in keys}
    for k in ('no_proxy', 'NO_PROXY'):
        os.environ.pop(k, None)
    for k in ('http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY'):
        os.environ[k] = 'http://127.0.0.1:1'
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class ProxyBypassTests(unittest.TestCase):
    def tearDown(self):
        # check_model_health 有 60s 全局缓存；这里写入过 reachable=True，
        # 不清会污染后面 G3「停机整批跳过」的基线测试。
        ai._health_cache['value'] = None
        ai._health_cache['at'] = 0.0

    def test_model_session_disables_env_trust(self):
        self.assertFalse(ai._MODEL_SESSION.trust_env)

    def test_health_and_chat_work_with_dead_proxy(self):
        """反证：默认 requests 被代理劫持；修复后的 session 直连正常。"""
        with local_model_server() as base, dead_proxy(), \
                mock.patch.dict(os.environ, {'AI_BASE_URL': base}):
            with self.assertRaises(requests.RequestException):
                requests.get(base.rsplit('/v1', 1)[0] + '/api/tags', timeout=1)

            h = ai.check_model_health(force=True, timeout=2)
            self.assertTrue(h['reachable'], h['message'])
            self.assertEqual(h['status'], 'ok')

            obj, err = ai._call_model('测试正文')
            self.assertIsNone(err, err)
            self.assertEqual(obj.get('project_name'), '测试项目')


class BackfillOrchestrationTests(unittest.TestCase):
    @staticmethod
    def _args(execute=True):
        return argparse.Namespace(execute=execute, days=3650, per_table=100,
                                  max_rounds=30)

    def test_dry_run_never_calls_batch(self):
        with mock.patch.object(cov, 'db_connect', return_value=mock.MagicMock()), \
                mock.patch.object(cov, 'pending_count', return_value=721), \
                mock.patch.object(ai, 'run_batch') as rb, \
                mock.patch.object(cov, 'build_app') as ba:
            rc = cov.cmd_backfill(self._args(execute=False))
        self.assertEqual(rc, 0)
        rb.assert_not_called()
        ba.assert_not_called()

    def test_down_host_skips_without_writing(self):
        app = mock.MagicMock()
        app.app_context.return_value = contextlib.nullcontext()
        with mock.patch.object(cov, 'db_connect', return_value=mock.MagicMock()), \
                mock.patch.object(cov, 'pending_count', return_value=721), \
                mock.patch.object(cov, 'build_app', return_value=app), \
                mock.patch.object(ai, 'check_model_health',
                                  return_value={'reachable': False, 'message': 'down'}), \
                mock.patch.object(ai, 'run_batch') as rb:
            rc = cov.cmd_backfill(self._args())
        self.assertEqual(rc, 0)
        rb.assert_not_called()

    def test_loops_until_pending_is_zero(self):
        app = mock.MagicMock()
        app.app_context.return_value = contextlib.nullcontext()
        state = {'model_status': 'ok', 'message': '完成：成功 6'}
        with mock.patch.object(cov, 'db_connect', return_value=mock.MagicMock()), \
                mock.patch.object(cov, 'pending_count', side_effect=[6, 3, 0]), \
                mock.patch.object(cov, 'build_app', return_value=app), \
                mock.patch.object(ai, 'check_model_health',
                                  return_value={'reachable': True, 'message': '在线'}), \
                mock.patch.object(ai, 'run_batch', return_value=3) as rb, \
                mock.patch.object(ai, 'get_task_state', return_value=state):
            rc = cov.cmd_backfill(self._args())
        self.assertEqual(rc, 0)
        self.assertEqual(rb.call_count, 2)

    def test_stops_when_model_drops_mid_batch(self):
        app = mock.MagicMock()
        app.app_context.return_value = contextlib.nullcontext()
        state = {'model_status': 'unavailable', 'message': '模型服务不可达，中止批量'}
        with mock.patch.object(cov, 'db_connect', return_value=mock.MagicMock()), \
                mock.patch.object(cov, 'pending_count', return_value=6), \
                mock.patch.object(cov, 'build_app', return_value=app), \
                mock.patch.object(ai, 'check_model_health',
                                  return_value={'reachable': True, 'message': '在线'}), \
                mock.patch.object(ai, 'run_batch', return_value=0) as rb, \
                mock.patch.object(ai, 'get_task_state', return_value=state):
            rc = cov.cmd_backfill(self._args())
        self.assertEqual(rc, 0)
        self.assertEqual(rb.call_count, 1)


if __name__ == '__main__':
    unittest.main()
