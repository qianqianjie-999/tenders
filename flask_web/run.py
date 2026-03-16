#!/usr/bin/env python3
"""
Flask 应用启动脚本
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    print("="*70)
    print("🚀 启动 Flask 服务")
    print("="*70)
    print("访问地址: http://localhost:5000")
    print("监控页面: http://localhost:5000/monitor/")
    print("="*70)

    # 从环境变量读取 debug 设置，默认为 False（生产环境）
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=5000,
        use_reloader=False
    )
