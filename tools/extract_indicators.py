# -*- coding: utf-8 -*-
"""
extract_indicators.py
=====================
从 detail_content 正文中用规则抽取 7 项核心指标：

    1. 项目名称      project_name
    2. 采购方式      method
    3. 预算金额      budget_text / budget_value(元)
    4. 投标截止时间  deadline (DATETIME)
    5. 资格要求      qualification
    6. 招标人        purchaser
    7. 发布日期      publish_date（直接取库字段，不抽取）

只做规则抽取，不调用 AI。抽不到的留 NULL，后续交给 AI 兜底。

用法：
    python tools/extract_indicators.py --days 7 --limit 50 --dry-run
    python tools/extract_indicators.py --days 7 --limit 50 --write
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
TABLES = ('bidding_info', 'jiangsu_bidding_info', 'zhejiang_bidding_info')


def _load_env():
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


_load_env()


def get_conn():
    return pymysql.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        user=os.getenv('DB_USER', 'bidding_user'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'bidding_db'),
        port=int(os.getenv('DB_PORT', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )


# ------------------------------------------------------------------ 正则
# 金额：各地区表述不同（江苏=预算/最高限价，浙江=工程造价，山东=估算价/投资额）
AMOUNT_KEY = (r'(?:预算金额|采购预算|项目预算|合同估算价|估算价|招标控制价|最高限价|'
              r'控制价|工程造价|项目总投资|投资额|总投资|预算)')
AMOUNT_RE = re.compile(
    AMOUNT_KEY + r'[^0-9]{0,15}([0-9][0-9,，]*(?:\.[0-9]+)?\s*(?:亿元|万元|万|元))'
)
MONEY_RE = re.compile(r'([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(亿元|万元|万|元)')

METHOD_RE = re.compile(r'(?:采\s*购\s*方\s*式|招\s*标\s*方\s*式|交\s*易\s*方\s*式)\s*[：:]\s*([^\s，,。；;、\n]{2,20})')

# 浙江 PDF：`4. 招投标方式 \n 4.1 公开招标。`（值在下一行，带编号）
METHOD_RE2 = re.compile(
    r'招\s*投\s*标\s*方\s*式\s*[：:]?\s*(?:\n\s*)?(?:\d+(?:\.\d+)*\s*)?([^\n，,。；;]{2,20})'
)

# 正文常不写「采购方式：」，用标题关键词兜底
METHOD_KEYWORDS = (
    ('竞争性磋商', '竞争性磋商'), ('竞争性谈判', '竞争性谈判'), ('单一来源', '单一来源'),
    ('询价', '询价'), ('邀请招标', '邀请招标'), ('公开招标', '公开招标'),
    ('框架协议', '框架协议'), ('竞价', '竞价'), ('比选', '比选'),
)

NAME_RE = re.compile(r'(?:项目名称|招标名称|工程名称|采购项目名称)\s*[：:]\s*([^\n]{2,120})')

DATE = r'(20\d{2})\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})\s*[日号]?'
TIME = r'(?:[^0-9\n]{0,8})?(\d{1,2})\s*[:：时]\s*(\d{1,2})'
DEADLINE_RE = re.compile(
    r'(?:投标|响应|递交|提交|申请|报名)[^\n。；;]{0,20}?截止(?:时间|日期)?[^\n。；;：:]{0,8}[：:]?\s*'
    + DATE + r'(?:[^0-9\n]{0,10}' + TIME + r')?'
)
OPEN_RE = re.compile(
    r'开标(?:时间|日期)[^\n。；;：:]{0,8}[：:]?\s*' + DATE + r'(?:[^0-9\n]{0,10}' + TIME + r')?'
)

QUAL_RE = re.compile(r'(?:投标人|申请人|供应商)?资格(?:要求|条件)|资质要求|投标人资格')

# 招标人：山东/浙江多用「招标人：」，江苏用「采购人信息 名称：」
PURCHASER_RE = re.compile(
    r'(?:招\s*标\s*人|采\s*购\s*人|招\s*标\s*单\s*位|采\s*购\s*单\s*位|建\s*设\s*单\s*位)'
    r'\s*(?:信\s*息)?\s*[：:]\s*([^\n]{2,80})'
)
NAME_AFTER_RE = re.compile(r'名\s*称\s*[：:]\s*([^\n]{2,80})')
_PURCHASER_CUT = re.compile(r'\s{2,}|地址|地\s*址|联系人|联系电话|电话|邮编|统一社会信用代码')


def extract_purchaser(text: str):
    m = PURCHASER_RE.search(text)
    if m:
        raw = m.group(1)
    else:
        pos = text.find('采购人信息')
        if pos < 0:
            pos = text.find('招标人信息')
        if pos < 0:
            return None
        m2 = NAME_AFTER_RE.search(text, pos, pos + 300)
        if not m2:
            return None
        raw = m2.group(1)
    raw = _PURCHASER_CUT.split(raw)[0]
    raw = re.sub(r'\s+', '', raw).strip(' ：:，,。')
    return raw if 2 <= len(raw) <= 80 else None


def _norm_money(num: str, unit: str):
    """把 '380.000000万元' 归一为元，返回 (float, 展示文本)。"""
    try:
        v = float(num.replace(',', '').replace('，', ''))
    except ValueError:
        return None, None
    factor = {'亿元': 1e8, '万元': 1e4, '万': 1e4, '元': 1}[unit]
    return v * factor, f'{num.strip()}{unit}'


def extract_amount(text: str):
    m = AMOUNT_RE.search(text)
    if not m:
        return None, None
    mm = MONEY_RE.match(m.group(1).replace(' ', ''))
    if mm:
        val, disp = _norm_money(mm.group(1), mm.group(2))
        return disp, val
    return m.group(1).strip(), None


def _to_dt(y, mo, d, hh=None, mi=None):
    try:
        return datetime.datetime(int(y), int(mo), int(d),
                                 int(hh) if hh else 0, int(mi) if mi else 0)
    except (ValueError, TypeError):
        return None


def extract_deadline(text: str):
    for rx in (DEADLINE_RE, OPEN_RE):
        m = rx.search(text)
        if not m:
            continue
        g = m.groups()
        dt = _to_dt(g[0], g[1], g[2], g[3], g[4])
        if dt:
            return dt
    return None


def extract_method(text: str, title: str = ''):
    m = METHOD_RE.search(text) or METHOD_RE2.search(text)
    if m:
        return m.group(1).strip(' ：:，,。')
    blob = (title or '') + ' ' + (text or '')[:300]
    for kw, val in METHOD_KEYWORDS:
        if kw in blob:
            return val
    return None


def extract_name(text: str, fallback: str):
    m = NAME_RE.search(text)
    if m:
        name = re.sub(r'\s+', ' ', m.group(1)).strip(' ：:')
        if 2 <= len(name) <= 120:
            return name
    return (fallback or '').strip() or None


def extract_qualification(text: str, cap: int = 500):
    m = QUAL_RE.search(text)
    if not m:
        return None
    seg = text[m.start():m.start() + cap]
    seg = re.sub(r'\s+', ' ', seg).strip()
    return seg or None


def extract_all(title: str, content: str, publish_date=None):
    content = content or ''
    budget_text, budget_value = extract_amount(content)
    return {
        'project_name': extract_name(content, title),
        'method': extract_method(content, title),
        'budget_text': budget_text,
        'budget_value': budget_value,
        'deadline': extract_deadline(content),
        'qualification': extract_qualification(content),
        'purchaser': extract_purchaser(content),
        'publish_date': publish_date,
    }


# ------------------------------------------------------------------ 主流程
def pick_rows(conn, table, days, limit):
    cur = conn.cursor()
    cur.execute(f"""
      SELECT id, project_name, publish_date, detail_content
      FROM `{table}`
      WHERE detail_content IS NOT NULL AND CHAR_LENGTH(detail_content) >= 20
        AND publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
      ORDER BY id DESC LIMIT %s
    """, (days, limit))
    rows = cur.fetchall()
    cur.close()
    return rows


def main():
    ap = argparse.ArgumentParser(description='规则抽取 6 项核心指标')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--limit', type=int, default=50)
    ap.add_argument('--tables', default=','.join(TABLES))
    ap.add_argument('--dry-run', action='store_true', help='只统计覆盖率，不写库')
    ap.add_argument('--write', action='store_true', help='写入 ai_analysis.core')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    tables = [t.strip() for t in args.tables.split(',') if t.strip()]
    conn = get_conn()
    try:
        for table in tables:
            rows = pick_rows(conn, table, args.days, args.limit)
            if not rows:
                print(f'[{table}] 无正文数据')
                continue

            stats = {k: 0 for k in ('project_name', 'method', 'budget_text',
                                    'deadline', 'qualification', 'purchaser', 'publish_date')}
            results = []
            for r in rows:
                res = extract_all(r['project_name'], r['detail_content'], r['publish_date'])
                results.append((r['id'], res))
                for k in stats:
                    if res.get(k):
                        stats[k] += 1

            total = len(rows)
            print(f'\n[{table}] 共 {total} 条')
            for k, v in stats.items():
                print(f'   {k:14s} {v:3d}/{total}  ({v * 100 // total}%)')

            if args.verbose or args.dry_run:
                for rid, res in results[:3]:
                    print(f'   --- id={rid}')
                    for k, v in res.items():
                        print(f'       {k}: {v}')

            if args.write and not args.dry_run:
                cur = conn.cursor()
                for rid, res in results:
                    core = {k: (v.isoformat(sep=' ') if isinstance(v, datetime.datetime) else v)
                            for k, v in res.items()}
                    cur.execute(f"""
                      UPDATE `{table}`
                      SET ai_analysis = JSON_SET(COALESCE(ai_analysis, JSON_OBJECT()),
                                                 '$.core', CAST(%s AS JSON))
                      WHERE id=%s
                    """, (json.dumps(core, ensure_ascii=False), rid))
                conn.commit()
                cur.close()
                print(f'   ✅ 已写入 ai_analysis.core')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
