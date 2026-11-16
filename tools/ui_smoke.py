#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 分析模块浏览器 UI 实测（playwright + 系统 Chrome）。

验证项：
  1. /ai-analysis/ 页面渲染、模型健康状态、统计卡片、列表数据
  2. 详情弹窗能否打开并显示 AI 结论字段
  3. /focus/ 转单弹窗能否弹出（X-Access-Code 二次校验入口）
  4. 捕获 console / network 错误（尤其 CDN 静态资源是否可达）

用法：python tools/ui_smoke.py [--headed]
产物：docs/ui_smoke/*.png
"""
import os
import sys
import json

os.environ.setdefault('HOME', '/home/qianqianjie')
_TMP = '/home/qianqianjie/mountSysdisk/tmp'
os.makedirs(_TMP, exist_ok=True)
os.environ['TMPDIR'] = _TMP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'ui_smoke')
os.makedirs(OUT, exist_ok=True)
ENV_FILE = '/home/qianqianjie/tenders/.env'
BASE = 'http://127.0.0.1:5000'
PY_DEPLOY = '/home/qianqianjie/tenders/venv/bin/python'


def load_env():
    env = {}
    for line in open(ENV_FILE):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def make_cookie(secret_key, user_id='1'):
    """用部署 venv 的 Flask 生成签名 session（本脚本环境可能没有 flask）。"""
    code = (
        'import sys;from flask import Flask;'
        'from flask.sessions import SecureCookieSessionInterface;'
        'app=Flask(__name__);app.secret_key=sys.argv[1];'
        'print(SecureCookieSessionInterface().get_signing_serializer(app)'
        '.dumps({"_user_id":sys.argv[2],"_fresh":True}))'
    )
    import subprocess
    out = subprocess.run([PY_DEPLOY, '-c', code, secret_key, user_id],
                         capture_output=True, text=True, env=dict(os.environ))
    if out.returncode != 0:
        raise RuntimeError('cookie 生成失败: ' + out.stderr[-300:])
    return out.stdout.strip()


def main():
    headed = '--headed' in sys.argv
    env = load_env()
    cookie = make_cookie(env['SECRET_KEY'])

    from playwright.sync_api import sync_playwright

    report = {'checks': [], 'console_errors': [], 'failed_requests': []}

    def check(name, ok, detail=''):
        report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:200]})
        print(('  [PASS] ' if ok else '  [FAIL] ') + name + ((' | ' + str(detail)[:120]) if detail else ''))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=not headed,
                                    args=['--no-sandbox', '--disable-dev-shm-usage'])
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        page = ctx.new_page()
        page.on('console', lambda m: report['console_errors'].append(m.text)
                if m.type == 'error' else None)
        page.on('requestfailed', lambda r: report['failed_requests'].append(
            '%s %s' % (r.url[:120], (r.failure or '')[:60])))

        print('== 1. /ai-analysis/ 页面 ==')
        page.goto(BASE + '/ai-analysis/', wait_until='domcontentloaded', timeout=40000)
        try:
            page.wait_for_selector('#statsRow .stat-card', timeout=20000)
        except Exception as e:
            check('统计卡片渲染', False, e)

        cards = page.locator('#statsRow .stat-card').count()
        check('统计卡片渲染', cards >= 3, '卡片数=%d' % cards)

        model_label = (page.locator('#modelLabel').inner_text() or '').strip()
        check('模型状态文案', 'qwen' in model_label or '在线' in model_label, model_label)

        alert_visible = page.locator('#modelAlert').is_visible()
        check('模型异常提示未误报', not alert_visible, 'alert可见=%s' % alert_visible)

        rows = page.locator('#listContainer tbody tr[data-table]').count()
        check('列表有数据', rows > 0, '行数=%d' % rows)

        css_ok = page.evaluate(
            "() => { const b=document.querySelector('.btn'); if(!b) return 'no-btn';"
            " return getComputedStyle(b).borderRadius; }")
        check('样式已生效(非裸HTML)', css_ok not in ('0px', 'no-btn'), 'btn radius=%s' % css_ok)
        page.screenshot(path=os.path.join(OUT, '01_ai_analysis.png'), full_page=False)

        print('== 2. 详情弹窗 ==')
        opened = False
        try:
            page.locator('#listContainer tbody tr[data-table]').first.click(timeout=8000)
            page.wait_for_selector('#detailModal.show', timeout=15000)
            opened = page.locator('#detailModal').is_visible()
        except Exception as e:
            detail = str(e)[:120]
        body_text = page.locator('#detailModal').inner_text() if opened else ''
        check('详情弹窗打开', opened, '' if opened else '未能打开')
        if opened:
            has_field = any(k in body_text for k in ('预算', '采购人', '资质', '摘要'))
            check('弹窗内显示 AI 字段', has_field, body_text[:80].replace('\n', ' '))
            page.screenshot(path=os.path.join(OUT, '02_detail_modal.png'))
            page.keyboard.press('Escape')

        print('== 3. /focus/ 转单弹窗 ==')
        page.goto(BASE + '/focus/', wait_until='domcontentloaded', timeout=40000)
        page.wait_for_timeout(1500)
        txt = page.content()
        check('转单按钮存在', '转入分析' in txt or 'moveToAnalysis' in txt, '')
        btn = page.locator("[onclick*='moveToAnalysis'], [data-action='transfer']").first
        if btn.count() > 0:
            try:
                btn.click(timeout=8000)
                page.wait_for_timeout(1200)
                modal_txt = page.content()
                has_code = 'access' in modal_txt.lower() and 'code' in modal_txt.lower()
                check('转单二次校验弹窗', has_code, 'code输入框出现=%s' % has_code)
                page.screenshot(path=os.path.join(OUT, '03_transfer_modal.png'))
            except Exception as e:
                check('转单二次校验弹窗', False, str(e)[:120])
        else:
            check('转单二次校验弹窗', False, '未找到按钮')

        browser.close()

    print('\n== console 错误 (%d) ==' % len(report['console_errors']))
    for e in report['console_errors'][:8]:
        print('   -', e[:160])
    print('== 失败请求 (%d) ==' % len(report['failed_requests']))
    for e in report['failed_requests'][:8]:
        print('   -', e[:160])

    json.dump(report, open(os.path.join(OUT, 'report.json'), 'w'),
              ensure_ascii=False, indent=2)
    passed = sum(1 for c in report['checks'] if c['ok'])
    print('\n结果: %d/%d 通过' % (passed, len(report['checks'])))
    return 0 if passed == len(report['checks']) else 1


if __name__ == '__main__':
    sys.exit(main())
