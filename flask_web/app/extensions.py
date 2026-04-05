import pymysql
from pymysqlpool import ConnectionPool
from flask import current_app, g

# 全局连接池实例
connection_pool = None

def init_db_pool():
    """初始化数据库连接池"""
    global connection_pool
    if connection_pool is None:
        connection_pool = ConnectionPool(
            size=10,  # 连接池大小
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
    return connection_pool.get_connection()

def close_db(e=None):
    """关闭数据库连接"""
    # 连接池会自动管理连接，不需要手动关闭
    pass