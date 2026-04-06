from flask import Flask
from datetime import timedelta
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import Config
from app.extensions import close_db, init_db_pool
from app.routes.design import design_bp
from app.routes.audit import audit_bp
from app.utils.exceptions import BaseAPIException

# 初始化缓存
cache = Cache()

# 初始化CSRF保护
csrf = CSRFProtect()

# 初始化速率限制
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"]
)

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

    # 初始化缓存
    cache.init_app(app)

    # 初始化CSRF保护
    csrf.init_app(app)

    # 初始化速率限制
    limiter.init_app(app)

    # 初始化数据库连接池
    with app.app_context():
        init_db_pool()

    # 注册全局异常处理器
    register_error_handlers(app)

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


def register_error_handlers(app):
    """注册全局异常处理器"""
    
    @app.errorhandler(BaseAPIException)
    def handle_api_exception(error):
        """处理自定义API异常"""
        from flask import jsonify
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """处理404错误"""
        from flask import jsonify
        return jsonify({'success': False, 'message': '资源不存在'}), 404
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """处理500错误"""
        from flask import jsonify
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """处理未预期的异常"""
        from flask import jsonify
        import traceback
        print(f"Unexpected error: {str(error)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500


