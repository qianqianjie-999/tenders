import secrets

from flask import Flask, request, session
from flask_wtf.csrf import CSRFError
from datetime import timedelta
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import Config
from app.extensions import init_db_pool, csrf
from app.routes.design import design_bp
from app.routes.audit import audit_bp
from app.utils.exceptions import BaseAPIException

# 初始化缓存
cache = Cache()

# ---------------------------------------------------------------- 速率限制
# 2026-10-07 修复三处缺陷：
# ① key_func=get_remote_address 在本架构下完全失效——frp 为 **L4 透传**，WSGI 侧
#    看到的 remote_addr 恒为内网跳板地址(192.168.31.75) ⇒ 全公司共用同一个桶
#    （50 req/min），一个人刷新数据看板就会把所有人打成 429。改为按人分桶。
# ② 超限时没有 429 处理器，RateLimitExceeded 落到 errorhandler(Exception) ⇒
#    用户看到 500「服务器内部错误」。见下方 handle_rate_limit。
# ③ 无 Retry-After、无日志线索。
def _rate_limit_key():
    """限流键：登录账号 > 匿名会话 > 远端地址（逐级降级）。"""
    try:
        uid = session.get('user_id') or session.get('_user_id')
        if uid:
            return 'user:%s' % uid
        sid = session.get('_rl_sid')
        if not sid:
            # 匿名请求用随机会话 id 分桶；首次写入随响应 Set-Cookie 下发，
            # 真实浏览器后续请求会带上 ⇒ 同一访客稳定落同一个桶。
            sid = secrets.token_hex(8)
            session['_rl_sid'] = sid
        return 'anon:%s' % sid
    except Exception:                      # 会话不可用 ⇒ 退化为远端地址
        return 'ip:%s' % (get_remote_address() or 'unknown')


def _rate_limit_exempt():
    """`/static/` 不参与默认限流。

    注：本机 /static 实际由 Apache `Alias /static` 直出，请求根本不进 WSGI；
    这里显式声明是为了防止将来改用 Flask 提供静态文件时把额度吃光。
    """
    return request.path.startswith('/static/')


# 初始化速率限制
limiter = Limiter(
    key_func=_rate_limit_key,
    # 原为 ["200 per hour", "50 per minute"] 的**全局单桶**（全公司共享）⇒
    # 改为按人额度：300/min 相对旧的"全公司 50/min"有 6 倍余量，仅作滥用兜底。
    default_limits=["2000 per hour", "300 per minute"],
    default_limits_exempt_when=_rate_limit_exempt,
    # 全局兜底：不带 cookie 的脚本每次请求都是新匿名桶，靠这个粗粒度上限拦住。
    application_limits=["6000 per minute"],
    storage_uri="memory://",  # 进程内存计数（mod_wsgi 2 进程下为近似值）
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

    # 2026-10-21：用户认证由 .env USERS_CONFIG 迁移至 bidding_db.users 表
    # （登录/管理见 routes/auth.py 与 routes/admin.py），此处不再解析 env 账号。

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
    from app.routes.admin import admin_bp
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
    app.register_blueprint(admin_bp)
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
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        """CSRF 校验失败 → 400（2026-10-07 修复）。

        此前没有 CSRFError 处理器，该异常由下面的 errorhandler(Exception)
        兜住 ⇒「缺 token / token 过期」的 POST 一律返回 500「服务器内部错误」：
        既把用户侧的错误渲染成 5xx、往错误日志里灌 traceback，又让用户完全
        看不出“该刷新页面重试”。CSRFError 继承 BadRequest(400)，这里显式
        返回 400 + 可操作提示；浏览器导航给 HTML，XHR/接口给 JSON。
        """
        from flask import Response, current_app, jsonify, request
        # ⚠️ 日志一行必须是纯 ASCII：procurement 的 WSGI 进程 stderr 编码为
        #    ascii（实测 UnicodeEncodeError），中文日志会在 logging 内部抛异常并
        #    往错误日志里灌 --- Logging error --- 转储。故这里统一 backslashreplace。
        line = 'CSRF validation failed: %s %s (%s)' % (request.method,
                                                       request.path,
                                                       error.description)
        current_app.logger.warning(line.encode('ascii', 'backslashreplace').decode('ascii'))
        if 'text/html' in (request.headers.get('Accept') or '') \
                and not request.path.startswith('/api'):
            return Response(_CSRF_ERROR_HTML, status=400,
                            mimetype='text/html; charset=utf-8')
        return jsonify({
            'success': False,
            'message': '会话已过期或页面校验令牌失效，请刷新页面后重试',
            'reason': error.description,
        }), 400

    @app.errorhandler(429)
    def handle_rate_limit(error):
        """超出限流 → 429（2026-10-07 新增）。

        此前没有 429 处理器：RateLimitExceeded 沿 MRO 落到下面的
        `errorhandler(Exception)` ⇒ 被当成 500「服务器内部错误」返回，
        既误导用户（以为服务挂了），又每次往错误日志里灌 traceback。
        """
        from flask import Response, jsonify, request
        line = 'Rate limit exceeded: %s %s' % (request.method, request.path)
        app.logger.warning(line.encode('ascii', 'backslashreplace').decode('ascii'))
        retry = ''
        try:
            retry = error.get_response().headers.get('Retry-After') or ''
        except Exception:
            retry = ''
        if 'text/html' in (request.headers.get('Accept') or '') \
                and not request.path.startswith('/api'):
            resp = Response(_RATE_LIMIT_HTML, status=429,
                            mimetype='text/html; charset=utf-8')
        else:
            resp = jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'})
            resp.status_code = 429
        if retry:
            resp.headers['Retry-After'] = retry
        return resp

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


_RATE_LIMIT_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>429 - 请求过于频繁</title>
<style>
  html,body{height:100%;margin:0}
  body{display:flex;align-items:center;justify-content:center;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
       background:#f5f6f8;color:#24292f}
  .box{max-width:460px;padding:36px 40px;background:#fff;border-radius:12px;
       box-shadow:0 6px 24px rgba(0,0,0,.08);text-align:center}
  h1{margin:0 0 8px;font-size:22px}
  p{margin:8px 0 20px;color:#57606a;line-height:1.7;font-size:14px}
  a{display:inline-block;padding:10px 22px;border-radius:8px;background:#1f6feb;
    color:#fff;text-decoration:none;font-size:14px}
  code{background:#f0f2f5;padding:1px 6px;border-radius:4px;font-size:12px}
</style>
</head>
<body>
  <div class="box">
    <h1>请求过于频繁</h1>
    <p>短时间内操作次数过多，本次请求已被暂时限制。<br>
       请稍等片刻后重试。</p>
    <a href="/">返回首页</a>
    <p style="margin-top:16px;font-size:12px;color:#8c959f">
      错误码 <code>429</code> · 限流
    </p>
  </div>
</body>
</html>
'''


_CSRF_ERROR_HTML = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>400 - 页面已过期</title>\n<style>\n  html,body{height:100%;margin:0}\n  body{display:flex;align-items:center;justify-content:center;\n       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;\n       background:#f5f6f8;color:#24292f}\n  .box{max-width:460px;padding:36px 40px;background:#fff;border-radius:12px;\n       box-shadow:0 6px 24px rgba(0,0,0,.08);text-align:center}\n  h1{margin:0 0 8px;font-size:22px}\n  p{margin:8px 0 20px;color:#57606a;line-height:1.7;font-size:14px}\n  a{display:inline-block;padding:10px 22px;border-radius:8px;background:#1f6feb;\n    color:#fff;text-decoration:none;font-size:14px}\n  a:hover{background:#1a5fd0}\n  code{background:#f0f2f5;padding:1px 6px;border-radius:4px;font-size:12px}\n</style>\n</head>\n<body>\n  <div class="box">\n    <h1>页面已过期</h1>\n    <p>会话或页面校验令牌已失效，本次提交未被处理。<br>\n       请返回后刷新页面，再重新提交一次。</p>\n    <a href="/">返回首页</a>\n    <p style="margin-top:16px;font-size:12px;color:#8c959f">\n      错误码 <code>400</code> · 校验失败（CSRF）\n    </p>\n  </div>\n</body>\n</html>\n'
