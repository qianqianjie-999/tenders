import pymysql
from flask import current_app, g

def get_db_connection():
    """获取数据库连接（兼容旧代码风格）"""
    if 'db_conn' not in g:
        g.db_conn = pymysql.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME'],
            charset=current_app.config['DB_CHARSET'],
            port=current_app.config['DB_PORT'],
            cursorclass=pymysql.cursors.DictCursor
        )
    return g.db_conn

def close_db(e=None):
    """关闭数据库连接"""
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        db_conn.close()