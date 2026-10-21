"""
认证路由模块
处理用户登录、登出、自助修改密码等认证相关请求
"""
import os as _os
import sys as _sys

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.services.user_service import UserService

# 登录失败限流（2026-10-07 新增）：服务端、账号级、跨进程/跨 worker 共享。
# 本架构下 frp 为 L4 透传，服务端拿不到真实客户端 IP，按 IP 限流无意义。
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from login_guard import LoginGuard

_login_guard = LoginGuard('/var/lib/login_guard/tenders.db',
                          max_fails=5, window=300, name='tenders')

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _is_safe_redirect_url(url):
    """验证重定向 URL 是否安全（仅允许站内相对路径）"""
    return bool(url) and url.startswith('/')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    用户登录页面

    GET: 显示登录表单
    POST: 处理登录请求
    """
    # 如果已登录，直接跳转到首页
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False) == 'on'  # 复选框值为 'on'

        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('auth/login.html')

        # 服务端账号级登录失败限流（详见 login_guard.py 头注）
        locked, wait = _login_guard.is_locked(username)
        if locked:
            flash(f'登录失败次数过多，请 {wait} 秒后再试', 'error')
            return render_template('auth/login.html'), 429

        # 2026-10-21：用户由 .env USERS_CONFIG 迁移至 users 表
        row = UserService.get_by_username(username)

        if row and User(row).check_password(password):
            user = User(row)
            if not user.is_active:
                flash('您的账户已被禁用，请联系管理员', 'error')
                return render_template('auth/login.html')

            _login_guard.reset(username)

            # 设置为会话级 Cookie（关闭浏览器失效）
            session.permanent = False
            login_user(user, remember=remember)
            flash('登录成功', 'success')
            # 跳转到来源页面或首页
            next_page = request.args.get('next')
            if _is_safe_redirect_url(next_page):
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


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改当前登录用户的密码（2026-10-21 新增，参考采购系统）"""
    if request.method == 'POST':
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([old_password, new_password, confirm_password]):
            flash('请填写所有字段', 'error')
            return render_template('auth/change_password.html')

        if new_password != confirm_password:
            flash('新密码两次输入不一致', 'error')
            return render_template('auth/change_password.html')

        if len(new_password) < 6:
            flash('新密码长度至少 6 位', 'error')
            return render_template('auth/change_password.html')

        if not current_user.check_password(old_password):
            flash('原密码错误', 'error')
            return render_template('auth/change_password.html')

        UserService.set_password(current_user.id, new_password)
        flash('密码修改成功', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/change_password.html')
