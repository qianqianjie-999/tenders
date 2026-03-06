#!/usr/bin/python3
import sys
import logging
import os

# 配置日志
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# 关键：添加项目根目录到 Python 路径
sys.path.insert(0, '/var/www/html/tenders')

# 设置环境
os.environ['FLASK_ENV'] = 'production'

try:
    # 从 flask_web 包导入 app 模块的 create_app 函数
    from flask_web.app import create_app
    
    # 创建应用实例
    application = create_app()
    
    # 强制生产环境配置
    application.config['DEBUG'] = False
    application.config['ENV'] = 'production'
    
except Exception as e:
    import traceback
    logging.error("Application startup failed: %s", str(e))
    logging.error(traceback.format_exc())
    raise
