#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 分析覆盖率诊断与全量回填（命令行，不走 Web 请求）。

背景：后台批量按钮每轮每表只跑 20 条、只取最近 3 天；三张主表共 700+ 条
待分析记录靠人工点按钮跑不完。同时 ai_analysis 列里混有爬虫写入的
{"source": {...}} 元数据，按「字段非空」算覆盖率会虚高十几倍。

用法（部署 venv 下运行）：
    python tools/ai_coverage.py report
    python tools/ai_coverage.py backfill                 # 默认只出计划，不写库
    python tools/ai_coverage.py backfill --execute --per-table 100

约定：
  * report 全程只读，不建 app context、不调模型。
  * backfill 未带 --execute 时是 dry-run；模型主机关机时直接退出，
    一条 failed 都不写（复用 G3 降级）。
"""
import argparse
import datetime
import json
import os
import sys
from collections import OrderedDict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'flask_web'))

MAIN_TABLES = ('bidding_info', 'jiangsu_bidding_info', 'zhejiang_bidding_info')
# normalize_analysis() 的固定输出字段；出现任一即视为真结论，
# 不能被 {"source": ...} / {"error": ...} 占位混进覆盖率。
RESULT_KEYS = (
    'project_name', 'purchaser', 'agency', 'budget', 'deadline',
    'qualification', 'summary', 'relevance', 'categories', 'risk',
    'compliance', 'scoring',
)


def load_env(path=None):
    """把 .env 注入 os.environ（已有值优先，不覆盖）。返回实际读取的文件。"""
    candidates = [
        path,
        os.environ.get('TENDERS_ENV'),
        os.path.join(_ROOT, '.env'),
        '/home/qianqianjie/tenders/.env',
    ]
    for p in candidates:
        if not p or not os.path.isfile(p):
            continue
        with open(p, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
        return p
    return None


def db_connect():
    import pymysql
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 3306) or 3306),
        user=os.environ.get('DB_USER', 'bidding_user'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'bidding_db'),
        charset=os.environ.get('DB_CHARSET', 'utf8mb4'),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def as_dict(v):
    """ai_analysis 在 MariaDB 里是 JSON 列，经 pymysql 可能已是 dict 或仍是 str。"""
    if isinstance(v, dict):
        return v
    if isinstance(v, (bytes, bytearray)):
        v = v.decode('utf-8', 'ignore')
    if isinstance(v, str) and v.strip():
        try:
            obj = json.loads(v)
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def classify_ai_payload(v):
    """区分真结论与占位内容。返回 valid/source_only/error/empty/unknown。

    真结论可能同时带 source（save_analysis 会合并抓取元数据），所以先判
    RESULT_KEYS；只有 source 而无结论字段的，是爬虫阶段写入的元数据占位。
    """
    obj = as_dict(v)
    if not obj:
        return 'empty'
    if any(k in obj for k in RESULT_KEYS):
        return 'valid'
    if 'error' in obj:
        return 'error'
    if 'source' in obj:
        return 'source_only'
    return 'unknown'


def summarize_rows(rows):
    """纯函数：按有效结论口径汇总一张表。便于单测，不需要数据库。"""
    s = {
        'total': 0, 'has_content': 0, 'valid': 0, 'ok_valid': 0,
        'source_only': 0, 'error': 0, 'empty': 0, 'unknown': 0,
        'pending_with_content': 0,
    }
    for r in rows:
        s['total'] += 1
        has_content = bool(r.get('has_content'))
        status = (r.get('status') or '').lower()
        kind = classify_ai_payload(r.get('payload'))
        if has_content:
            s['has_content'] += 1
        s[kind] += 1
        if kind == 'valid' and status == 'ok':
            s['ok_valid'] += 1
        if has_content and status != 'ok':
            s['pending_with_content'] += 1
    return s


def fetch_rows(conn, table):
    cur = conn.cursor()
    # 不做跨表比较（主表 utf8mb4_unicode_ci / analysis utf8mb4_general_ci 会报 1267）
    cur.execute(
        "SELECT id, project_name, publish_date, detail_url, ai_analysis, "
        "ai_analysis_status, "
        "(detail_content IS NOT NULL AND TRIM(detail_content) <> '') AS has_content "
        "FROM `%s`" % table)
    raw = cur.fetchall()
    cur.close()
    # 统一成汇总/命中统计用的字段名，避免与数据库列名耦合
    return [{
        'id': r['id'],
        'project_name': r.get('project_name'),
        'publish_date': r.get('publish_date'),
        'detail_url': r.get('detail_url'),
        'payload': r.get('ai_analysis'),
        'status': r.get('ai_analysis_status') or '',
        'has_content': bool(r.get('has_content')),
    } for r in raw]


def g1_hit_stats(conn, main_rows):
    """G1 转单回填可命中基数：内存比对，避开跨表 collation 冲突。"""
    by_url = set()
    by_name_date = set()
    for table, rows in main_rows.items():
        for r in rows:
            if (r.get('status') or '').lower() != 'ok':
                continue
            if classify_ai_payload(r.get('payload')) != 'valid':
                continue
            url = (r.get('detail_url') or '').strip()
            if url:
                by_url.add((table, url))
            if r.get('project_name') and r.get('publish_date'):
                by_name_date.add((str(r['project_name']).strip(), str(r['publish_date'])))

    cur = conn.cursor()
    cur.execute("SELECT id, project_name, publish_date, detail_url FROM analysis_projects")
    ana = cur.fetchall()
    cur.execute("SELECT MIN(publish_date) AS lo, MAX(publish_date) AS hi FROM analysis_projects")
    rng = cur.fetchone() or {}
    cur.close()

    hit_url = hit_name = 0
    for r in ana:
        url = (r.get('detail_url') or '').strip()
        if url and any((t, url) in by_url for t in MAIN_TABLES):
            hit_url += 1
            continue
        key = (str(r.get('project_name') or '').strip(), str(r.get('publish_date') or ''))
        if key[0] and key[1] and key in by_name_date:
            hit_name += 1
    return {
        'analysis_total': len(ana),
        'analysis_range': '%s ~ %s' % (rng.get('lo'), rng.get('hi')),
        'ok_pool': len(by_url),
        'hit_url': hit_url,
        'hit_name_date': hit_name,
        'hit_any': hit_url + hit_name,
    }


def cmd_report(args):
    conn = db_connect()
    try:
        main_rows = OrderedDict()
        stats = OrderedDict()
        for t in MAIN_TABLES:
            rows = fetch_rows(conn, t)
            main_rows[t] = rows
            stats[t] = summarize_rows(rows)
        g1 = g1_hit_stats(conn, main_rows)
        main_range = conn_range(conn)
        health = probe_health()
    finally:
        conn.close()
    render(stats, g1, main_range, health)
    return 0


def conn_range(conn):
    cur = conn.cursor()
    ranges = []
    for t in MAIN_TABLES:
        cur.execute("SELECT MIN(publish_date) AS lo, MAX(publish_date) AS hi FROM `%s`" % t)
        r = cur.fetchone() or {}
        if r.get('lo'):
            ranges.append('%s~%s' % (r['lo'], r['hi']))
    cur.close()
    return ' / '.join(ranges)


def probe_health():
    """只读探测；失败不阻断 report。"""
    try:
        from app.services import ai_analyzer_service as ai
        return ai.check_model_health(force=True, timeout=3.0)
    except Exception as e:
        return {'status': 'unknown', 'message': '%s: %s' % (type(e).__name__, e),
                'model': os.environ.get('AI_MODEL', 'qwen3.8:27b')}


def render(stats, g1, main_range, health):
    print('=== AI 分析覆盖率诊断  %s ===' %
          datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('模型  : %s @ %s' % (health.get('model', '?'),
                              os.environ.get('AI_BASE_URL', 'http://127.0.0.1:11434/v1')))
    print('健康  : %s (%s)' % (health.get('status'), health.get('message', '')))
    print()
    head = ('%-24s %7s %8s %9s %8s %11s %9s %9s' %
            ('表', '总数', '有正文', '有效结论', '覆盖率', '源数据占位', '失败占位', '待分析'))
    print(head)
    print('-' * len(head))
    tot = {k: 0 for k in ('total', 'has_content', 'valid', 'ok_valid',
                          'source_only', 'error', 'empty', 'unknown',
                          'pending_with_content')}
    for t, s in stats.items():
        for k in tot:
            tot[k] += s[k]
        rate = 100.0 * s['ok_valid'] / s['total'] if s['total'] else 0.0
        print('%-24s %7d %8d %9d %7.1f%% %11d %9d %9d' %
              (t, s['total'], s['has_content'], s['ok_valid'], rate,
               s['source_only'], s['error'], s['pending_with_content']))
    print('-' * len(head))
    rate = 100.0 * tot['ok_valid'] / tot['total'] if tot['total'] else 0.0
    print('%-24s %7d %8d %9d %7.1f%% %11d %9d %9d' %
          ('合计', tot['total'], tot['has_content'], tot['ok_valid'], rate,
           tot['source_only'], tot['error'], tot['pending_with_content']))
    print()
    print('口径  : 有效结论 = status=ok 且 JSON 含 normalize_analysis 字段；'
          '{"source":...} 是爬虫元数据，不计入。')
    inflated = tot['source_only'] + tot['ok_valid']
    print('        按「AI 字段非空」统计会把 %d 条源数据占位一并算成结论，'
          '虚报为 %d 条 / %.1f%%。' %
          (tot['source_only'], inflated,
           100.0 * inflated / tot['total'] if tot['total'] else 0))
    print()
    print('=== G1 转单回填 ===')
    print('  analysis_projects : %d 条  %s' % (g1['analysis_total'], g1['analysis_range']))
    print('  主表发布日        : %s' % main_range)
    print('  可用结论池        : %d 条 (status=ok 且结构有效)' % g1['ok_pool'])
    print('  detail_url 命中   : %d 条 | (项目名,日期) 命中 %d 条 | 合计 %d / %d (%.1f%%)' %
          (g1['hit_url'], g1['hit_name_date'], g1['hit_any'],
           g1['analysis_total'],
           100.0 * g1['hit_any'] / g1['analysis_total'] if g1['analysis_total'] else 0))
    if g1['hit_any'] == 0:
        print('  结论            : 存量分析单与主表日期完全不相交 → 数据断档，'
              'G1 对存量永远回填不了；扩大覆盖率只对「今后新转入」有效。')
    print()
    print('=== 批量上限 ===')
    print('  后台默认 days=3 / 每表 20 条/轮；当前待分析(有正文且非ok) %d 条，'
          '约需 %d 轮才能跑完。' %
          (tot['pending_with_content'],
           max(1, (tot['pending_with_content'] + 20 * len(MAIN_TABLES) - 1)
               // (20 * len(MAIN_TABLES)))))
    print('  backfill 会跨轮循环调用 run_batch 直到清空 pending。')


def build_app():
    """run_batch 内部经 current_app.config 取 DB 配置，这里造最小 app。"""
    from flask import Flask
    app = Flask(__name__)
    app.config.update(
        DB_HOST=os.environ.get('DB_HOST', 'localhost'),
        DB_USER=os.environ.get('DB_USER', 'bidding_user'),
        DB_PASSWORD=os.environ.get('DB_PASSWORD', ''),
        DB_NAME=os.environ.get('DB_NAME', 'bidding_db'),
        DB_CHARSET=os.environ.get('DB_CHARSET', 'utf8mb4'),
        DB_PORT=int(os.environ.get('DB_PORT', 3306) or 3306),
    )
    return app


def pending_count(conn):
    cur = conn.cursor()
    n = 0
    for t in MAIN_TABLES:
        cur.execute(
            "SELECT COUNT(*) AS n FROM `%s` "
            "WHERE (ai_analysis_status <> 'ok' OR ai_analysis_status IS NULL) "
            "AND detail_content IS NOT NULL AND TRIM(detail_content) <> '' "
            "AND detail_url IS NOT NULL" % t)
        n += (cur.fetchone() or {}).get('n', 0)
    cur.close()
    return n


def cmd_backfill(args):
    conn = db_connect()
    try:
        before = pending_count(conn)
    finally:
        conn.close()
    rounds = max(1, (before + args.per_table * len(MAIN_TABLES) - 1)
                 // (args.per_table * len(MAIN_TABLES)))
    print('待分析 %d 条 | 每轮每表 %d 条 | 预计 %d 轮 | days=%d | max-rounds=%d' %
          (before, args.per_table, rounds, args.days, args.max_rounds))
    if not args.execute:
        print('dry-run：未写库、不探测模型。加 --execute 才会真正跑批量分析。')
        return 0
    if before == 0:
        print('无待分析记录，结束。')
        return 0

    from app.services import ai_analyzer_service as ai

    with build_app().app_context():
        # 开机探测放这里：dry-run 不该被模型停机挡住，实跑必须在写库前判一次。
        health = ai.check_model_health(force=True, timeout=3.0)
        if not health.get('reachable'):
            print('模型主机关机/不可达（%s），跳过回填；待分析记录保持 pending，'
                  '一条 failed 都不写。' % health.get('message'))
            return 0

        total_ok = 0
        stagnant = 0
        for i in range(1, min(args.max_rounds, rounds + 5) + 1):
            print('--- 第 %d 轮 ---' % i)
            total_ok += ai.run_batch(
                list(MAIN_TABLES), days=args.days,
                limit_per_table=args.per_table, status='has_content',
                force=False, today_only=False, keywords_only=False)
            state = ai.get_task_state()
            if state.get('model_status') == 'unavailable' or '中止' in (state.get('message') or ''):
                print('模型运行中不可达，已中止；剩余记录保持 pending。')
                break
            conn = db_connect()
            try:
                left = pending_count(conn)
            finally:
                conn.close()
            print('本轮后剩余待分析 %d 条，累计成功 %d 条' % (left, total_ok))
            if left == 0:
                print('全部完成。')
                break
            if left >= before and total_ok == 0:
                stagnant += 1
                if stagnant >= 2:
                    print('连续两轮无进展（可能全部失败），中止，避免死循环。')
                    return 2
            else:
                stagnant = 0
            before = left
        else:
            print('达到轮次上限，仍有剩余；可再次执行续跑。')
        return 0


def main():
    p = argparse.ArgumentParser(description='AI 分析覆盖率诊断与全量回填')
    p.add_argument('--env', help='显式指定 .env 路径')
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('report', help='只读诊断（默认）')
    b = sub.add_parser('backfill', help='跨轮批量回填')
    b.add_argument('--execute', action='store_true', help='真正写库；缺省为 dry-run')
    b.add_argument('--days', type=int, default=3650, help='挑行窗口天数，默认全量')
    b.add_argument('--per-table', type=int, default=100, help='每轮每表条数，默认 100')
    b.add_argument('--max-rounds', type=int, default=30, help='最多轮次，默认 30')
    args = p.parse_args()
    if args.cmd is None:
        args.cmd = 'report'
    env_file = load_env(getattr(args, 'env', None))
    if env_file:
        print('[env] %s' % env_file)
    try:
        return cmd_report(args) if args.cmd == 'report' else cmd_backfill(args)
    except Exception as e:
        print('执行失败: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
