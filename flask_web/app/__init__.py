from flask import Flask
from datetime import timedelta
from app.config import Config
from app.extensions import close_db
from app.routes.design import design_bp
from app.routes.audit import audit_bp

def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    app.config.from_object(Config)

    # 会话配置 - 关闭浏览器后失效
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 会话有效期 8 小时
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(hours=8)  # 记住我有效期 8 小时

    # 初始化扩展
    from app.models.user import init_login
    init_login(app)

    # 从环境变量加载用户配置到 config
    users = {}
    users_config = Config.USERS_CONFIG if hasattr(Config, 'USERS_CONFIG') else ''
    if users_config:
        for user_entry in users_config.split(';'):
            if ':' in user_entry:
                username, password_hash = user_entry.split(':', 1)
                username = username.strip()
                password_hash = password_hash.strip()
                if username:
                    users[username] = password_hash
    app.config['USERS'] = users
    app.config['USERS_CONFIG'] = users_config

    # 注册蓝图
    from app.routes.main import main_bp
    from app.routes.focus import focus_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.analysis import analysis_bp
    from app.routes.bidding import bidding_bp
    from app.routes.monitor import monitor_bp
    from app.routes.jiangsu import jiangsu_bp
    from app.routes.auth import auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(bidding_bp)
    app.register_blueprint(design_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(jiangsu_bp)
    app.register_blueprint(auth_bp)

    app.teardown_appcontext(close_db)

    return app


