import pymysql
from dbutils.pooled_db import PooledDB
from flask import current_app, g
from flask_wtf.csrf import CSRFProtect

# 全局连接池实例
connection_pool = None

# 初始化CSRF保护
csrf = CSRFProtect()

def init_db_pool():
    """初始化数据库连接池"""
    global connection_pool
    if connection_pool is None:
        connection_pool = PooledDB(
            creator=pymysql,  # 使用pymysql作为连接创建者
            maxconnections=20,  # 最大连接数
            mincached=2,  # 初始化时创建的空闲连接数
            maxcached=5,  # 连接池中空闲连接的最大数量
            maxshared=3,  # 连接池中共享连接的最大数量
            blocking=True,  # 连接池满时是否阻塞等待
            maxusage=None,  # 单个连接的最大复用次数
            setsession=[],  # 开始会话前执行的命令列表
            ping=1,  # 检查连接是否可用
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME'],
            charset=current_app.config['DB_CHARSET'],
            port=current_app.config['DB_PORT'],
            cursorclass=pymysql.cursors.DictCursor
        )


def get_db_connection():
    """获取数据库连接（使用连接池）"""
    global connection_pool
    if connection_pool is None:
        init_db_pool()
    return connection_pool.connection()

def close_db(e=None):
    """关闭数据库连接"""
    # 连接池会自动管理连接，不需要手动关闭
    pass
