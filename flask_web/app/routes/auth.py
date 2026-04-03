"""
认证路由模块
处理用户登录、登出等认证相关请求
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required
from app.models.user import User

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

        # 从配置中获取用户列表
        users = current_app.config.get('USERS', {})

        if username in users:
            user = User(username, users[username])
            if User.check_password(users[username], password):
                # 设置为会话级 Cookie（关闭浏览器失效）
                session.permanent = False
                login_user(user, remember=remember)
                flash('登录成功', 'success')
                # 跳转到来源页面或首页
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('main.index'))
            else:
                flash('用户名或密码错误', 'error')
        else:
            flash('用户名或密码错误', 'error')

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
