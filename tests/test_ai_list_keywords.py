# -*- coding: utf-8 -*-
"""AI 分析页列表：默认只显示命中后台关键词的项目。

口径与 run_batch 一致：标题或正文前 4000 字包含关键词即命中。
关键词来自 highlight_keywords，由后台维护；测试覆盖默认开启、可关闭、
LIKE 通配符转义、关键词数量硬顶，以及未分析记录的命中徽章实时补齐。
"""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))
os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')

from flask import Flask  # noqa: E402

from app.routes import ai_analysis as routes  # noqa: E402


class KeywordCondTest(unittest.TestCase):
    def test_two_keywords_build_or_like(self):
        cond, params = routes._keyword_like_cond(['信号灯', '监控'])
        self.assertIn('project_name LIKE %s', cond)
        self.assertIn('LEFT(detail_content, 4000) LIKE %s', cond)
        self.assertEqual(cond.count(' OR '), 3)   # 两个括号条件 + 两者之间一个 OR
        self.assertEqual(params, ['%信号灯%', '%信号灯%', '%监控%', '%监控%'])

    def test_like_wildcards_are_literal(self):
        cond, params = routes._keyword_like_cond(['a%b', 'c_d', 'e\\f'])
        self.assertEqual(params, ['%a\\%b%', '%a\\%b%', '%c\\_d%', '%c\\_d%',
                                  '%e\\\\f%', '%e\\\\f%'])
        self.assertEqual(cond.count("ESCAPE '\\\\'"), 6)   # 3 个关键词 × 2 列

    def test_empty_keywords_no_condition(self):
        for value in (None, [], ['', '  ']):
            cond, params = routes._keyword_like_cond(value)
            self.assertEqual(cond, '')
            self.assertEqual(params, [])

    def test_keyword_count_capped(self):
        cond, params = routes._keyword_like_cond(['kw%d' % i for i in range(200)])
        self.assertEqual(len(params), routes.MAX_LIST_KEYWORDS * 2)


class ApiListTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.row = {
            'id': 7,
            'project_name': '交通信号灯采购',
            'publish_date': datetime.date(2026, 11, 18),
            'project_source': '山东',
            'project_category': '',
            'detail_url': '',
            'ai_analysis': None,
            'ai_analysis_status': None,
            'ai_analyzed_at': None,
            'has_content': 1,
            'hit_text': '本项目含信号灯、监控设备',
        }

    def _call(self, query=''):
        cur = mock.MagicMock()
        cur.fetchall.return_value = [self.row]
        conn = mock.MagicMock()
        conn.cursor.return_value = cur
        with self.app.test_request_context('/ai-analysis/api/list?' + query, method='GET'):
            with mock.patch.object(routes, 'get_db_connection', return_value=conn), \
                 mock.patch.object(routes.ai, 'load_keywords',
                                   return_value=['信号灯', '监控']), \
                 mock.patch.object(routes.ai, 'check_model_health', return_value={}):
                resp = routes.api_list.__wrapped__()   # 绕过 @login_required，单测只验查询逻辑
        return resp, cur.execute.call_args_list

    def test_default_filters_by_keywords(self):
        resp, calls = self._call('days=7')
        body = resp.get_json()
        self.assertTrue(body['success'])
        sql, params = calls[0][0]
        self.assertIn('ESCAPE', sql)
        self.assertIn('%信号灯%', params)
        data = body['data'][0]
        self.assertEqual(data['matched_keywords'], ['信号灯', '监控'])

    def test_matched_only_zero_disables_filter(self):
        resp, calls = self._call('days=7&matched_only=0')
        sql, params = calls[0][0]
        self.assertNotIn('ESCAPE', sql)
        self.assertNotIn('%信号灯%', params)

    def test_matched_only_false_also_disables(self):
        _resp, calls = self._call('days=7&matched_only=false')
        sql, _params = calls[0][0]
        self.assertNotIn('ESCAPE', sql)

    def test_keyword_search_still_applies(self):
        _resp, calls = self._call('days=7&keyword=采购')
        sql, params = calls[0][0]
        self.assertIn('project_name LIKE %s', sql)
        self.assertIn('%采购%', params)


if __name__ == '__main__':
    unittest.main()
