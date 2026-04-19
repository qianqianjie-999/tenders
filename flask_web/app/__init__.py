from flask import Flask
from datetime import timedelta
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import Config
from app.extensions import close_db, init_db_pool, csrf
from app.routes.design import design_bp
from app.routes.audit import audit_bp
from app.utils.exceptions import BaseAPIException

# 初始化缓存
cache = Cache()

# 初始化速率限制
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="redis://localhost:6379/0"  # 使用Redis存储，生产环境推荐
)

def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    app.config.from_object(Config)

    # 会话配置 - 关闭浏览器后失效
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 会话有效期 8 小时
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(hours=8)  # 记住我有效期 8 小时
    
    # 安全配置
    app.config['SESSION_COOKIE_SECURE'] = False  # 内网使用HTTP，设为False
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # 防止JavaScript访问cookie，减少XSS攻击的风险
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 限制cookie的发送范围，防止CSRF攻击
    app.config['PREFERRED_URL_SCHEME'] = 'https'  # 外部访问使用HTTPS，设为https

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
    from app.routes.zhejiang import zhejiang_bp
    from app.routes.auth import auth_bp
    from app.routes.enhanced_monitor import enhanced_monitor_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(bidding_bp)
    app.register_blueprint(design_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(jiangsu_bp)
    app.register_blueprint(zhejiang_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(enhanced_monitor_bp)

    # 为分析模块的验证接口添加CSRF豁免
    from app.routes.analysis import verify_access_code
    csrf.exempt(verify_access_code)
    
    # 为投标模块的验证接口添加CSRF豁免
    from app.routes.bidding import verify_access_code as bidding_verify_access_code
    csrf.exempt(bidding_verify_access_code)
    
    # 为main模块的API接口添加CSRF豁免
    from app.routes.main import api_keywords, api_keyword_detail
    csrf.exempt(api_keywords)
    csrf.exempt(api_keyword_detail)
    
    # 为focus模块的API接口添加CSRF豁免
    from app.routes.focus import api_add, api_update, api_delete, api_add_track, api_move_to_analysis
    csrf.exempt(api_add)
    csrf.exempt(api_update)
    csrf.exempt(api_delete)
    csrf.exempt(api_add_track)
    csrf.exempt(api_move_to_analysis)

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


