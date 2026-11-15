# -*- coding: utf-8 -*-
"""G2 上传接口离线测试：真实路由函数 + mock 数据库连接，不写业务库。

运行：python3 -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault('SECRET_KEY', 'spec-local-test-only')
# werkzeug 构造 multipart 会写临时文件；本机 /tmp 是 10MB tmpfs，
# 超大文件用例必须先把临时目录指向大分区（与生产长稳项同一处理）
_BIG_TMP = '/home/qianqianjie/mountDisk/tenders_wheels/tmp'
if os.path.isdir(_BIG_TMP):
    os.environ['TMPDIR'] = _BIG_TMP
    tempfile.tempdir = _BIG_TMP
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))

from flask import Flask, request  # noqa: E402
from app.routes import ai_analysis as routes  # noqa: E402
from app.decorators import require_auth_write  # noqa: E402
from app.services import analysis_bridge_service as bridge  # noqa: E402

_SAMPLE_PDF = os.path.join(
    '/home/qianqianjie/mountDisk/tenders_wheels/probe', 'sample.pdf')


class FakeCursor(object):
    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def execute(self, sql, params=None):
        s = sql.strip()
        if s.startswith('SELECT'):
            self._row = ({'analysis_content': self.conn.existing}
                         if self.conn.exists else None)
        elif s.startswith('UPDATE'):
            self.conn.updates.append((s, params))

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn(object):
    def __init__(self, existing='', exists=True):
        self.existing = existing
        self.exists = exists
        self.updates = []
        self.committed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        pass


class UploadRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'

    def _call(self, body, filename, existing='', exists=True):
        conn = FakeConn(existing, exists)
        with mock.patch.object(routes, 'get_db_connection', return_value=conn):
            with self.app.test_request_context(
                    method='POST',
                    data={'file': (io.BytesIO(body), filename)},
                    content_type='multipart/form-data'):
                request.auth_user = 'tester'
                # 绕过 require_auth_write（鉴权另有专门用例）；函数体仍是真实实现
                resp = routes.api_upload_source.__wrapped__(171)
        if isinstance(resp, tuple):
            payload = resp[0].get_json()
            status = resp[1]
        else:
            payload = resp.get_json()
            status = resp.status_code
        return payload, status, conn

    def test_chinese_pdf_extracts_text(self):
        """A7：上传中文 PDF 能提取文本并追加，且总字节受限。"""
        if not os.path.exists(_SAMPLE_PDF):
            self.skipTest('中文 PDF 样本不存在（需先跑设计规格 §0.2 探针）')
        with open(_SAMPLE_PDF, 'rb') as f:
            body = f.read()
        payload, status, conn = self._call(body, 'notice.pdf')
        self.assertEqual(status, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['kind'], 'pdf')
        self.assertGreater(payload['data']['extracted_chars'], 50)
        self.assertLessEqual(payload['data']['stored_bytes'], bridge.MAX_CONTENT_BYTES)
        self.assertTrue(conn.committed)
        self.assertEqual(len(conn.updates), 1)
        written = conn.updates[0][1][0]
        self.assertIn('汶上县', written)
        self.assertIn('210000', written)

    def test_existing_manual_content_is_preserved(self):
        payload, status, conn = self._call(
            '公告正文纯文本内容'.encode('utf-8'), 'a.txt', existing='人工结论：不投')
        self.assertEqual(status, 200)
        written = conn.updates[0][1][0]
        self.assertTrue(written.startswith('人工结论：不投'))
        self.assertIn('公告正文纯文本内容', written)

    def test_utf8_text_upload(self):
        payload, status, conn = self._call(
            '预算 20万元\n截止 2026-11-26 09:30'.encode('utf-8'), 'body.txt')
        self.assertEqual(status, 200)
        self.assertEqual(payload['data']['kind'], 'text')
        self.assertIn('20万元', conn.updates[0][1][0])

    def test_unsupported_binary_rejected(self):
        payload, status, conn = self._call(b'\x00\x01\x02\xff\xfe', 'x.bin')
        self.assertEqual(status, 400)
        self.assertFalse(payload['success'])
        self.assertEqual(conn.updates, [])

    def test_empty_file_rejected(self):
        payload, status, conn = self._call(b'', 'empty.pdf')
        self.assertEqual(status, 400)

    def test_oversize_rejected(self):
        """用内存 FileStorage 构造超限值，避免 werkzeug multipart 写临时文件。"""
        from werkzeug.datastructures import FileStorage
        fs = FileStorage(stream=io.BytesIO(b'x' * (routes.MAX_UPLOAD_BYTES + 1)),
                         filename='huge.pdf')
        conn = FakeConn()
        with mock.patch.object(routes, 'get_db_connection', return_value=conn):
            with self.app.test_request_context(method='POST'):
                request.files = {'file': fs}
                request.auth_user = 'tester'
                resp = routes.api_upload_source.__wrapped__(171)
        payload = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
        status = resp[1] if isinstance(resp, tuple) else resp.status_code
        self.assertEqual(status, 413)
        self.assertFalse(payload['success'])

    def test_missing_analysis_record(self):
        payload, status, conn = self._call('正文'.encode('utf-8'), 'a.txt',
                                           exists=False)
        self.assertEqual(status, 404)

    def test_safe_filename_strips_path(self):
        self.assertEqual(routes._safe_filename('../../etc/passwd'), 'passwd')
        self.assertEqual(routes._safe_filename('<script>.pdf'), 'script.pdf')


class AuthTests(unittest.TestCase):
    """A6：写入接口必须登录 + 访问口令双门槛。"""

    def setUp(self):
        from flask_login import LoginManager
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.config['ANALYSIS_ACCESS_CODE'] = 'kwd12345'
        lm = LoginManager()
        lm.init_app(self.app)  # current_user 需要 login_manager
        lm.user_loader(lambda uid: None)  # 测试环境无用户库，恒为匿名

        @require_auth_write
        def probe():
            from flask import jsonify
            return jsonify({'success': True})

        self.probe = probe

    def _status(self, headers=None, query=''):
        with self.app.test_request_context('/x' + query, headers=headers or {}):
            resp = self.probe()
            return resp[1] if isinstance(resp, tuple) else resp.status_code

    def test_no_credentials_is_401(self):
        self.assertEqual(self._status(), 401)

    def test_access_code_alone_is_401(self):
        self.assertEqual(self._status({'X-Access-Code': 'kwd12345'}), 401)

    def test_wrong_access_code_is_401(self):
        self.assertEqual(self._status({'X-Access-Code': 'wrong'}), 401)


if __name__ == '__main__':
    unittest.main()
