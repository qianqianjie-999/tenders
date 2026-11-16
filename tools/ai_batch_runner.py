#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 批量分析——独立任务进程。

为什么要单独一个进程：
    生产用 gunicorn（2 workers、`--max-requests 1000`）。批量分析一条要 20~30 秒，
    整批可能跑几十分钟，若放在 worker 的 daemon 线程里，worker 被回收时任务会
    无声消失，状态也永远停在"任务启动中"。独立进程用 start_new_session 脱离
    worker 的会话，worker 重启/回收都不影响它。

由 Web 侧拉起（tools 里的 /api/batch 入口），也可以手工跑：
    HOME=/home/qianqianjie venv312/bin/python tools/ai_batch_runner.py \
        --tables bidding_info --limit 5 --days 1 --today-only --keywords-only

退出码：0 正常；2 已有任务在跑（没抢到锁）；1 异常。
"""
import argparse
import os
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'flask_web'))


def _load_env():
    """与 tools/ 下其他脚本同款：TENDERS_ENV → 仓库根 .env → 开发机主目录兜底。

    Web 侧拉起时会直接把已加载的 os.environ 传下来，这里主要给手工跑用
    （worktree 里没有 .env，需要回落到主工作目录那份）。
    """
    for path in (os.environ.get('TENDERS_ENV'), str(ROOT / '.env'),
                 '/home/qianqianjie/tenders/.env'):
        if path and os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            os.environ.setdefault(k.strip(), v.strip())
            except Exception:
                pass
            return path
    return None


_load_env()

from app import create_app  # noqa: E402
from app.services import ai_analyzer_service as ai  # noqa: E402
from app.services import ai_task_store as store  # noqa: E402

HEARTBEAT_INTERVAL = 20  # 秒；单条长正文 + 深入分析可能 3~6 分钟，靠它兜底保活


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='AI 批量分析任务进程')
    p.add_argument('--task-id', type=int, default=0, help='Web 侧已创建的任务 id；缺省则自行抢占')
    p.add_argument('--tables', default='all')
    p.add_argument('--days', type=int, default=1)
    p.add_argument('--limit', type=int, default=20, help='每张表最多分析多少条')
    p.add_argument('--status', default='all', help='候选记录筛选：has_content / all / pending…')
    p.add_argument('--force', action='store_true', help='已分析过的也重跑')
    p.add_argument('--today-only', action='store_true')
    p.add_argument('--keywords-only', action='store_true')
    return p.parse_args(argv)


def resolve_tables(raw: str):
    if raw in ('', 'all', None):
        return list(ai.VALID_TABLES)
    names = [x.strip() for x in raw.split(',') if x.strip()]
    return [t for t in names if t in ai.VALID_TABLES]


def main(argv=None) -> int:
    args = parse_args(argv)
    tables = resolve_tables(args.tables)
    if not tables:
        print('[runner] 没有可用的表名：%r' % args.tables, flush=True)
        return 1

    app = create_app()
    with app.app_context():
        task_id = args.task_id
        if not task_id:
            params = ('tables=%s;limit=%d;days=%d;manual=1'
                      % (','.join(tables), args.limit, args.days))
            ok, task_id, reason = store.try_start(params, pid=os.getpid())
            if not ok:
                print('[runner] 未能启动：%s' % reason, flush=True)
                return 2

        lock_conn = store.get_db_connection()
        try:
            if not store.acquire_run_lock(lock_conn, timeout=0):
                # 同一时刻只允许一份在跑：多出来的这份直接退出，不改任务状态
                print('[runner] 已有任务进程持有运行锁，退出', flush=True)
                return 2

            print('[runner] 启动 task_id=%s tables=%s limit=%d days=%d today=%s kw=%s'
                  % (task_id, ','.join(tables), args.limit, args.days,
                     args.today_only, args.keywords_only), flush=True)

            ai.set_progress_sink(lambda payload: store.touch(task_id, **payload))

            stop = threading.Event()

            def _beat():
                while not stop.wait(HEARTBEAT_INTERVAL):
                    try:
                        store.heartbeat(task_id)
                    except Exception:
                        pass

            beat = threading.Thread(target=_beat, name='ai-heartbeat', daemon=True)
            beat.start()

            t0 = time.time()
            try:
                ok_cnt = ai.run_batch(
                    tables, args.days, args.limit, args.status, args.force,
                    today_only=args.today_only, keywords_only=args.keywords_only)
            except Exception as e:
                traceback.print_exc()
                store.finish(task_id, 'failed', '任务异常: %s' % str(e)[:400])
                return 1
            finally:
                stop.set()

            state = store.get_latest() or {}
            print('[runner] 结束 %.1fs ok=%s status=%s message=%s'
                  % (time.time() - t0, ok_cnt, state.get('status'), state.get('message')),
                  flush=True)
            # run_batch 内部已通过 sink 写入终态；这里只在状态仍为 running 时兜底
            if state.get('task_id') == task_id and state.get('status') == 'running':
                store.finish(task_id, 'done', '完成：成功 %s' % ok_cnt)
            return 0
        finally:
            try:
                store.release_run_lock(lock_conn)
            finally:
                lock_conn.close()


if __name__ == '__main__':
    sys.exit(main())
