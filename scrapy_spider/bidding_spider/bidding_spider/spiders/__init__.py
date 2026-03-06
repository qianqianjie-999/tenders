"""
Bidding Spider - 招标信息爬虫
"""
import logging
import sys
from pathlib import Path


def setup_logging():
    """设置项目日志配置"""

    # 创建logs目录
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # 文件处理器
    log_file = log_dir / f'bidding_spider.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # 设置scrapy的日志级别
    logging.getLogger('scrapy').setLevel(logging.WARNING)
    logging.getLogger('twisted').setLevel(logging.WARNING)

    # 创建专门的超时日志记录器
    timeout_logger = logging.getLogger('timeout')
    timeout_file_handler = logging.FileHandler(
        log_dir / 'timeout_errors.log',
        encoding='utf-8',
        mode='a'
    )
    timeout_format = logging.Formatter(
        '[%(asctime)s] [TIMEOUT] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    timeout_file_handler.setFormatter(timeout_format)
    timeout_logger.addHandler(timeout_file_handler)

    # 创建统计日志记录器
    stats_logger = logging.getLogger('stats')
    stats_file_handler = logging.FileHandler(
        log_dir / 'spider_stats.log',
        encoding='utf-8',
        mode='a'
    )
    stats_format = logging.Formatter(
        '[%(asctime)s] [STATS] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    stats_file_handler.setFormatter(stats_format)
    stats_logger.addHandler(stats_file_handler)

    return root_logger


# 初始化日志
logger = setup_logging()