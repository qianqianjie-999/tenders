# Scrapy settings for bidding_spider project
import os
import datetime
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 尝试从项目根目录加载 .env 文件（tenders/.env）
try:
    env_path = BASE_DIR.parent.parent / '.env'
    if not env_path.exists():
        # 回退到 bidding_spider 目录
        env_path = BASE_DIR / '.env'

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
except Exception:
    pass

BOT_NAME = 'bidding_spider'

SPIDER_MODULES = ['bidding_spider.spiders']
NEWSPIDER_MODULE = 'bidding_spider.spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 4

# Configure a delay for requests for the same website (default: 0)
DOWNLOAD_DELAY = 1

# The download delay setting will honor only one of:
CONCURRENT_REQUESTS_PER_DOMAIN = 2
# CONCURRENT_REQUESTS_PER_IP 已弃用，移除以兼容新版本 Scrapy
# CONCURRENT_REQUESTS_PER_IP = 2

# Disable cookies (enabled by default)
COOKIES_ENABLED = False

# Enable or disable spider middlewares
# SPIDER_MIDDLEWARES = {
#    'bidding_spider.middlewares.BiddingSpiderSpiderMiddleware': 543,
# }

# Enable or disable downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'scrapy_fake_useragent.middleware.RandomUserAgentMiddleware': 400,
    'bidding_spider.middlewares.TimeoutRetryMiddleware': 550,
    'bidding_spider.middlewares.RequestStatsMiddleware': 600,
}

# Enable or disable extensions
# EXTENSIONS = {
#    'scrapy.extensions.telnet.TelnetConsole': None,
# }

# Configure item pipelines
ITEM_PIPELINES = {
    'bidding_spider.pipelines.MariaDBPipeline': 300,
}

# Enable and configure the AutoThrottle extension (disabled by default)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
HTTPCACHE_ENABLED = False

# Database settings
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'bidding_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'bidding_db')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# ==================== 日志配置 ====================
# 创建日志目录
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 日志级别
LOG_LEVEL = 'INFO'

# 日志格式
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'

# 日志文件配置
LOG_ENABLED = True
LOG_FILE = str(LOG_DIR / f'bidding_spider_{datetime.datetime.now().strftime("%Y%m%d")}.log')
LOG_FILE_APPEND = True
LOG_STDOUT = False

# 超时错误日志文件
TIMEOUT_LOG_FILE = str(LOG_DIR / 'timeout_errors.log')
SLOW_LOG_FILE = str(LOG_DIR / 'scrapy_slow.log')  # 已经存在的文件

# 爬虫性能统计日志
STATS_LOG_FILE = str(LOG_DIR / 'spider_stats.log')

# 错误日志级别文件
ERROR_LOG_FILE = str(LOG_DIR / 'spider_errors.log')

# User agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Timeout settings
DOWNLOAD_TIMEOUT = 30  # 30秒超时
DOWNLOAD_TIMEOUT_LIMIT = 60  # 最大超时时间限制

# 慢请求阈值（毫秒）
SLOW_REQUEST_THRESHOLD = 5000  # 5秒以上的请求被认为是慢请求


# ========== 运行时日志初始化（集成 logging_utils） ==========
try:
    from bidding_spider.logging_utils import setup_spider_logging
    import logging as _logging

    _level = getattr(_logging, LOG_LEVEL.upper(), _logging.INFO)
    # 支持通过环境变量启用 JSON 日志与保留天数
    JSON_LOG = os.getenv('LOG_JSON', 'false').lower() == 'true'
    BACKUP_DAYS = int(os.getenv('LOG_BACKUP_DAYS', 7))
    try:
        setup_spider_logging(LOG_FILE, level=_level, json_output=JSON_LOG, backup_count=BACKUP_DAYS)
    except Exception as _e:
        _logging.getLogger(__name__).warning(f"Failed to setup spider logging: {_e}")
except Exception:
    # 在无法导入或初始化日志时保持默认 Scrapy 日志行为
    pass