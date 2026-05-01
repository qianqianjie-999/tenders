import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys
import json
from datetime import datetime
from typing import Optional, Tuple


# 日志文件命名规范
LOG_FILE_PATTERN = '{prefix}_{spider_name}_{timestamp}.{ext}'
STATS_FILE_PATTERN = 'spider_stats_{spider_name}_{timestamp}.json'
DEFAULT_LOG_PREFIX = 'bidding_spider'


def generate_log_file_path(log_dir: Path, spider_name: str, 
                           timestamp: Optional[str] = None,
                           prefix: str = DEFAULT_LOG_PREFIX) -> Path:
    """
    生成统一格式的日志文件路径
    
    Args:
        log_dir: 日志目录路径
        spider_name: 爬虫名称
        timestamp: 时间戳字符串，默认自动生成
        prefix: 文件名前缀，默认为 'bidding_spider'
    
    Returns:
        日志文件完整路径
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = LOG_FILE_PATTERN.format(
        prefix=prefix,
        spider_name=spider_name,
        timestamp=timestamp,
        ext='log'
    )
    return log_dir / filename


def generate_stats_file_path(log_dir: Path, spider_name: str,
                             timestamp: Optional[str] = None) -> Path:
    """
    生成统一格式的统计文件路径
    
    Args:
        log_dir: 日志目录路径
        spider_name: 爬虫名称
        timestamp: 时间戳字符串，默认自动生成
    
    Returns:
        统计文件完整路径
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = STATS_FILE_PATTERN.format(
        spider_name=spider_name,
        timestamp=timestamp
    )
    return log_dir / filename


def generate_log_paths(log_dir: Path, spider_name: str,
                       timestamp: Optional[str] = None) -> Tuple[Path, Path]:
    """
    一次性生成日志文件和统计文件路径（使用相同时间戳保持一致性）
    
    Args:
        log_dir: 日志目录路径
        spider_name: 爬虫名称
        timestamp: 时间戳字符串，默认自动生成
    
    Returns:
        (日志文件路径, 统计文件路径)
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = generate_log_file_path(log_dir, spider_name, timestamp)
    stats_path = generate_stats_file_path(log_dir, spider_name, timestamp)
    return log_path, stats_path


class JsonFormatter(logging.Formatter):
    """简单的 JSON 格式化器，将记录输出为 JSON 行。"""
    def format(self, record):
        payload = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        # 可选字段
        if record.exc_info:
            payload['exc'] = self.formatException(record.exc_info)
        if hasattr(record, 'extra'):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_spider_logging(log_file: str, level=logging.INFO, when='midnight', backup_count=7, fmt=None, json_output=False):
    """为爬虫进程配置日志文件（带时间轮转），支持 JSON 输出。

    Args:
        log_file: 日志文件路径
        level: 日志级别
        when: 轮转周期（传给 TimedRotatingFileHandler）
        backup_count: 保留天数
        fmt: 文本格式化模板（当 json_output=False 时有效）
        json_output: 是否使用 JSON 每行格式
    """
    logger = logging.getLogger()

    # 默认文本格式
    if fmt is None:
        fmt = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

    # 确保目录存在
    try:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # 检查是否已有针对该路径的 handler
    for h in list(logger.handlers):
        if getattr(h, 'baseFilename', None) == str(log_file):
            return logger

    try:
        handler = TimedRotatingFileHandler(str(log_file), when=when, backupCount=backup_count, encoding='utf-8')
    except Exception:
        handler = logging.FileHandler(str(log_file), encoding='utf-8')

    if json_output:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(fmt)

    handler.setFormatter(formatter)
    handler.setLevel(level)

    # 同时保持 stderr 输出（便于调试）
    stream_handler_exists = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    if not stream_handler_exists:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    logger.addHandler(handler)
    logger.setLevel(level)

    return logger
