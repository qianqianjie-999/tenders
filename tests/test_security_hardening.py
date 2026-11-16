import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import create_app
from app.models.user import User, login_manager
from app.routes.auth import _is_safe_redirect_url
from app.services.monitor_service import MonitorService
from app.utils.helpers import highlight_keywords
from app.utils.security import validate_password_policy


class SecurityHardeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_patch = patch("app.init_db_pool")
        cls.db_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.current_user = None
        cls.user_callback_patch = patch.object(
            login_manager,
            "_user_callback",
            side_effect=lambda user_id: cls.current_user,
        )
        cls.user_callback_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.user_callback_patch.stop()
        cls.db_patch.stop()

    def authenticate(self, role="user"):
        client = self.app.test_client()
        base_url = "https://localhost"
        login_page = client.get("/auth/login", base_url=base_url)
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login_page.data,
        )
        self.assertIsNotNone(token_match)
        row = {
            "id": 1,
            "username": "security-tester",
            "password_hash": "unused",
            "role": role,
            "is_active": 1,
        }
        type(self).current_user = User(row)
        with (
            patch(
                "app.services.user_service.UserService.get_by_username",
                return_value=row,
            ),
            patch("app.models.user.User.check_password", return_value=True),
            patch("app.routes.auth._login_guard.reset"),
        ):
            response = client.post(
                "/auth/login",
                data={
                    "csrf_token": token_match.group(1).decode(),
                    "username": "security-tester",
                    "password": "test-password",
                },
                headers={"Referer": f"{base_url}/auth/login"},
                base_url=base_url,
            )
        self.assertEqual(response.status_code, 302)
        return client

    def test_business_api_defaults_to_unauthenticated_denial(self):
        response = self.app.test_client().get("/api/data")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_business_page_redirects_anonymous_user_to_login(self):
        response = self.app.test_client().get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["Location"])

    def test_health_check_remains_public(self):
        response = self.app.test_client().get(
            "/api/monitor/health",
            base_url="https://localhost",
        )

        self.assertEqual(response.status_code, 200)

    def test_valid_password_is_not_blocked_by_attacker_lockout(self):
        client = self.app.test_client()
        base_url = "https://localhost"
        login_page = client.get("/auth/login", base_url=base_url)
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login_page.data,
        )
        row = {
            "id": 1,
            "username": "locked-admin",
            "password_hash": "unused",
            "role": "admin",
            "is_active": 1,
        }
        type(self).current_user = User(row)
        with (
            patch(
                "app.services.user_service.UserService.get_by_username",
                return_value=row,
            ),
            patch("app.models.user.User.check_password", return_value=True),
            patch(
                "app.routes.auth._login_guard.is_locked",
                return_value=(True, 240),
            ),
            patch("app.routes.auth._login_guard.reset"),
        ):
            response = client.post(
                "/auth/login",
                data={
                    "csrf_token": token_match.group(1).decode(),
                    "username": "locked-admin",
                    "password": "valid-password",
                },
                headers={"Referer": f"{base_url}/auth/login"},
                base_url=base_url,
            )

        self.assertEqual(response.status_code, 302)

    def test_session_cookies_are_secure(self):
        self.assertTrue(self.app.config["SESSION_COOKIE_SECURE"])
        self.assertTrue(self.app.config["REMEMBER_COOKIE_SECURE"])

    def test_security_headers_are_set(self):
        response = self.app.test_client().get(
            "/auth/login",
            base_url="https://localhost",
        )

        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(
            response.headers["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertEqual(
            response.headers["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )

    def test_access_code_has_no_hardcoded_runtime_default(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.config import Config; print(Config.ANALYSIS_ACCESS_CODE)",
            ],
            env={
                key: value
                for key, value in os.environ.items()
                if key != "ANALYSIS_ACCESS_CODE"
            },
            cwd=str(Path(__file__).resolve().parents[1] / "flask_web"),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(result.stdout.strip(), "None")

    def test_log_reader_rejects_path_traversal(self):
        old_root = MonitorService.SPIDER_ROOT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                logs_dir = root / "logs"
                logs_dir.mkdir()
                (logs_dir / "safe.log").write_text("safe", encoding="utf-8")
                (root / "secret.txt").write_text("secret", encoding="utf-8")
                MonitorService.SPIDER_ROOT = root

                result = MonitorService.get_log_file_content("../secret.txt")

                self.assertFalse(result["success"])
                self.assertNotIn("secret", result)
        finally:
            MonitorService.SPIDER_ROOT = old_root

    def test_highlight_keywords_escapes_scraped_html(self):
        rendered = highlight_keywords(
            '<img src=x onerror=alert(1)>交通项目',
            ["交通"],
        )

        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertIn('<span class="highlight-keyword"', rendered)

    def test_monitor_routes_are_admin_only(self):
        client = self.authenticate(role="user")
        with patch(
            "app.routes.monitor.MonitorService.get_log_files",
            return_value={"success": True, "logs": []},
        ):
            response = client.get(
                "/monitor/api/logs",
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 403)

    def test_monitor_start_rejects_unlisted_spider(self):
        client = self.authenticate(role="admin")
        original = self.app.config["WTF_CSRF_ENABLED"]
        self.app.config["WTF_CSRF_ENABLED"] = False
        try:
            with patch(
                "app.routes.monitor.MonitorService.execute_spider",
                return_value={"success": True},
            ) as execute:
                response = client.post(
                    "/monitor/api/start",
                    json={"spider_name": "../../not-a-spider"},
                    base_url="https://localhost",
                )
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = original

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_monitor_stop_rejects_non_spider_process(self):
        client = self.authenticate(role="admin")
        process = MagicMock()
        process.cmdline.return_value = ["/usr/bin/python3", "-m", "http.server"]
        original = self.app.config["WTF_CSRF_ENABLED"]
        self.app.config["WTF_CSRF_ENABLED"] = False
        try:
            with patch("psutil.Process", return_value=process):
                response = client.post(
                    "/monitor/api/stop",
                    json={"pid": 123},
                    base_url="https://localhost",
                )
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = original

        self.assertEqual(response.status_code, 400)
        process.terminate.assert_not_called()

    def test_keyword_mutation_requires_csrf(self):
        client = self.authenticate(role="admin")
        with patch(
            "app.routes.main.KeywordService.add_keyword",
            return_value=(True, "created"),
        ):
            response = client.post(
                "/api/keywords",
                json={"keyword": "安全测试", "category": "general"},
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 400)

    def test_focus_track_requires_csrf(self):
        client = self.authenticate(role="user")
        with patch(
            "app.routes.focus.FocusService.add_track",
            return_value=1,
        ):
            response = client.post(
                "/focus/api/tracks/1",
                json={"content": "安全测试"},
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 400)

    def test_short_password_is_rejected(self):
        errors = validate_password_policy("Ab1!short")

        self.assertTrue(errors)

    def test_long_passphrase_is_accepted(self):
        errors = validate_password_policy("correct horse battery staple")

        self.assertEqual(errors, [])

    def test_login_redirect_rejects_scheme_relative_external_url(self):
        self.assertFalse(_is_safe_redirect_url("//evil.example/path"))
        self.assertTrue(_is_safe_redirect_url("/dashboard"))


if __name__ == "__main__":
    unittest.main()
