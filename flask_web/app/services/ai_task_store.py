"""AI 批量分析任务状态（落库版）。

为什么必须落库：
    gunicorn 用 2 个 worker 进程（生产 `--workers 2 --max-requests 1000`）。
    原实现把任务状态放在模块内的 `_task_state` 字典里、批量任务跑在 daemon 线程中，于是：
      1. 两个 worker 各看各的内存 → 页面可能显示"没有任务"，用户再点一次就重复启动；
      2. worker 跑满 1000 个请求被回收时，线程随之静默消失，页面永远停在"任务启动中"。
    改成：状态写 `ai_batch_tasks` 表（跨进程共享），任务本身由独立进程
    （tools/ai_batch_runner.py）执行，worker 重启不影响它。

并发控制：
    启动用 MySQL 命名锁 GET_LOCK 串行化"检查-插入"，避免两个 worker 同时抢到。
    运行期用 `heartbeat_at` 判活：超过 STALE_SECONDS 没心跳即判定中断，允许接管。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from app.extensions import get_db_connection

logger = logging.getLogger(__name__)

TABLE = 'ai_batch_tasks'
LOCK_START = 'tenders_ai_batch_start'
LOCK_RUN = 'tenders_ai_batch_run'

# 心跳超过这个秒数就认为进程已死。运行中每条记录都会刷新，另有独立心跳线程兜底
# （单条长正文 + 深入分析最长可达 3~6 分钟，所以不能把阈值卡得太紧）。
STALE_SECONDS = 180

_DDL = """
CREATE TABLE IF NOT EXISTS `ai_batch_tasks` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `status` VARCHAR(16) NOT NULL DEFAULT 'running' COMMENT 'running/done/aborted/failed',
  `params` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'tables/limit/days 等启动参数快照',
  `total` INT NOT NULL DEFAULT 0,
  `done` INT NOT NULL DEFAULT 0,
  `ok` INT NOT NULL DEFAULT 0,
  `failed` INT NOT NULL DEFAULT 0,
  `deep_ok` INT NOT NULL DEFAULT 0,
  `current` VARCHAR(255) NOT NULL DEFAULT '',
  `message` VARCHAR(500) NOT NULL DEFAULT '',
  `model_status` VARCHAR(20) NOT NULL DEFAULT 'unknown',
  `pid` INT NULL,
  `started_at` DATETIME NOT NULL,
  `finished_at` DATETIME NULL,
  `heartbeat_at` DATETIME NOT NULL,
  KEY `idx_status_started` (`status`, `started_at`),
  KEY `idx_heartbeat` (`heartbeat_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 批量分析任务状态（跨 worker 共享）'
"""

# 只允许更新这些列，避免外部随手拼列名
_STATE_FIELDS = {
    'status', 'total', 'done', 'ok', 'failed', 'deep_ok',
    'current', 'message', 'model_status', 'finished_at', 'pid', 'params',
}

_table_ready = False


def ensure_table(conn=None) -> None:
    """幂等建表；每个进程只真正执行一次。"""
    global _table_ready
    if _table_ready:
        return
    own = conn is None
    if own:
        conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(_DDL)
        cur.close()
        conn.commit()
        _table_ready = True
    finally:
        if own:
            conn.close()


def reset_table_cache() -> None:
    """测试用：让下一次 ensure_table 重新建表。"""
    global _table_ready
    _table_ready = False


def try_start(params: str = '', pid: Optional[int] = None) -> Tuple[bool, Optional[int], str]:
    """抢占启动权并插入一条 running 记录。

    返回 (是否抢到, 任务 id, 失败原因)。已有新鲜任务在跑时返回 (False, 那个 id, 原因)。
    """
    conn = get_db_connection()
    try:
        ensure_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK(%s, 5) AS got", (LOCK_START,))
        row = cur.fetchone() or {}
        if int(row.get('got') or 0) != 1:
            cur.close()
            return False, None, '数据库繁忙，未能获取启动锁'

        try:
            cur.execute(
                "SELECT id, TIMESTAMPDIFF(SECOND, heartbeat_at, NOW()) AS age "
                f"FROM `{TABLE}` WHERE status = 'running' ORDER BY id DESC LIMIT 1")
            running = cur.fetchone()
            age = None if running is None else running.get('age')
            if running is not None and age is not None and int(age) <= STALE_SECONDS:
                cur.close()
                return False, running['id'], '已有分析任务在运行（%d 秒前刚有心跳）' % int(age)

            if running is not None:
                # 心跳过期：认领并标记中断，让新任务接管，避免"僵尸 running"卡死入口
                cur.execute(
                    f"UPDATE `{TABLE}` SET status='aborted', finished_at=NOW(), "
                    "message=CONCAT('心跳超时 ', %s, ' 秒，判定中断；已由新任务接管') WHERE id=%s",
                    (int(age if age is not None else -1), running['id']))

            cur.execute(
                f"INSERT INTO `{TABLE}` (status, params, total, done, ok, failed, deep_ok, "
                "current, message, model_status, pid, started_at, heartbeat_at) "
                "VALUES ('running', %s, 0, 0, 0, 0, 0, '', '任务启动中', 'unknown', %s, NOW(), NOW())",
                (params[:255], pid))
            task_id = cur.lastrowid
            conn.commit()
            cur.close()
            return True, task_id, ''
        finally:
            # 命名锁必须显式释放：连接会归还连接池，靠断开释放会污染池里的连接
            try:
                cur2 = conn.cursor()
                cur2.execute("SELECT RELEASE_LOCK(%s)", (LOCK_START,))
                cur2.close()
                conn.commit()
            except Exception:
                logger.warning('释放启动锁失败', exc_info=True)
    finally:
        conn.close()


def touch(task_id: int, **fields: Any) -> None:
    """刷新进度 + 心跳。任何异常都不应打断分析主流程。"""
    if not task_id:
        return
    clean = {k: v for k, v in fields.items() if k in _STATE_FIELDS}
    sets = ['heartbeat_at = NOW()']
    args = []
    for key, value in clean.items():
        sets.append(f'`{key}` = %s')
        args.append(value)
    args.append(task_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE `{TABLE}` SET {', '.join(sets)} WHERE id = %s", tuple(args))
        conn.commit()
        cur.close()
    except Exception as e:
        # 每条记录都会调用，失败也不能中断分析；同样不打栈
        logger.warning('写任务进度失败（不影响分析）: %s', e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def heartbeat(task_id: int) -> None:
    touch(task_id)


def finish(task_id: int, status: str, message: str = '') -> None:
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE `{TABLE}` SET status=%s, message=%s, finished_at=NOW(), heartbeat_at=NOW() "
            "WHERE id=%s", (status, message[:500], task_id))
        conn.commit()
        cur.close()
    except Exception:
        logger.warning('写任务结束状态失败', exc_info=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_latest() -> Optional[Dict[str, Any]]:
    """读最近一条任务，转成前端/接口用的结构；无记录返回 None。"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_table(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, params, total, done, ok, failed, deep_ok, current, message, "
            "model_status, pid, started_at, finished_at, heartbeat_at, "
            "TIMESTAMPDIFF(SECOND, heartbeat_at, NOW()) AS age "
            f"FROM `{TABLE}` ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
    except Exception as e:
        # 页面每 2.5 秒轮询一次，这里不打栈，避免刷爆日志
        logger.warning('读任务状态失败: %s', e)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not row:
        return None

    age = row.get('age')
    age = int(age) if age is not None else None
    still_running = row.get('status') == 'running'
    fresh = age is not None and age <= STALE_SECONDS
    running = bool(still_running and fresh)

    message = row.get('message') or ''
    if still_running and not fresh:
        # 进程已经没了（worker 被回收 / 被 kill）：别让页面永远停在"任务启动中"
        message = ('任务异常中断（已 %s 秒无心跳，进程可能被回收）；'
                   '未处理记录仍为 pending，可重新启动' % age) if age is not None else message

    return {
        'task_id': row.get('id'),
        'running': running,
        'status': 'running' if running else (row.get('status') or ''),
        'params': row.get('params') or '',
        'total': int(row.get('total') or 0),
        'done': int(row.get('done') or 0),
        'ok': int(row.get('ok') or 0),
        'failed': int(row.get('failed') or 0),
        'deep_ok': int(row.get('deep_ok') or 0),
        'current': row.get('current') or '',
        'message': message,
        'model_status': row.get('model_status') or 'unknown',
        'started_at': _fmt(row.get('started_at')),
        'finished_at': _fmt(row.get('finished_at')),
        'heartbeat_age': age,
        'stale': bool(still_running and not fresh),
    }


def _fmt(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return value.strftime('%Y-%m-%d %H:%M:%S')
    except AttributeError:
        return str(value)


def acquire_run_lock(conn, timeout: int = 0) -> bool:
    """任务进程侧的互斥锁：即使被手工重复拉起，也只有一份在跑。"""
    cur = conn.cursor()
    cur.execute("SELECT GET_LOCK(%s, %s) AS got", (LOCK_RUN, timeout))
    row = cur.fetchone() or {}
    cur.close()
    return int(row.get('got') or 0) == 1


def release_run_lock(conn) -> None:
    try:
        cur = conn.cursor()
        cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_RUN,))
        cur.close()
    except Exception:
        logger.warning('释放运行锁失败', exc_info=True)
