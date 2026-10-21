# -*- coding: utf-8 -*-
"""账号级登录失败限流守卫（零第三方依赖，仅标准库）。

为什么按【账号】而不是按 IP
    本架构下客户端经 frp（L4 透传）到达 .75，服务端看到的源地址恒为内网 frpc
    地址（实测 192.168.31.75），真实客户端 IP 不可得。按 IP 计数既拦不住攻击者，
    又会让全公司共用一个桶（一人失败即锁全员）。

为什么用 SQLite 而不是进程内存
    9000/9001/9002 = httpd + mod_wsgi（多进程），8000 = gunicorn --workers 3
    ⇒ 进程内 defaultdict 既不共享也不持久。SQLite（WAL）跨进程、跨 worker 生效。

并发与失败策略（v2，2026-10-07）
    · WAL 只在 _ensure 里设一次（每连接都设会引入写锁竞争）；
    · 写操作走 BEGIN IMMEDIATE + 退避重试，避免"读-升级写"死锁；
    · 任何一次失败都**同时**写进程内存，读取时 SQLite 与内存**合并计数** ⇒ 绝不丢
      一条失败记录；SQLite 恢复可用后自动回归（不做永久降级）。
    · 守卫自身的异常绝不阻断登录。
"""

import os
import sqlite3
import sys
import threading
import time

_MAX_FAILS = int(os.environ.get('LOGIN_GUARD_MAX', '5'))
_WINDOW = int(os.environ.get('LOGIN_GUARD_WINDOW', '300'))

# 全局软节流（不硬封禁，避免被用来 DoS 全员）
_GLOBAL_WINDOW = 60
_GLOBAL_SOFT_LIMIT = 30
_GLOBAL_SOFT_MAX_SLEEP = 1.0

_MEM = {}
_MEM_LOCK = threading.Lock()


def _norm(scope):
    s = (scope or '').strip().lower()
    return s[:64] if s else '__unknown__'


class LoginGuard(object):
    """按账号（scope）计数的登录失败限流。"""

    def __init__(self, db_path, max_fails=None, window=None, name='login'):
        self.db_path = db_path
        self.max_fails = int(max_fails or _MAX_FAILS)
        self.window = int(window or _WINDOW)
        self.name = name
        self.sqlite_ok = True
        self._err_streak = 0
        self._ensure()

    # ---------------- 存储层 ----------------
    def _conn(self):
        d = os.path.dirname(os.path.abspath(self.db_path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        # isolation_level=None ⇒ autocommit，事务由我们显式 BEGIN/COMMIT 控制
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    def _note_err(self, exc, where):
        self._err_streak += 1
        if self._err_streak in (1, 10) or self._err_streak % 100 == 0:
            print('[login_guard:%s] %s 失败(第 %d 次，已计入内存兜底): %r'
                  % (self.name, where, self._err_streak, exc), file=sys.stderr)

    def _note_ok(self):
        if self._err_streak:
            print('[login_guard:%s] SQLite 已恢复（此前连续失败 %d 次）'
                  % (self.name, self._err_streak), file=sys.stderr)
            self._err_streak = 0

    def _run(self, fn, retries=4):
        """执行 fn(conn)；遇 locked/busy 退避重试。全部失败则抛出。"""
        last = None
        for i in range(retries):
            conn = None
            try:
                conn = self._conn()
                rv = fn(conn)
                self._note_ok()
                return rv
            except Exception as exc:
                last = exc
                msg = str(exc).lower()
                if 'locked' in msg or 'busy' in msg:
                    time.sleep(0.05 * (i + 1))
                    continue
                raise
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
        raise last

    def _ensure(self):
        try:
            def _probe(c):
                try:
                    c.execute('PRAGMA journal_mode=WAL')
                except Exception:
                    pass
                c.execute('CREATE TABLE IF NOT EXISTS login_fail '
                          '(scope TEXT NOT NULL, ts REAL NOT NULL)')
                c.execute('CREATE INDEX IF NOT EXISTS ix_login_fail ON login_fail(scope, ts)')
                # 真实"写"探针：只用 CREATE ... IF NOT EXISTS 时，若表已存在但当前用户
                # 对文件无写权限，语句不报错 ⇒ 守卫看似正常、实际每次写入都失败并静默
                # 退化（多 worker 下＝限流失效）。必须真写一次才算探到。
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute("INSERT INTO login_fail (scope, ts) VALUES ('__probe__', 0)")
                    c.execute("DELETE FROM login_fail WHERE scope = '__probe__'")
                    c.execute('COMMIT')
                except Exception:
                    c.execute('ROLLBACK')
                    raise
            self._run(_probe)
        except Exception as exc:
            self._note_err(exc, 'ensure')
            print('[login_guard:%s] 提示：%s 或其所在目录对运行用户不可写，'
                  '请核对属主/权限' % (self.name, self.db_path), file=sys.stderr)

    # ---------------- 内存兜底 ----------------
    @staticmethod
    def _mem_add(scope, ts):
        with _MEM_LOCK:
            _MEM.setdefault(scope, []).append(ts)

    @staticmethod
    def _mem_get(scope, since):
        with _MEM_LOCK:
            lst = [t for t in _MEM.get(scope, []) if t > since]
            _MEM[scope] = lst
            return list(lst)

    @staticmethod
    def _mem_clear(scope):
        with _MEM_LOCK:
            _MEM.pop(scope, None)

    # ---------------- 公开 API ----------------
    def record_failure(self, scope):
        """记一次失败（键：归一化账号名）。写 SQLite；写失败才落内存兜底。

        ⛔ 不要"SQLite 与内存都写"：读取端会把两者合并计数，双写＝双计。
        memory 只作为 SQLite 不可用时的兜底，且读取端合并 ⇒ 一条都不丢。
        """
        scope = _norm(scope)
        now = time.time()
        try:
            def _w(c):
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute('INSERT INTO login_fail (scope, ts) VALUES (?, ?)', (scope, now))
                    c.execute('DELETE FROM login_fail WHERE ts < ?',
                              (now - 2 * max(self.window, _GLOBAL_WINDOW),))
                    c.execute('COMMIT')
                except Exception:
                    c.execute('ROLLBACK')
                    raise
            self._run(_w)
            return
        except Exception as exc:
            self._note_err(exc, 'record_failure')
            self._mem_add(scope, now)

    def _fail_times(self, scope, since):
        """SQLite + 进程内存合并取失败时间戳（两处都不丢）。"""
        times = list(self._mem_get(scope, since))
        try:
            def _q(c):
                return [float(r[0]) for r in c.execute(
                    'SELECT ts FROM login_fail WHERE scope = ? AND ts > ?',
                    (scope, since)).fetchall()]
            times += self._run(_q) or []
        except Exception as exc:
            self._note_err(exc, 'read')
        return times

    def is_locked(self, scope):
        """返回 (是否锁定, 剩余秒数)。"""
        scope = _norm(scope)
        now = time.time()
        ts = self._fail_times(scope, now - self.window)
        if len(ts) >= self.max_fails:
            return True, max(1, int(self.window - (now - min(ts))))
        return False, 0

    def remaining_attempts(self, scope):
        scope = _norm(scope)
        return max(0, self.max_fails - len(self._fail_times(scope, time.time() - self.window)))

    def failure_count(self, scope):
        return len(self._fail_times(_norm(scope), time.time() - self.window))

    def reset(self, scope):
        """只清当前账号（绝不清整桶）。"""
        scope = _norm(scope)
        self._mem_clear(scope)
        try:
            self._run(lambda c: c.execute('DELETE FROM login_fail WHERE scope = ?', (scope,)))
        except Exception as exc:
            self._note_err(exc, 'reset')

    def global_pressure(self):
        """全局失败速率过高时返回建议节流秒数（软节流，不硬封禁）。"""
        now = time.time()
        n = 0
        with _MEM_LOCK:
            n += sum(len([t for t in v if t > now - _GLOBAL_WINDOW]) for v in _MEM.values())
        try:
            def _q(c):
                return c.execute('SELECT COUNT(*) FROM login_fail WHERE ts > ?',
                                 (now - _GLOBAL_WINDOW,)).fetchone()[0]
            n += int(self._run(_q) or 0)
        except Exception as exc:
            self._note_err(exc, 'global_pressure')
        if n <= _GLOBAL_SOFT_LIMIT:
            return 0.0
        return min(_GLOBAL_SOFT_MAX_SLEEP, 0.05 * (n - _GLOBAL_SOFT_LIMIT))

    def stats(self):
        return {'name': self.name, 'db': self.db_path, 'err_streak': self._err_streak,
                'max_fails': self.max_fails, 'window': self.window}


if __name__ == '__main__':
    import json
    g = LoginGuard(sys.argv[1] if len(sys.argv) > 1 else '/tmp/login_guard_selftest.db')
    print(json.dumps(g.stats(), ensure_ascii=False))
    g.reset('selftest')
    for _ in range(g.max_fails):
        g.record_failure('selftest')
    print('locked_after_%d=%r' % (g.max_fails, g.is_locked('selftest')[0]))
    print('remaining=%d' % g.remaining_attempts('selftest'))
    print('count=%d' % g.failure_count('selftest'))
    g.reset('selftest')
    print('locked_after_reset=%r' % (g.is_locked('selftest')[0],))
    print('count_after_reset=%d' % g.failure_count('selftest'))
    print('RESULT=SELFTEST_PASS')
