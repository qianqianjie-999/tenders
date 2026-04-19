from app.routes.main import main_bp
from app.routes.jiangsu import jiangsu_bp
from app.routes.zhejiang import zhejiang_bp
from app.routes.monitor import monitor_bp
from app.routes.focus import focus_bp
from app.routes.analysis import analysis_bp
from app.routes.bidding import bidding_bp
from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.enhanced_monitor import enhanced_monitor_bp


def register_blueprints(app):
    """注册所有蓝图"""
    app.register_blueprint(main_bp)
    app.register_blueprint(jiangsu_bp)
    app.register_blueprint(zhejiang_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(bidding_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(enhanced_monitor_bp)