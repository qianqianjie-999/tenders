# -*- coding: utf-8 -*-
"""focus/api/check 的离线单测：GET 兼容 + POST 传数组 + 条数/长度上限。

背景：原实现只收 GET，前端把整页 project_key 拼进 query，中文 URL-encode 后
一页能到 6KB，超过 gunicorn 默认 4094 的 request-line 上限会直接 400。
改成 POST JSON 后，GET 仍要能用（旧缓存页面），并且不能让超长输入把 SQL 撑爆。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))
os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')   # config 导入即校验

from flask import Flask  # noqa: E402

from app.routes import focus  # noqa: E402


class CollectKeysTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def _get(self, query):
        with self.app.test_request_context('/focus/api/check?' + query, method='GET'):
            return focus._collect_check_keys()

    def _post(self, payload):
        with self.app.test_request_context('/focus/api/check', method='POST', json=payload):
            return focus._collect_check_keys()

    def test_get_comma_separated(self):
        self.assertEqual(self._get('keys=a%7C%7C2026-11-16%7C%7C山东,b'), ['a||2026-11-16||山东', 'b'])

    def test_get_empty(self):
        self.assertEqual(self._get(''), [])

    def test_post_list(self):
        self.assertEqual(self._post({'keys': ['x', 'y']}), ['x', 'y'])

    def test_post_string_is_split(self):
        self.assertEqual(self._post({'keys': 'x,y'}), ['x', 'y'])

    def test_post_missing_keys(self):
        self.assertEqual(self._post({}), [])
        self.assertEqual(self._post({'keys': 123}), [])

    def test_post_blank_items_skipped(self):
        self.assertEqual(self._post({'keys': ['', '  ', 'ok']}), ['ok'])

    def test_overlong_key_dropped(self):
        long_key = '名' * (focus.MAX_KEY_LENGTH + 1)
        self.assertEqual(self._post({'keys': [long_key, 'ok']}), ['ok'])

    def test_key_count_capped(self):
        keys = ['k%d' % i for i in range(focus.MAX_CHECK_KEYS + 50)]
        self.assertEqual(len(self._post({'keys': keys})), focus.MAX_CHECK_KEYS)

    def test_get_over_cap_truncated_not_error(self):
        # 3KB 的 GET：旧页面仍能拿到部分结果，而不是 500/400
        keys = ','.join('项目名称%d||2026-11-16||山东' % i for i in range(120))
        got = self._get('keys=' + keys)
        self.assertEqual(len(got), 120)   # 未超上限就全收，不报错


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.seen = []

    def test_post_calls_service_with_keys(self):
        def fake_check(keys):
            self.seen.append(list(keys))
            return ['x']

        with self.app.test_request_context('/focus/api/check', method='POST',
                                           json={'keys': ['x', 'y']}):
            with mock.patch.object(focus.FocusService, 'check_exists', side_effect=fake_check):
                resp = focus.api_check()
                self.assertEqual(resp.get_json()['focused'], ['x'])
        self.assertEqual(self.seen, [['x', 'y']])

    def test_service_error_returns_500(self):
        with self.app.test_request_context('/focus/api/check', method='POST', json={'keys': ['x']}):
            with mock.patch.object(focus.FocusService, 'check_exists',
                                            side_effect=RuntimeError('db down')):
                resp, code = focus.api_check()
                self.assertEqual(code, 500)
                self.assertFalse(resp.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
