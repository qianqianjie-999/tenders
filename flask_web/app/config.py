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


def _require_secret_key():
    """SECRET_KEY 必须由部署注入；缺失或仍是占位常量时拒绝启动。"""
    _bad = {
        'dev-secret-key-change-in-production', 'change_me_secret',
        'your_secret_key_here', 'your-secret-key-here',
    }
    _v = (os.environ.get('SECRET_KEY') or '').strip()
    if not _v or _v in _bad:
        raise RuntimeError('SECRET_KEY 未配置或仍为占位常量，拒绝启动（tenders）')
    return _v


class Config:
    # 安全配置
    # 2026-10-07 修复：原兜底值是公开常量，环境变量缺失即静默降级 ⇒ fail-closed。
    # （tenders.wsgi 会显式加载 tenders/.env，正常情况下一定有值）
    SECRET_KEY = _require_secret_key()
    
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

    # 2026-10-21：用户认证迁移至 bidding_db.users 表，USERS_CONFIG 已废弃
    # （init_users.py 可读取旧 .env 中的 USERS_CONFIG 做一次性迁移）

    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')