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
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'

    # 数据库配置（来自你原来的 DB_CONFIG）
    DB_HOST = 'localhost'
    DB_USER = 'bidding_user'
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'your_password')  # 从环境变量读取，默认 your_password
    DB_NAME = 'bidding_db'
    DB_PORT = 3306
    DB_CHARSET = 'utf8mb4'

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

    #分类规则 - 按优先级排序（具体规则在前，宽泛规则在后）
    CATEGORY_RULES = {
        '智能交通': ['信号灯', '交通信号灯', '红绿灯', '电警', '交警', '交管大队', '交管', '交通安全', '交通管理'],
        '大交通': ['交通'],  # 只包含"交通"本身，但会被上面的具体规则优先匹配
        '智能化': ['监控', '智能化', '运维', '系统集成', '机房', '平安城市', '天网', '智慧', '电子警察'],
        '公安招标': ['公安局', '公安'],
        '其他': []
    }

    # 访问控制口令（从环境变量读取，默认值仅用于本地开发）
    ANALYSIS_ACCESS_CODE = os.environ.get('ANALYSIS_ACCESS_CODE', 'kwd12345')

    # 用户配置（从环境变量读取，用于登录认证）
    # 格式：USERNAME1:PASSWORD_HASH1;USERNAME2:PASSWORD_HASH2
    USERS_CONFIG = os.environ.get('USERS_CONFIG', '')