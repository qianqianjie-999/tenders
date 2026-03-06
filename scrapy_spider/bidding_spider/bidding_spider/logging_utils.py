import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys
import json
from datetime import datetime


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
