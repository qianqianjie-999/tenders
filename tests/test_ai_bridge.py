# -*- coding: utf-8 -*-
"""G1/G2 桥接服务离线单测（不连库、不调模型、不需要 Flask 上下文）。

运行：python3 -m unittest discover -s tests -v
"""
import datetime
import importlib.util
import json
import os
import unittest
from decimal import Decimal

_HERE = os.path.dirname(os.path.abspath(__file__))
_SVC = os.path.join(_HERE, '..', 'flask_web', 'app', 'services',
                    'analysis_bridge_service.py')
_spec = importlib.util.spec_from_file_location('analysis_bridge_service', _SVC)
svc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(svc)


class FakeCursor(object):
    """按 SQL 片段注册返回值，同时记录所有调用，便于断言参数化。"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []
        self._row = None

    def on(self, fragment, row):
        self.responses.append((fragment, row))
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._row = None
        for fragment, row in self.responses:
            if fragment in sql:
                self._row = row
                break

    def fetchone(self):
        return self._row


def _ai(budget='20万元', deadline='2026-11-26 09:30', **kw):
    base = {
        'summary': '项目简介一段话',
        'purchaser': '华东革命烈士陵园管理服务中心',
        'agency': '某某招标代理有限公司',
        'budget': budget,
        'deadline': deadline,
        'risk': [],
        'compliance': [],
        'scoring': [],
    }
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


class BudgetTests(unittest.TestCase):
    """A2：唯一金额写 control_price，歧义置 NULL。"""

    def test_wan_yuan(self):
        self.assertEqual(svc.normalize_budget('20万元'), Decimal('200000.00'))

    def test_yuan_with_thousands(self):
        self.assertEqual(svc.normalize_budget('¥1,234,567.89元'), Decimal('1234567.89'))

    def test_multi_lot_is_none(self):
        self.assertIsNone(svc.normalize_budget(
            '一标段500万元；二标段350万元；三标段350万元'))

    def test_range_is_none(self):
        self.assertIsNone(svc.normalize_budget('20-30万元'))

    def test_vague_is_none(self):
        for s in ('详见招标文件', '以招标文件为准', '未获取', '800',
                  '2026-11-26', '', None, '0元', '99999999999999元'):
            self.assertIsNone(svc.normalize_budget(s), s)

    def test_highest_limit_phrase(self):
        self.assertEqual(svc.normalize_budget('最高限价260万元'),
                         Decimal('2600000.00'))


class DeadlineTests(unittest.TestCase):
    def test_datetime_prefix(self):
        self.assertEqual(svc.normalize_deadline('2026-11-26 09:30'), '2026-11-26')

    def test_chinese_date(self):
        self.assertEqual(svc.normalize_deadline('2026年12月3日 09:00'), '2026-12-03')

    def test_invalid(self):
        for s in ('未获取', '5日内', '2026-13-45', '', None):
            self.assertIsNone(svc.normalize_deadline(s), s)


class TextSafetyTests(unittest.TestCase):
    """A4 / A5：纯文本拼接、限长、不切断多字节字符。"""

    def test_summary_tolerates_empty_lists(self):
        s = svc.build_summary(json.loads(_ai()), model='qwen3.8:27b',
                              analyzed_at='2026-11-12 21:18:00')
        self.assertIn('摘要', s)
        self.assertIn('预算原文', s)
        self.assertIn('非开标日', s)
        self.assertNotIn('<', s)

    def test_summary_bytes_limit(self):
        big = json.loads(_ai(summary='项' * 40000))
        s = svc.build_summary(big)
        self.assertLess(len(s.encode('utf-8')), svc.MAX_CONTENT_BYTES)

    def test_truncate_keeps_valid_utf8(self):
        s = svc.truncate_utf8('中' * 30000, 60000)
        self.assertLessEqual(len(s.encode('utf-8')), 60000)
        self.assertTrue(s.endswith('中'))

    def test_append_keeps_manual_content(self):
        head = '人工结论：不投'
        out = svc.append_uploaded_text(head, '附件解析文本', 'a.pdf')
        self.assertTrue(out.startswith(head))
        self.assertIn('附件解析文本', out)

    def test_append_total_bytes_bounded(self):
        out = svc.append_uploaded_text('人' * 20000, '附' * 30000, 'b.pdf')
        self.assertLessEqual(len(out.encode('utf-8')), svc.MAX_CONTENT_BYTES)


class FillFromAiTests(unittest.TestCase):
    """A3 / A9：非空不覆盖、agency 不误填、查不到留空。"""

    def _cursor_with_ai(self, ai_json, manual=''):
        c = FakeCursor()
        c.on('SELECT analysis_content', {'analysis_content': manual})
        c.on('SELECT id, ai_analysis',
             {'id': 403, 'ai_analysis': ai_json,
              'ai_analyzed_at': datetime.datetime(2026, 11, 12, 21, 18)})
        return c

    def _find_update(self, cursor):
        for sql, params in cursor.calls:
            if sql.strip().startswith('UPDATE analysis_projects'):
                return params
        return None

    def test_fills_unique_budget_and_purchaser(self):
        c = self._cursor_with_ai(_ai())
        r = svc.fill_from_ai(c, 171, 'https://example.invalid/detail?id=1',
                             '某项目', datetime.date(2026, 11, 12), 'qwen3.8:27b')
        self.assertTrue(r['filled'])
        p = self._find_update(c)
        self.assertEqual(p[0], Decimal('200000.00'))
        self.assertEqual(p[1], '2026-11-26')
        self.assertEqual(p[2], '华东革命烈士陵园管理服务中心')
        self.assertNotEqual(p[2], '某某招标代理有限公司')
        self.assertLess(r['bytes'], 60000)

    def test_agency_never_becomes_tenderer(self):
        c = self._cursor_with_ai(_ai(purchaser='未获取'))
        svc.fill_from_ai(c, 171, 'https://example.invalid/detail?id=1')
        self.assertIsNone(self._find_update(c)[2])

    def test_multi_lot_price_is_null(self):
        c = self._cursor_with_ai(_ai(budget='一标段500万元；二标段350万元'))
        svc.fill_from_ai(c, 171, 'https://example.invalid/detail?id=1')
        self.assertIsNone(self._find_update(c)[0])

    def test_manual_content_not_overwritten(self):
        c = self._cursor_with_ai(_ai(), manual='资质不符')
        r = svc.fill_from_ai(c, 171, 'https://example.invalid/detail?id=1')
        self.assertFalse(r['filled'])
        self.assertEqual(r['reason'], 'manual_content_exists')
        self.assertIsNone(self._find_update(c))

    def test_no_ai_result_still_ok(self):
        c = FakeCursor().on('SELECT analysis_content', {'analysis_content': None})
        r = svc.fill_from_ai(c, 171, 'https://example.invalid/detail?id=1',
                             '某项目', datetime.date(2026, 11, 12))
        self.assertFalse(r['filled'])
        self.assertEqual(r['reason'], 'no_ai_result')
        self.assertIsNone(self._find_update(c))

    def test_lookup_is_parameterized_and_uses_whitelisted_tables(self):
        c = self._cursor_with_ai(_ai())
        svc.fill_from_ai(c, 171, "https://x.invalid/a' OR 1=1--",
                         '某项目', datetime.date(2026, 11, 12))
        for sql, params in c.calls:
            if 'FROM `' in sql:
                self.assertIn('detail_url = %s', sql)
                self.assertTrue(any(t in sql for t in svc.MAIN_TABLES))
                self.assertIsInstance(params, tuple)
                self.assertNotIn("OR 1=1", sql)


if __name__ == '__main__':
    unittest.main()
