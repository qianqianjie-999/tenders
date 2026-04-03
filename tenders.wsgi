#!/usr/bin/python3
import sys
import logging
import os

# 配置日志
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# 添加项目根目录到 Python 路径
sys.path.insert(0, '/var/www/html/tenders')
sys.path.insert(0, '/var/www/html/tenders/flask_web')

# 手动加载 .env 文件（指定 UTF-8 编码）
env_path = '/var/www/html/tenders/.env'
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# 设置环境
os.environ['FLASK_ENV'] = 'production'

try:
    from flask_web.app import create_app
    application = create_app()
    application.config['DEBUG'] = False
except Exception as e:
    import traceback
    logging.error("Application startup failed: %s", str(e))
    logging.error(traceback.format_exc())
    raise
