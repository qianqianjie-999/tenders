#!/usr/bin/env python3
"""
项目功能测试脚本
测试 Flask API 和 Scrapy 爬虫
"""
import sys
import os
import subprocess
import time
import requests

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'flask_web'))

BASE_URL = 'http://127.0.0.1:5000'
PASSED = 0
FAILED = 0


def ok(name, msg=""):
    global PASSED
    PASSED += 1
    print(f"  ✅ {name}" + (f" - {msg}" if msg else ""))


def fail(name, err):
    global FAILED
    FAILED += 1
    print(f"  ❌ {name}: {err}")


def test_flask_api():
    """测试 Flask API 端点"""
    print("\n" + "=" * 60)
    print("📋 Flask API 测试")
    print("=" * 60)

    tests = [
        ("GET /", lambda: requests.get(f"{BASE_URL}/", timeout=5)),
        ("GET /api/data", lambda: requests.get(f"{BASE_URL}/api/data?date=2026-03-01&page=1&page_size=5", timeout=10)),
        ("GET /api/categories", lambda: requests.get(f"{BASE_URL}/api/categories", timeout=5)),
        ("GET /api/sources", lambda: requests.get(f"{BASE_URL}/api/sources", timeout=5)),
        ("GET /api/keywords", lambda: requests.get(f"{BASE_URL}/api/keywords", timeout=5)),
        ("GET /dashboard", lambda: requests.get(f"{BASE_URL}/dashboard", timeout=5)),
        ("GET /focus/", lambda: requests.get(f"{BASE_URL}/focus/", timeout=5)),
        ("GET /focus/api/list", lambda: requests.get(f"{BASE_URL}/focus/api/list?page=1&page_size=5", timeout=5)),
        ("GET /analysis/", lambda: requests.get(f"{BASE_URL}/analysis/", timeout=5)),
        ("GET /analysis/api/list", lambda: requests.get(f"{BASE_URL}/analysis/api/list?page=1&page_size=5", timeout=5)),
        ("GET /bidding/", lambda: requests.get(f"{BASE_URL}/bidding/", timeout=5)),
        ("GET /bidding/api/list", lambda: requests.get(f"{BASE_URL}/bidding/api/list?page=1&page_size=5", timeout=5)),
        ("GET /monitor/", lambda: requests.get(f"{BASE_URL}/monitor/", timeout=5)),
        ("GET /monitor/api/stats", lambda: requests.get(f"{BASE_URL}/monitor/api/stats", timeout=5)),
        ("GET /monitor/api/spiders", lambda: requests.get(f"{BASE_URL}/monitor/api/spiders", timeout=5)),
        ("GET /design/api/list", lambda: requests.get(f"{BASE_URL}/design/api/list", timeout=5)),
        ("GET /audit/api/list", lambda: requests.get(f"{BASE_URL}/audit/api/list", timeout=5)),
    ]

    for name, fn in tests:
        try:
            r = fn()
            if r.status_code == 200:
                ok(name, f"status={r.status_code}")
            else:
                fail(name, f"status={r.status_code}")
        except Exception as e:
            fail(name, str(e))


def test_scrapy_spiders():
    """测试 Scrapy 爬虫（限制抓取量）"""
    print("\n" + "=" * 60)
    print("🕷️ Scrapy 爬虫测试 (CLOSESPIDER_PAGECOUNT=1 或 ITEMCOUNT=3)")
    print("=" * 60)

    spider_dir = os.path.join(os.path.dirname(__file__), 'scrapy_spider', 'bidding_spider')
    venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python')

    spiders = [
        ('sd_post', '-s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=INFO'),
        ('jining_get', '-s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=INFO'),
        ('jinan_post', '-s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=INFO'),
        ('taian_post', '-s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=INFO'),
        ('zibo_post', '-s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=INFO'),
    ]

    for spider_name, extra_args in spiders:
        try:
            cmd = f'cd "{spider_dir}" && {venv_python} -m scrapy crawl {spider_name} {extra_args}'
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=spider_dir,
                env={**os.environ, 'PATH': os.environ.get('PATH', '')}
            )
            if result.returncode == 0:
                ok(f"爬虫 {spider_name}", "运行成功")
            else:
                fail(f"爬虫 {spider_name}", f"exit={result.returncode}, stderr={result.stderr[:200] if result.stderr else 'N/A'}")
        except subprocess.TimeoutExpired:
            fail(f"爬虫 {spider_name}", "超时")
        except Exception as e:
            fail(f"爬虫 {spider_name}", str(e))


def main():
    print("\n" + "=" * 60)
    print("🧪 tenders 项目功能测试")
    print("=" * 60)

    # 1. 检查 Flask 是否已运行
    try:
        r = requests.get(f"{BASE_URL}/", timeout=2)
        print("\n✅ Flask 服务已运行，开始 API 测试...")
    except requests.exceptions.RequestException:
        print("\n⚠️ Flask 未运行，请先启动: cd flask_web && python run.py")
        print("   或在本终端运行: cd flask_web && python run.py &")
        print("\n跳过 Flask API 测试，仅运行爬虫测试...")
        test_scrapy_spiders()
        print_summary()
        return

    # 2. 运行 Flask API 测试
    test_flask_api()

    # 3. 运行爬虫测试
    test_scrapy_spiders()

    print_summary()


def print_summary():
    print("\n" + "=" * 60)
    print(f"📊 测试结果: 通过 {PASSED} / 失败 {FAILED} / 总计 {PASSED + FAILED}")
    print("=" * 60)
    sys.exit(0 if FAILED == 0 else 1)


if __name__ == '__main__':
    main()
