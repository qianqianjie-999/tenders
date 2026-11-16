# -*- coding: utf-8 -*-
"""AI 输出 JSON 解析鲁棒性测试（离线，不调模型、不连库）。

针对实测缺陷：本地 27B 模型偶发在最后一个字段后直接结束（finish_reason=stop，
completion_tokens 远未触顶），输出少一个 `}`，被括号扫描判为非法而整条丢成 failed。
运行：python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))

from app.services import ai_analyzer_service as ai  # noqa: E402


class RepairTruncatedJsonTests(unittest.TestCase):
    def test_complete_json_untouched(self):
        obj = ai._extract_json('{"a": 1, "b": "x"}')
        self.assertEqual(obj, {'a': 1, 'b': 'x'})

    def test_missing_final_brace_recovered(self):
        # 实测形态：内容到最后一个字段都完整，只差结尾 } 
        raw = ('{"project_name": "某特刊项目", "budget": "347万元", '
               '"scoring": "需查招标文件"')
        obj = ai._extract_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj['project_name'], '某特刊项目')
        self.assertEqual(obj['scoring'], '需查招标文件')

    def test_nested_objects_all_closed(self):
        raw = '{"a": {"x": 1, "y": 2}, "b": {"z": [1, 2]'
        obj = ai._extract_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj['a'], {'x': 1, 'y': 2})
        self.assertEqual(obj['b'], {'z': [1, 2]})

    def test_half_cut_string_value_dropped(self):
        # 最后一段字符串被截半：不能把半截文本当结论，应退回到上一个完整字段
        raw = '{"project_name": "测试", "qualification": "须具备建筑工程施工总承包'
        obj = ai._extract_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj['project_name'], '测试')
        self.assertNotIn('qualification', obj)

    def test_fenced_output_with_missing_brace(self):
        raw = '```json\n{"a": "b", "c": 3\n```'
        obj = ai._extract_json(raw)
        self.assertIsNotNone(obj)
        self.assertEqual(obj['a'], 'b')

    def test_garbage_returns_none(self):
        for raw in ('', '   ', '抱歉，我无法完成', '[]', 'null'):
            self.assertIsNone(ai._extract_json(raw), repr(raw))

    def test_unrecoverable_broken_json_returns_none(self):
        # 闭合了但语法非法（多余逗号），不应被"修复"成错数据
        self.assertIsNone(ai._extract_json('{"a": 1,, "b": 2}'))

    def test_escape_at_tail_returns_none(self):
        # 末尾落在转义符上，补引号会变成 \" 仍非法，应安全返回 None
        raw = '{"a": "x\\'
        self.assertIsNone(ai._extract_json(raw))


class PromptBudgetTests(unittest.TestCase):
    def test_analysis_budget_covers_long_chinese_json(self):
        # 22 字段中文 JSON 在 2000 token 下会被截断，实测 2400 仍不够
        import inspect
        sig = inspect.signature(ai._call_model)
        self.assertGreaterEqual(sig.parameters['max_tokens'].default, 4096)

    def test_call_sites_use_enough_budget(self):
        import inspect
        src = inspect.getsource(ai.deep_analyze_text)
        self.assertNotIn('max_tokens=2400', src)
        self.assertIn('max_tokens=4096', src)


if __name__ == '__main__':
    unittest.main()
