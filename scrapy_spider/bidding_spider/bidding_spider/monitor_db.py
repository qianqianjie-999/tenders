"""
爬虫监控数据库操作模块
提供爬虫运行记录、超时日志等数据的写入功能
所有爬虫统一使用此模块进行监控埋点
支持连接池和实例生命周期管理
"""
import os
import sys
import pymysql
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, date
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger('bidding_spider.monitor_db')
try:
    from bidding_spider.logging_utils import setup_spider_logging
except Exception:
    setup_spider_logging = None

# 尝试导入连接池（可选依赖）
try:
    from dbutils.pooled_db import PooledDB
    HAS_POOLED_DB = True
except ImportError:
    HAS_POOLED_DB = False
    logger.warning("[MonitorDB] DBUtils 未安装，将使用普通连接模式。建议安装: pip install DBUtils")


# 全局连接池实例（懒加载）
_global_db_pool = None


def _get_db_pool(db_config: Dict[str, Any]) -> Optional[PooledDB]:
    """
    获取全局数据库连接池（单例模式）
    
    Args:
        db_config: 数据库配置字典
    
    Returns:
        连接池实例，如果不支持则返回 None
    """
    global _global_db_pool
    
    if not HAS_POOLED_DB:
        return None
    
    if _global_db_pool is None:
        try:
            # 创建连接池，最小5个连接，最大20个连接
            _global_db_pool = PooledDB(
                creator=pymysql,
                mincached=5,
                maxcached=20,
                maxshared=10,
                maxconnections=50,
                blocking=True,
                maxusage=None,
                setsession=[],
                ping=0,  # 0 = 从不检查连接
                **db_config
            )
            logger.info("[MonitorDB] 数据库连接池已初始化")
        except Exception as e:
            logger.error(f"[MonitorDB] 创建连接池失败: {e}")
            return None
    
    return _global_db_pool


class SpiderMonitorDB:
    """爬虫监控数据库操作类"""
    
    def __init__(self, db_config: Optional[Dict[str, Any]] = None, use_pool: bool = True):
        """
        初始化数据库连接
        
        Args:
            db_config: 数据库配置字典，默认从环境变量读取
            use_pool: 是否使用连接池（默认启用）
        """
        if db_config is None:
            db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', 3306)),
                'user': os.getenv('DB_USER', 'bidding_user'),
                'password': os.getenv('DB_PASSWORD', 'your_password'),
                'database': os.getenv('DB_NAME', 'bidding_db'),
                'charset': 'utf8mb4',
                'cursorclass': pymysql.cursors.DictCursor,
                'autocommit': True
            }
        
        self.db_config = db_config
        self.use_pool = use_pool and HAS_POOLED_DB
        self.connection = None
        self.current_run_id = None
        self._is_pool_connection = False  # 标记是否使用连接池连接
        
    def connect(self):
        """建立数据库连接（支持连接池模式）"""
        try:
            if self.use_pool:
                pool = _get_db_pool(self.db_config)
                if pool:
                    self.connection = pool.connection()
                    self._is_pool_connection = True
                    logger.debug(f"[MonitorDB] 从连接池获取连接")
                else:
                    # 连接池不可用，降级为普通连接
                    self.connection = pymysql.connect(**self.db_config)
                    self._is_pool_connection = False
            else:
                self.connection = pymysql.connect(**self.db_config)
                self._is_pool_connection = False
            return True
        except Exception as e:
            logger.error(f"[MonitorDB] 数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接（支持连接池模式）"""
        if self.connection:
            if self._is_pool_connection:
                # 连接池模式：归还连接到池中
                try:
                    self.connection.close()
                    logger.debug(f"[MonitorDB] 连接已归还到连接池")
                except Exception as e:
                    logger.warning(f"[MonitorDB] 归还连接到池时出错: {e}")
            else:
                # 普通模式：直接关闭
                self.connection.close()
            self.connection = None
            self._is_pool_connection = False
    
    def _ensure_connection(self):
        """确保连接可用"""
        if not self.connection:
            return self.connect()
        try:
            self.connection.ping(reconnect=True)
            return True
        except:
            # 连接失效，重新连接
            self.close()
            return self.connect()
    
    def __del__(self):
        """析构函数：确保连接被正确释放"""
        self.close()
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器：自动关闭连接"""
        self.close()
    
    def start_run(self, spider_name: str, log_file: str = None, stats_file: str = None) -> int:
        """
        记录爬虫开始运行
        
        Returns:
            run_id: 本次运行的记录ID
        """
        if not self._ensure_connection():
            return None

        try:
            today = date.today()
            
            # 查询今日该爬虫已运行次数
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM spider_run_logs WHERE spider_name = %s AND run_date = %s",
                    (spider_name, today)
                )
                result = cursor.fetchone()
                run_index = result['count'] + 1 if result else 1
            
            # 插入运行记录
            # 如果提供了 log_file，先配置日志（尽量不抛出异常）
            if log_file and setup_spider_logging:
                try:
                    setup_spider_logging(log_file)
                except Exception:
                    pass

            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO spider_run_logs 
                    (spider_name, run_date, run_index, start_time, status, log_file, stats_file)
                    VALUES (%s, %s, %s, NOW(), 'running', %s, %s)
                """, (spider_name, today, run_index, log_file, stats_file))
                
                self.connection.commit()
                self.current_run_id = cursor.lastrowid
                logger.info(f"[MonitorDB] {spider_name} 第{run_index}次运行开始，记录ID: {self.current_run_id}")
                return self.current_run_id
                
        except Exception as e:
            logger.error(f"[MonitorDB] 记录运行开始失败: {e}")
            return None
    
    def end_run(self, run_id: int, status: str = 'success', items_crawled: int = 0, 
                items_stored: int = None, error_count: int = 0, warning_count: int = 0,
                timeout_count: int = 0, close_reason: str = None):
        """
        记录爬虫运行结束
        
        Args:
            run_id: 运行记录ID
            status: 结束状态 (success/failed/stopped)
            items_crawled: 爬取数量
            items_stored: 实际入库数量，为 None 时不更新该字段（保留 Pipeline 累积的值）
            error_count: 错误数
            warning_count: 警告数
            timeout_count: 超时次数
            close_reason: 关闭原因
        """
        if not run_id or not self._ensure_connection():
            return False
        
        try:
            with self.connection.cursor() as cursor:
                # 如果 items_stored 为 None，则不更新该字段，保留 Pipeline 累积的值
                if items_stored is None:
                    cursor.execute("""
                        UPDATE spider_run_logs 
                        SET end_time = NOW(),
                            status = %s,
                            duration_seconds = TIMESTAMPDIFF(SECOND, start_time, NOW()),
                            items_crawled = %s,
                            error_count = %s,
                            warning_count = %s,
                            timeout_count = %s,
                            close_reason = %s
                        WHERE id = %s
                    """, (status, items_crawled, error_count, warning_count, 
                          timeout_count, close_reason, run_id))
                else:
                    cursor.execute("""
                        UPDATE spider_run_logs 
                        SET end_time = NOW(),
                            status = %s,
                            duration_seconds = TIMESTAMPDIFF(SECOND, start_time, NOW()),
                            items_crawled = %s,
                            items_stored = %s,
                            error_count = %s,
                            warning_count = %s,
                            timeout_count = %s,
                            close_reason = %s
                        WHERE id = %s
                    """, (status, items_crawled, items_stored, error_count, warning_count, 
                          timeout_count, close_reason, run_id))
                
                self.connection.commit()
                
                # 更新每日统计
                self._update_daily_stats(run_id)
                
                logger.info(f"[MonitorDB] 运行记录{run_id}结束，状态: {status}")
                return True
                
        except Exception as e:
            logger.error(f"[MonitorDB] 记录运行结束失败: {e}")
            return False
    
    def _update_daily_stats(self, run_id: int):
        """更新每日统计汇总"""
        try:
            with self.connection.cursor() as cursor:
                # 获取运行记录信息
                cursor.execute("""
                    SELECT spider_name, run_date FROM spider_run_logs WHERE id = %s
                """, (run_id,))
                run_info = cursor.fetchone()
                
                if not run_info:
                    return
                
                spider_name = run_info['spider_name']
                stat_date = run_info['run_date']
                
                # 计算统计数据
                cursor.execute("""
                    SELECT 
                        COUNT(*) as run_count,
                        SUM(items_crawled) as total_crawled,
                        SUM(items_stored) as total_stored,
                        SUM(error_count) as total_errors,
                        SUM(timeout_count) as total_timeouts,
                        AVG(duration_seconds) as avg_duration,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*) * 100 as success_rate
                    FROM spider_run_logs 
                    WHERE spider_name = %s AND run_date = %s
                """, (spider_name, stat_date))
                
                stats = cursor.fetchone()
                
                # 插入或更新每日统计
                cursor.execute("""
                    INSERT INTO spider_daily_stats 
                    (spider_name, stat_date, run_count, total_items_crawled, total_items_stored,
                     total_errors, total_timeouts, avg_duration_seconds, success_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    run_count = VALUES(run_count),
                    total_items_crawled = VALUES(total_items_crawled),
                    total_items_stored = VALUES(total_items_stored),
                    total_errors = VALUES(total_errors),
                    total_timeouts = VALUES(total_timeouts),
                    avg_duration_seconds = VALUES(avg_duration_seconds),
                    success_rate = VALUES(success_rate),
                    updated_at = NOW()
                """, (
                    spider_name, stat_date,
                    stats['run_count'],
                    stats['total_crawled'] or 0,
                    stats['total_stored'] or 0,
                    stats['total_errors'] or 0,
                    stats['total_timeouts'] or 0,
                    stats['avg_duration'],
                    round(stats['success_rate'], 2) if stats['success_rate'] else 0
                ))
                
                self.connection.commit()
                
        except Exception as e:
            logger.error(f"[MonitorDB] 更新每日统计失败: {e}")
    
    def log_timeout(self, spider_name: str, url: str, timeout_seconds: int = 60,
                    retry_count: int = 0, error_message: str = None, 
                    spider_run_id: int = None):
        """
        记录超时错误
        
        Args:
            spider_name: 爬虫名称
            url: 超时URL
            timeout_seconds: 超时设置秒数
            retry_count: 重试次数
            error_message: 错误信息
            spider_run_id: 关联的运行记录ID（可选）
        """
        if not self._ensure_connection():
            return False
        
        # 如果没有传入run_id，尝试使用当前run_id
        if spider_run_id is None:
            spider_run_id = self.current_run_id
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO spider_timeout_logs 
                    (spider_run_id, spider_name, url, timeout_seconds, retry_count, 
                     error_message, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (spider_run_id, spider_name, url, timeout_seconds, 
                      retry_count, error_message))
                
                self.connection.commit()
                return True
                
        except Exception as e:
            logger.error(f"[MonitorDB] 记录超时日志失败: {e}")
            return False

    def log_interface_warning(self, spider_name: str, url: str, warning_type: str,
                             response_status: int = None, item_count: int = 0,
                             error_message: str = None, spider_run_id: int = None):
        """
        记录接口异常警告（用于检测接口变更）

        Args:
            spider_name: 爬虫名称
            url: 请求的URL
            warning_type: 警告类型 (no_data/json_error/http_error/empty_response)
            response_status: HTTP响应状态码
            item_count: 返回的数据项数量
            error_message: 错误信息
            spider_run_id: 关联的运行记录ID（可选）
        """
        if not self._ensure_connection():
            return False

        if spider_run_id is None:
            spider_run_id = self.current_run_id

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO spider_timeout_logs
                    (spider_run_id, spider_name, url, warning_type, response_status,
                     error_message, occurred_at, resolved)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), FALSE)
                """, (spider_run_id, spider_name, url, warning_type,
                      response_status or 0, f"item_count:{item_count} {error_message or ''}"))

                self.connection.commit()
                logger.info(f"[MonitorDB] 接口警告已记录: {warning_type} - {url}")
                return True

        except Exception as e:
            logger.error(f"[MonitorDB] 记录接口警告失败: {e}")
            return False

    def get_recent_interface_warnings(self, spider_name: str = None, days: int = 7) -> List[Dict]:
        """
        获取最近N天的接口异常警告

        Args:
            spider_name: 爬虫名称（可选，不指定则查所有）
            days: 查询天数

        Returns:
            警告列表
        """
        if not self._ensure_connection():
            return []

        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT * FROM spider_timeout_logs
                    WHERE occurred_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND warning_type IN ('no_data', 'json_error', 'http_error')
                """
                params = [days]

                if spider_name:
                    sql += " AND spider_name = %s"
                    params.append(spider_name)

                sql += " ORDER BY occurred_at DESC LIMIT 100"

                cursor.execute(sql, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"[MonitorDB] 查询接口警告失败: {e}")
            return []

    def increment_items_stored(self, run_id: int, count: int = 1):
        """
        增加入库数量（用于pipeline中每插入一条就更新）
        
        Args:
            run_id: 运行记录ID
            count: 增加数量
        """
        if not run_id or not self._ensure_connection():
            return False
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE spider_run_logs 
                    SET items_stored = items_stored + %s
                    WHERE id = %s
                """, (count, run_id))
                
                self.connection.commit()
                return True
                
        except Exception as e:
            logger.error(f"[MonitorDB] 更新入库数量失败: {e}")
            return False
    
    def get_current_run_id(self) -> Optional[int]:
        """获取当前运行记录ID"""
        return self.current_run_id


# 全局监控实例缓存（按爬虫名缓存，避免单例模式导致的并发问题）
_monitor_instances: Dict[str, SpiderMonitorDB] = {}


def get_monitor(db_config: Optional[Dict[str, Any]] = None, spider_name: str = None) -> SpiderMonitorDB:
    """
    获取监控实例（按爬虫名独立实例）

    Usage:
        from bidding_spider.monitor_db import get_monitor

        # 方式1：指定爬虫名（推荐，支持并发）
        monitor = get_monitor(spider_name='jining_get')
        run_id = monitor.start_run('jining_get')
        # ... 爬虫逻辑 ...
        monitor.end_run(run_id, status='success', items_crawled=100)

        # 方式2：不指定爬虫名（向后兼容）
        monitor = get_monitor()
        run_id = monitor.start_run('jining_get')
    """
    global _monitor_instances

    # 如果指定了spider_name，返回独立实例
    if spider_name:
        if spider_name not in _monitor_instances:
            _monitor_instances[spider_name] = SpiderMonitorDB(db_config)
            logger.info(f"[MonitorDB] 创建新监控实例: {spider_name}")
        return _monitor_instances[spider_name]

    # 向后兼容：未指定spider_name时，返回默认实例
    if 'default' not in _monitor_instances:
        _monitor_instances['default'] = SpiderMonitorDB(db_config)
        logger.info("[MonitorDB] 创建默认监控实例")
    return _monitor_instances['default']


def cleanup_monitor(spider_name: str) -> bool:
    """
    清理指定爬虫的监控实例（释放资源）

    Args:
        spider_name: 爬虫名称

    Returns:
        bool: 是否成功清理
    """
    global _monitor_instances

    if spider_name in _monitor_instances:
        try:
            _monitor_instances[spider_name].close()
            del _monitor_instances[spider_name]
            logger.info(f"[MonitorDB] 已清理监控实例: {spider_name}")
            return True
        except Exception as e:
            logger.error(f"[MonitorDB] 清理监控实例失败 {spider_name}: {e}")
            return False
    else:
        logger.warning(f"[MonitorDB] 监控实例不存在: {spider_name}")
        return False


def reset_monitor(spider_name: str = None):
    """
    重置监控实例（用于测试或爬虫结束时清理）

    Args:
        spider_name: 指定爬虫名重置，若不指定则重置所有实例
    """
    global _monitor_instances

    if spider_name:
        if spider_name in _monitor_instances:
            _monitor_instances[spider_name].close()
            del _monitor_instances[spider_name]
            logger.info(f"[MonitorDB] 已重置监控实例: {spider_name}")
        else:
            logger.warning(f"[MonitorDB] 监控实例不存在: {spider_name}")
    else:
        count = len(_monitor_instances)
        for monitor in _monitor_instances.values():
            monitor.close()
        _monitor_instances.clear()
        logger.info(f"[MonitorDB] 已重置所有监控实例 ({count} 个)")


def get_monitor_instances() -> Dict[str, SpiderMonitorDB]:
    """
    获取所有活跃的监控实例

    Returns:
        Dict[str, SpiderMonitorDB]: 实例字典（爬虫名 -> 实例）
    """
    return _monitor_instances


def get_monitor_stats() -> Dict[str, int]:
    """
    获取监控实例统计信息

    Returns:
        Dict[str, int]: 统计信息字典
    """
    global _monitor_instances
    return {
        'active_instances': len(_monitor_instances),
        'total_created': len(_monitor_instances)  # 简化统计，实际可扩展
    }
