"""
认证路由模块
处理用户登录、登出等认证相关请求
"""
import os as _os
import sys as _sys

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required
from app.models.user import User

# 登录失败限流（2026-10-07 新增）：服务端、账号级、跨进程/跨 worker 共享。
# 本架构下 frp 为 L4 透传，服务端拿不到真实客户端 IP，按 IP 限流无意义。
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from login_guard import LoginGuard

_login_guard = LoginGuard('/var/lib/login_guard/tenders.db',
                          max_fails=5, window=300, name='tenders')

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    用户登录页面

    GET: 显示登录表单
    POST: 处理登录请求
    """
    # 如果已登录，直接跳转到首页
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False) == 'on'  # 复选框值为 'on'

        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('auth/login.html')

        # 登录失败限流（2026-10-07 由 client session 计数迁移到服务端账号级计数）：
        # 旧实现把失败次数写进 Flask session —— session 只签名不加密、且删掉该 cookie
        # 即清零，攻击者换个会话就能无限重试，等于没有限流。
        locked, wait = _login_guard.is_locked(username)
        if locked:
            flash(f'登录失败次数过多，请 {wait} 秒后再试', 'error')
            return render_template('auth/login.html'), 429

        # 从配置中获取用户列表
        users = current_app.config.get('USERS', {})

        if username in users and User.check_password(users.get(username, ''), password):
            _login_guard.reset(username)

            # 设置为会话级 Cookie（关闭浏览器失效）
            session.permanent = False
            user = User(username, users[username])
            login_user(user, remember=remember)
            flash('登录成功', 'success')
            # 跳转到来源页面或首页
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))

        _login_guard.record_failure(username)
        remaining_attempts = _login_guard.remaining_attempts(username)
        if remaining_attempts > 0:
            flash(f'用户名或密码错误，还有 {remaining_attempts} 次尝试机会', 'error')
        else:
            flash('登录失败次数过多，请 5 分钟后再试', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """
    用户登出

    需要登录才能访问
    """
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))
