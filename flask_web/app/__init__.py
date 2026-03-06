from flask import Flask
from app.config import Config
from app.extensions import close_db
from app.routes.design import design_bp
from app.routes.audit import audit_bp

def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    app.config.from_object(Config)

    # 注册蓝图
    from app.routes.main import main_bp
    from app.routes.focus import focus_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.analysis import analysis_bp
    from app.routes.bidding import bidding_bp
    from app.routes.monitor import monitor_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(bidding_bp)
    app.register_blueprint(design_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(monitor_bp)

    app.teardown_appcontext(close_db)

    return app


