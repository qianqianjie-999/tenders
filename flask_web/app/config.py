import os

# 尝试加载 .env 文件（优先根目录，兼容 flask_web 目录）
try:
    from pathlib import Path
    # 优先尝试从项目根目录加载（tenders/.env）
    env_path = Path(__file__).parent.parent.parent / '.env'
    if not env_path.exists():
        # 回退到 flask_web 目录
        env_path = Path(__file__).parent.parent / '.env'

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)
except Exception:
    pass


class Config:
    # 安全配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # 数据库配置
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER', 'bidding_user')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'bidding_db')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_CHARSET = os.environ.get('DB_CHARSET', 'utf8mb4')

    # 缓存配置
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))

    # 速率限制配置
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_STRATEGY = os.environ.get('RATELIMIT_STRATEGY', 'fixed-window')

    # 关键词列表
    HIGHLIGHT_KEYWORDS = [
        '交通', '信号灯', '监控', '交通信号灯', '电警', '运维', '智能化', '交警',
        '交管大队', '公安局', '交管', '系统集成', '机房', '平安城市', '天网',
        '智慧', '公安', '交通安全', '交通管理', '红绿灯'
    ]

    PROJECT_STATUS = {
        'active': '新关注',
        'contacted': '已跟踪',
        'bid': '持续关注'
    }

    # 分类规则 - 按优先级排序（具体规则在前，宽泛规则在后）
    CATEGORY_RULES = {
        '智能交通': ['信号灯', '交通信号灯', '红绿灯', '电警', '交警', '交管大队', '交管', '交通安全', '交通管理'],
        '大交通': ['交通'],  # 只包含"交通"本身，但会被上面的具体规则优先匹配
        '智能化': ['监控', '智能化', '运维', '系统集成', '机房', '平安城市', '天网', '智慧', '电子警察'],
        '公安招标': ['公安局', '公安'],
        '其他': []
    }

    # 访问控制口令
    ANALYSIS_ACCESS_CODE = os.environ.get('ANALYSIS_ACCESS_CODE', 'kwd12345')

    # 用户配置（从环境变量读取，用于登录认证）
    # 格式：USERNAME1:PASSWORD_HASH1;USERNAME2:PASSWORD_HASH2
    USERS_CONFIG = os.environ.get('USERS_CONFIG', '')
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')