"""
用户模型模块
实现基于 Flask-Login 的用户认证功能

2026-10-21 改造：用户由 .env USERS_CONFIG 迁移至 bidding_db.users 表
（参考采购系统模式：角色 admin/user、启用禁用、管理员维护）。
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
    """用户类 - 从 users 表记录构造"""

    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.password_hash = row['password_hash']
        self.full_name = row.get('full_name')
        self.email = row.get('email')
        self.department = row.get('department')
        self.role = row.get('role') or 'user'
        self.is_active_field = bool(row.get('is_active', 1))

    # Flask-Login 用 is_active 判断会话有效性：禁用用户已发会话随之失效
    @property
    def is_active(self):
        return self.is_active_field

    def is_administrator(self):
        return self.role == 'admin'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def get_password_hash(password):
        """生成密码哈希（供脚本/管理接口使用）"""
        return generate_password_hash(password)


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 回调：按用户 id 从 users 表加载"""
    from app.services.user_service import UserService
    try:
        row = UserService.get_by_id(int(user_id))
    except Exception:
        return None
    return User(row) if row else None
