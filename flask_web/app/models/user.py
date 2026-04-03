"""
用户模型模块
实现基于 Flask-Login 的用户认证功能
"""
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

login_manager = LoginManager()


def init_login(app):
    """初始化 Flask-Login"""
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录以访问此页面'
    login_manager.login_message_category = 'warning'


class User(UserMixin):
    """
    用户类 - 从配置文件加载

    用户信息存储在 .env 文件的 USERS_CONFIG 中
    格式：USERNAME1:PASSWORD_HASH1;USERNAME2:PASSWORD_HASH2
    """
    def __init__(self, username, password_hash):
        self.id = username
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get_password_hash(password):
        """生成密码哈希"""
        return generate_password_hash(password)

    @staticmethod
    def check_password(password_hash, password):
        """验证密码"""
        return check_password_hash(password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login 回调函数：根据用户 ID 加载用户

    从 app config 中读取用户配置
    """
    from flask import current_app
    users = current_app.config.get('USERS', {})
    if user_id in users:
        return User(user_id, users[user_id])
    return None
