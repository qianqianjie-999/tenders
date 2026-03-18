"""
爬虫监控服务
提供系统资源、爬虫进程、日志文件等监控功能
"""
import os
import re
import time
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, date
from collections import deque
from flask import current_app
from app.extensions import get_db_connection


class MonitorService:
    """爬虫监控服务"""
    
    # 爬虫项目根目录
    SPIDER_ROOT = None
    
    @classmethod
    def get_spider_root(cls):
        """获取爬虫项目根目录"""
        if cls.SPIDER_ROOT is None:
            # 从 tenders 目录找到 scrapy_spider
            cls.SPIDER_ROOT = Path(current_app.root_path).parent.parent / 'scrapy_spider' / 'bidding_spider'
        return cls.SPIDER_ROOT
    
    @staticmethod
    def get_system_resources():
        """获取系统资源使用情况"""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=0.5)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 获取网络IO
            net_io = psutil.net_io_counters()
            
            return {
                'success': True,
                'cpu': {
                    'percent': cpu_percent,
                    'core_count': psutil.cpu_count(),
                    'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
                },
                'memory': {
                    'percent': memory.percent,
                    'used_gb': round(memory.used / (1024**3), 2),
                    'total_gb': round(memory.total / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2)
                },
                'disk': {
                    'percent': disk.percent,
                    'used_gb': round(disk.used / (1024**3), 2),
                    'total_gb': round(disk.total / (1024**3), 2),
                    'free_gb': round(disk.free / (1024**3), 2)
                },
                'network': {
                    'bytes_sent': net_io.bytes_sent,
                    'bytes_recv': net_io.bytes_recv,
                    'packets_sent': net_io.packets_sent,
                    'packets_recv': net_io.packets_recv
                },
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
        except ImportError:
            return {
                'success': False,
                'message': 'psutil 模块未安装，执行: pip install psutil'
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    @classmethod
    def get_spider_processes(cls):
        """获取运行的爬虫进程"""
        try:
            import psutil

            running_spiders = []
            seen_spider_names = set()  # 避免重复识别同一爬虫

            for process in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info', 'create_time']):
                try:
                    cmdline = ' '.join(process.info['cmdline'] or [])

                    # 只检查包含 'scrapy crawl' 的主进程，避免识别 worker 子进程
                    if 'scrapy' not in cmdline.lower() or 'crawl' not in cmdline.lower():
                        continue

                    # 提取爬虫名称
                    spider_name = None
                    for known_spider in ['jining_get', 'sd_post', 'jinan_post', 'taian_post', 'zibo_post']:
                        if known_spider in cmdline:
                            # 如果已经识别过该爬虫，跳过（避免重复）
                            if known_spider in seen_spider_names:
                                continue
                            spider_name = known_spider
                            seen_spider_names.add(known_spider)
                            break

                    if not spider_name:
                        continue

                    # 计算运行时间
                    create_time = process.info['create_time']
                    runtime_seconds = time.time() - create_time
                    runtime_str = cls._format_runtime(runtime_seconds)

                    running_spiders.append({
                        'pid': process.info['pid'],
                        'name': process.info['name'],
                        'spider_name': spider_name,
                        'cmdline': cmdline[:200] + '...' if len(cmdline) > 200 else cmdline,
                        'cpu_percent': process.info['cpu_percent'] or 0,
                        'memory_mb': round(process.info['memory_info'].rss / (1024**2), 2),
                        'runtime': runtime_str,
                        'runtime_seconds': int(runtime_seconds)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return {
                'success': True,
                'processes': running_spiders,
                'count': len(running_spiders)
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    @staticmethod
    def _format_runtime(seconds):
        """格式化运行时间"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds/60)}分{int(seconds%60)}秒"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}小时{minutes}分"
    
    @classmethod
    def get_log_files(cls, spider_name=None, lines=50, date_filter='today'):
        """获取日志文件列表和内容
        
        Args:
            spider_name: 爬虫名称过滤
            lines: 读取行数
            date_filter: 日期过滤 ('today' | 'all' | 'YYYY-MM-DD')
        """
        try:
            spider_root = cls.get_spider_root()
            logs_dir = spider_root / 'logs'
            
            if not logs_dir.exists():
                return {
                    'success': True,
                    'logs': [],
                    'message': '日志目录不存在'
                }
            
            log_files = []
            today = datetime.now().strftime('%Y%m%d')
            
            # 获取所有日志文件（lines=0 时仅列文件，不读取内容）
            for log_file in sorted(logs_dir.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True):
                # 日期过滤
                if date_filter == 'today':
                    # 检查文件名或修改日期是否为今天
                    if today not in log_file.name:
                        file_date = datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y%m%d')
                        if file_date != today:
                            continue
                elif date_filter and date_filter != 'all':
                    # 指定日期过滤
                    if date_filter.replace('-', '') not in log_file.name:
                        file_date = datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y%m%d')
                        if file_date != date_filter.replace('-', ''):
                            continue
                
                stat = log_file.stat()
                size_mb = round(stat.st_size / (1024**2), 2)
                mtime = datetime.fromtimestamp(stat.st_mtime)
                content = []
                if lines > 0:
                    content_deque = cls._read_last_lines(log_file, lines)
                    try:
                        content = [c.rstrip('\n') for c in content_deque]
                    except Exception:
                        content = [str(content_deque)]
                log_files.append({
                    'name': log_file.name,
                    'size_mb': size_mb,
                    'modified': mtime.strftime('%Y-%m-%d %H:%M:%S'),
                    'content': content,
                    'path': str(log_file)
                })
            
            return {
                'success': True,
                'logs': log_files,
                'count': len(log_files)
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }

    @classmethod
    def get_error_logs(cls, spider_name=None, limit=200, q=None, since=None, until=None):
        """获取日志文件中的错误行以及数据库中失败运行摘要（管理员查看）

        支持按关键词(q)和时间范围(since, until)过滤。时间格式支持 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS`。
        """
        try:
            results = []
            spider_root = cls.get_spider_root()
            logs_dir = spider_root / 'logs'

            # 解析时间过滤
            def parse_time(s):
                if not s:
                    return None
                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                    try:
                        return datetime.strptime(s, fmt)
                    except Exception:
                        continue
                return None

            since_dt = parse_time(since)
            until_dt = parse_time(until)

            datetime_re = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
            
            # 更精确的错误匹配：匹配日志级别 [ERROR] 或 ERROR:，排除误报
            error_level_re = re.compile(r'\[(?:ERROR|error|Error)\]|ERROR:|错误：|异常')
            # 排除误报关键词
            false_positive_patterns = [
                'httperrormiddleware',      # Scrapy 中间件名称
                'log_count/error',          # 统计信息
                'error_count',              # 统计字段
                'spidermiddlewares',        # 中间件模块名
                '超时错误数',               # 监控统计
                'dns 错误数',               # 监控统计
                '最大超时错误数',           # 监控统计
                '📊',                       # emoji 统计行
            ]

            # 从文件中提取真正的错误行
            if logs_dir.exists():
                for log_file in sorted(logs_dir.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True):
                    # 允许按爬虫名过滤（文件名通常包含爬虫名或时间戳）
                    if spider_name and spider_name not in log_file.name:
                        continue

                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            for line in f:
                                text = line.strip()
                                lower = text.lower()

                                # 检查是否包含错误关键词
                                has_error_keyword = ('error' in lower) or ('错误' in lower) or ('exception' in lower) or ('异常' in lower)
                                if not has_error_keyword:
                                    continue
                                
                                # 排除误报：如果没有 [ERROR] 级别标记，且包含误报关键词，则跳过
                                if not error_level_re.search(text):
                                    if any(fp in lower for fp in false_positive_patterns):
                                        continue
                                    # 额外排除：统计信息行（包含📊或"错误数"但没有实际错误）
                                    if '错误数' in text or '📊' in text:
                                        continue
                                
                                # 关键词过滤
                                if q and q.strip().lower() not in lower:
                                    continue

                                # 时间过滤（尝试从行中提取时间）
                                m = datetime_re.search(text)
                                if m:
                                    try:
                                        t = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                                        if since_dt and t < since_dt:
                                            continue
                                        if until_dt and t > until_dt:
                                            continue
                                    except Exception:
                                        pass

                                results.append({
                                    'source': log_file.name,
                                    'line': text
                                })
                    except Exception:
                        continue
            
            # 限制结果数量
            if len(results) > limit:
                results = results[:limit]

            # 再从数据库中拉取标记为 failed 的运行记录（作为结构化错误摘要）
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # 基于时间范围过滤数据库中的结束时间
                sql = """
                    SELECT spider_name, run_index, close_reason, start_time, end_time
                    FROM spider_run_logs
                    WHERE status = 'failed'
                """
                params = []
                if since_dt:
                    sql += " AND end_time >= %s"
                    params.append(since_dt)
                if until_dt:
                    sql += " AND end_time <= %s"
                    params.append(until_dt)
                sql += " ORDER BY end_time DESC"

                # 添加分页支持
                sql += " LIMIT %s"
                params.append(limit)

                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
                for row in rows:
                    msg = row.get('close_reason') or '运行失败'
                    ts = None
                    if row.get('end_time'):
                        ts = row['end_time'].strftime('%Y-%m-%d %H:%M:%S')
                    line_text = f"{ts or ''} {row.get('spider_name')} #{row.get('run_index')} - {msg}"

                    # 关键词过滤
                    if q and q.strip().lower() not in line_text.lower():
                        continue

                    results.append({
                        'source': f"db_failed:{row.get('spider_name')}#{row.get('run_index')}",
                        'line': line_text
                    })
            except Exception:
                pass
            finally:
                if cursor:
                    cursor.close()

            return {'success': True, 'logs': results, 'count': len(results)}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    @staticmethod
    def _read_last_lines(filepath, n=50):
        """读取文件最后N行"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # 使用 deque 保持最后N行
                return deque(f, maxlen=n)
        except Exception as e:
            return [f"读取失败: {e}"]

    @classmethod
    def get_log_file_content(cls, filename: str, lines: int = 50, offset: int = 0):
        """按页读取单个日志文件内容。

        返回值为 {'success': True, 'name': filename, 'lines': [...], 'has_more': bool}
        `offset` 表示已加载的行数（从文件末尾计数），每次返回最近的 `lines` 条数据，
        偏移量为 0 时返回最后 `lines` 行；偏移量为 `lines` 时返回前一个区间。
        """
        try:
            spider_root = cls.get_spider_root()
            logs_dir = spider_root / 'logs'
            target = logs_dir / filename
            if not target.exists():
                return {'success': False, 'message': '日志文件不存在'}

            # 为分页，从文件末尾取 offset + lines 条，再截取前 lines 条作为本次返回
            to_take = offset + lines
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                dq = deque(f, maxlen=to_take)
                all_taken = list(dq)

            # If there are fewer than to_take lines, then start index is 0
            start = max(0, len(all_taken) - lines)
            chunk = [l.rstrip('\n') for l in all_taken[start:]]

            # Determine if there is more older content
            has_more = False
            # If total file lines > to_take, we have more
            # Try to quickly estimate by checking file size vs read lines; safest is to re-open and count lines if needed
            if len(all_taken) >= to_take:
                # There could be more older lines; set has_more True unless file length equals to_take
                # We'll do a lightweight check: count lines if file is not huge
                try:
                    # If file size < 10MB, count lines to be accurate
                    if target.stat().st_size < 10 * 1024 * 1024:
                        total_lines = 0
                        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                            for _ in f:
                                total_lines += 1
                        has_more = total_lines > to_take
                    else:
                        has_more = True
                except Exception:
                    has_more = True

            return {'success': True, 'name': filename, 'lines': chunk, 'has_more': has_more}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    @classmethod
    def get_spider_stats(cls):
        """获取爬虫统计信息（从数据库读取）"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            today = date.today()
            
            # 1. 获取今日运行统计
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_runs,
                    SUM(error_count) as total_errors,
                    SUM(warning_count) as total_warnings
                FROM spider_run_logs
                WHERE run_date = %s
            """, (today,))
            
            stats_result = cursor.fetchone()
            
            # 2. 获取每个爬虫的今日运行信息
            cursor.execute("""
                SELECT 
                    spider_name,
                    run_index,
                    status,
                    items_crawled,
                    items_stored,
                    error_count,
                    warning_count,
                    timeout_count,
                    start_time,
                    end_time,
                    close_reason
                FROM spider_run_logs
                WHERE run_date = %s
                ORDER BY spider_name, run_index
            """, (today,))
            
            runs = cursor.fetchall()
            
            # 3. 获取超时日志数量
            cursor.execute("""
                SELECT COUNT(*) as timeout_count
                FROM spider_timeout_logs
                WHERE DATE(occurred_at) = %s
            """, (today,))
            
            timeout_result = cursor.fetchone()
            
            # 处理数据
            all_spiders = ['jining_get', 'sd_post', 'jinan_post', 'taian_post', 'zibo_post', 'jiangsu_post']
            spider_info = {
                'jining_get': {'name': '济宁公共资源', 'desc': '济宁市及12区县招标信息'},
                'sd_post': {'name': '山东省政府采购', 'desc': '全省17地市采购公告'},
                'jinan_post': {'name': '济南公共资源', 'desc': '济南市区县招标信息'},
                'taian_post': {'name': '泰安公共资源', 'desc': '泰安市区县招标信息'},
                'zibo_post': {'name': '淄博公共资源', 'desc': '淄博市区县招标信息'},
                'jiangsu_post': {'name': '江苏省公共资源', 'desc': '江苏省公共资源交易中心'}
            }
            
            stats = {
                'total_runs': stats_result['total_runs'] or 0,
                'total_errors': stats_result['total_errors'] or 0,
                'total_warnings': stats_result['total_warnings'] or 0,
                'total_timeouts': timeout_result['timeout_count'] or 0,
                'last_runs': {},
                'failed_spiders': []
            }
            
            # 处理每个爬虫的最新运行记录
            spider_runs = {}
            for run in runs:
                spider_name = run['spider_name']
                if spider_name not in spider_runs or run['run_index'] > spider_runs[spider_name]['run_index']:
                    spider_runs[spider_name] = run
            
            for spider_name, run in spider_runs.items():
                status = run['status']
                
                # 映射状态
                if status == 'running':
                    mapped_status = 'running'
                elif status == 'success':
                    mapped_status = 'success'
                elif status == 'failed':
                    mapped_status = 'failed'
                else:
                    mapped_status = 'stopped'
                
                run_info = {
                    'spider': spider_name,
                    'name': spider_info.get(spider_name, {}).get('name', spider_name),
                    'desc': spider_info.get(spider_name, {}).get('desc', ''),
                    'time': run['end_time'].strftime('%H:%M:%S') if run['end_time'] else run['start_time'].strftime('%H:%M:%S'),
                    'status': mapped_status,
                    'items_crawled': run['items_crawled'],
                    'items_stored': run['items_stored'],
                    'errors': run['error_count'],
                    'warnings': run['warning_count'],
                    'timeouts': run['timeout_count'],
                    'close_reason': run['close_reason']
                }
                
                stats['last_runs'][spider_name] = run_info
                
                if status == 'failed':
                    run_info['error_msg'] = run['close_reason'] or '运行失败'
                    stats['failed_spiders'].append(run_info)
            
            # 检查哪些爬虫今天没有运行记录
            for spider in all_spiders:
                if spider not in spider_runs:
                    stats['failed_spiders'].append({
                        'spider': spider,
                        'name': spider_info.get(spider, {}).get('name', spider),
                        'desc': spider_info.get(spider, {}).get('desc', ''),
                        'status': 'not_run',
                        'time': None,
                        'error_msg': '今日尚未运行'
                    })
            
            cursor.close()
            
            return {'success': True, 'stats': stats}

        except Exception as e:
            # 如果数据库查询失败，返回基于日志的统计作为后备
            return cls._get_spider_stats_from_logs()
        finally:
            if cursor:
                cursor.close()
    
    @classmethod
    def _get_spider_stats_from_logs(cls):
        """从日志文件获取统计（后备方案）"""
        try:
            spider_root = cls.get_spider_root()
            logs_dir = spider_root / 'logs'
            
            stats = {
                'total_runs': 0,
                'total_errors': 0,
                'total_warnings': 0,
                'total_timeouts': 0,
                'last_runs': {},
                'failed_spiders': []
            }
            
            if not logs_dir.exists():
                return {'success': True, 'stats': stats}
            
            all_spiders = ['jining_get', 'sd_post', 'jinan_post', 'taian_post', 'zibo_post', 'jiangsu_post']
            spider_info = {
                'jining_get': {'name': '济宁公共资源', 'desc': '济宁市及12区县招标信息'},
                'sd_post': {'name': '山东省政府采购', 'desc': '全省17地市采购公告'},
                'jinan_post': {'name': '济南公共资源', 'desc': '济南市区县招标信息'},
                'taian_post': {'name': '泰安公共资源', 'desc': '泰安市区县招标信息'},
                'zibo_post': {'name': '淄博公共资源', 'desc': '淄博市区县招标信息'},
                'jiangsu_post': {'name': '江苏省公共资源', 'desc': '江苏省公共资源交易中心'}
            }
            
            today = datetime.now().strftime('%Y%m%d')
            today_logs = list(logs_dir.glob(f'*{today}*.log'))
            
            stats['total_runs'] = len(today_logs)
            
            total_errors = 0
            total_warnings = 0
            
            for log_file in today_logs:
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        error_count = content.lower().count('error')
                        warning_count = content.lower().count('warning')
                        total_errors += error_count
                        total_warnings += warning_count
                except:
                    continue
            
            stats['total_errors'] = total_errors
            stats['total_warnings'] = total_warnings
            
            # 检查未运行的爬虫
            for spider in all_spiders:
                stats['failed_spiders'].append({
                    'spider': spider,
                    'name': spider_info.get(spider, {}).get('name', spider),
                    'desc': spider_info.get(spider, {}).get('desc', ''),
                    'status': 'not_run',
                    'time': None,
                    'error_msg': '今日尚未运行（数据库连接失败）'
                })
            
            return {'success': True, 'stats': stats}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @classmethod
    def get_today_overview(cls):
        """获取今日概览数据"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            today = date.today()
            
            # 今日运行次数
            cursor.execute("""
                SELECT COUNT(*) as count FROM spider_run_logs WHERE run_date = %s
            """, (today,))
            run_count = int(cursor.fetchone()['count'] or 0)
            
            # 今日爬取数据量（含重复）
            cursor.execute("""
                SELECT COALESCE(SUM(items_crawled), 0) as count FROM spider_run_logs WHERE run_date = %s
            """, (today,))
            crawled_count = int(cursor.fetchone()['count'] or 0)
            
            # 今日入库数据量（去重后）
            cursor.execute("""
                SELECT COALESCE(SUM(items_stored), 0) as count FROM spider_run_logs WHERE run_date = %s
            """, (today,))
            stored_count = int(cursor.fetchone()['count'] or 0)
            
            # 今日超时次数
            cursor.execute("""
                SELECT COUNT(*) as count FROM spider_timeout_logs WHERE DATE(occurred_at) = %s
            """, (today,))
            timeout_count = int(cursor.fetchone()['count'] or 0)
            
            # 运行中进程数（优先从实时进程获取，更准确）
            try:
                proc_result = cls.get_spider_processes()
                running_count = int(proc_result.get('count', 0)) if proc_result.get('success') else 0
            except Exception:
                running_count = 0

            # 如果实时检测没有运行中进程，检查数据库中是否有最近 5 分钟内的 running 记录
            if running_count == 0:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM spider_run_logs
                    WHERE run_date = %s
                    AND status = 'running'
                    AND start_time >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                """, (today,))
                running_count = int(cursor.fetchone()['count'] or 0)
            
            # 各爬虫今日运行次数
            cursor.execute("""
                SELECT spider_name, COUNT(*) as count 
                FROM spider_run_logs 
                WHERE run_date = %s 
                GROUP BY spider_name
            """, (today,))
            spider_runs = {row['spider_name']: row['count'] for row in cursor.fetchall()}
            
            cursor.close()
            
            return {
                'success': True,
                'stats': {
                    'total_runs': run_count,
                    'crawled_count': crawled_count,
                    'stored_count': stored_count,
                    'total_timeouts': timeout_count,
                    'running_count': running_count,
                    'spider_runs': spider_runs
                }
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
        finally:
            if cursor:
                cursor.close()

    @classmethod
    def get_timeout_logs(cls, spider_name=None, limit=50):
        """获取超时日志列表"""
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            today = date.today()

            if spider_name:
                cursor.execute("""
                    SELECT
                        id,
                        spider_name,
                        url,
                        timeout_seconds,
                        retry_count,
                        error_message,
                        occurred_at,
                        resolved
                    FROM spider_timeout_logs
                    WHERE spider_name = %s AND DATE(occurred_at) = %s
                    ORDER BY occurred_at DESC
                    LIMIT %s
                """, (spider_name, today, limit))
            else:
                cursor.execute("""
                    SELECT
                        id,
                        spider_name,
                        url,
                        timeout_seconds,
                        retry_count,
                        error_message,
                        occurred_at,
                        resolved
                    FROM spider_timeout_logs
                    WHERE DATE(occurred_at) = %s
                    ORDER BY occurred_at DESC
                    LIMIT %s
                """, (today, limit))

            logs = cursor.fetchall()

            # 格式化数据（保留完整 url 供前端 tooltip 使用）
            formatted_logs = []
            for log in logs:
                raw_url = log['url'] or ''
                formatted_logs.append({
                    'id': log['id'],
                    'spider_name': log['spider_name'],
                    'url': raw_url,
                    'timeout_seconds': log['timeout_seconds'],
                    'retry_count': log['retry_count'],
                    'error_message': log['error_message'][:200] if log['error_message'] else None,
                    'occurred_at': log['occurred_at'].strftime('%Y-%m-%d %H:%M:%S') if log['occurred_at'] else None,
                    'resolved': bool(log['resolved'])
                })

            return {'success': True, 'logs': formatted_logs, 'count': len(formatted_logs)}
        except Exception as e:
            return {'success': False, 'message': str(e)}
        finally:
            if cursor:
                cursor.close()

    @classmethod
    def get_spider_run_history(cls, spider_name=None, days=7):
        """获取爬虫运行历史"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            end_date = date.today()
            start_date = end_date - timedelta(days=days-1)
            
            if spider_name:
                cursor.execute("""
                    SELECT 
                        run_date,
                        run_index,
                        status,
                        items_crawled,
                        items_stored,
                        error_count,
                        timeout_count,
                        duration_seconds,
                        start_time
                    FROM spider_run_logs
                    WHERE spider_name = %s AND run_date BETWEEN %s AND %s
                    ORDER BY run_date DESC, run_index DESC
                """, (spider_name, start_date, end_date))
            else:
                cursor.execute("""
                    SELECT 
                        spider_name,
                        run_date,
                        run_index,
                        status,
                        items_crawled,
                        items_stored,
                        error_count,
                        timeout_count,
                        duration_seconds,
                        start_time
                    FROM spider_run_logs
                    WHERE run_date BETWEEN %s AND %s
                    ORDER BY run_date DESC, start_time DESC
                """, (start_date, end_date))
            
            runs = cursor.fetchall()
            
            # 格式化
            formatted_runs = []
            for run in runs:
                formatted_run = dict(run)
                if run.get('start_time'):
                    formatted_run['start_time'] = run['start_time'].strftime('%Y-%m-%d %H:%M:%S')
                formatted_runs.append(formatted_run)
            
            cursor.close()
            
            return {'success': True, 'runs': formatted_runs, 'count': len(formatted_runs)}
        except Exception as e:
            return {'success': False, 'message': str(e)}
        finally:
            if cursor:
                cursor.close()
    
    @classmethod
    def execute_spider(cls, spider_name, args=None):
        """执行爬虫命令"""
        try:
            import sys
            spider_root = cls.get_spider_root()

            # 构建命令 - 使用当前 Python 解释器运行 scrapy
            cmd = [sys.executable, '-m', 'scrapy.cmdline', 'crawl', spider_name]
            if args:
                cmd.extend(args)

            # 异步执行爬虫（不等待完成）
            process = subprocess.Popen(
                cmd,
                cwd=str(spider_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # 脱离父进程
            )

            return {
                'success': True,
                'message': f'爬虫 {spider_name} 已启动',
                'pid': process.pid
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    @classmethod
    def stop_spider(cls, pid):
        """停止爬虫进程"""
        try:
            import psutil
            
            process = psutil.Process(pid)
            process.terminate()
            
            # 等待进程结束
            gone, alive = psutil.wait_procs([process], timeout=3)
            
            if alive:
                # 强制结束
                for p in alive:
                    p.kill()
            
            return {
                'success': True,
                'message': f'进程 {pid} 已停止'
            }
        except psutil.NoSuchProcess:
            return {
                'success': False,
                'message': f'进程 {pid} 不存在'
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
