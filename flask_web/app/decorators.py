"""认证装饰器模块
支持三种认证模式：
1. @require_auth - 读取权限：登录 OR 访问口令，任一即可
2. @require_auth_write - 写入权限：登录 AND 访问口令，必须同时满足
"""
from functools import wraps
from flask import request, jsonify, current_app
from flask_login import current_user


def _check_access_code():
    """检查访问口令是否有效"""
    access_code = request.headers.get('X-Access-Code', '')
    if not access_code:
        access_code = request.args.get('access_code', '')
    config_code = current_app.config.get('ANALYSIS_ACCESS_CODE', '')
    return config_code and access_code and access_code == config_code


def _unauthorized_response(message='未授权访问'):
    return jsonify({
        'success': False,
        'message': message,
        'need_auth': True
    }), 401


def require_auth(f):
    """
    读取权限装饰器：登录 OR 访问口令，任一即可

    适用：列表查询、详情查看
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 已登录
        if current_user.is_authenticated:
            request.auth_method = 'session'
            request.auth_user = current_user.username
            return f(*args, **kwargs)

        # 访问口令
        if _check_access_code():
            request.auth_method = 'access_code'
            request.auth_user = 'access_code_user'
            return f(*args, **kwargs)

        return _unauthorized_response('请先登录或提供访问口令（X-Access-Code）')

    return decorated


def require_auth_write(f):
    """
    写入权限装饰器：登录 AND 访问口令，必须同时满足

    适用：更新、删除、转换等操作

    使用方式：
    - 先登录（cookie session）
    - 请求时附带 X-Access-Code 头或 access_code 参数
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        errors = []

        # 检查登录
        logged_in = current_user.is_authenticated
        if logged_in:
            request.auth_user = current_user.username
        else:
            errors.append('未登录')

        # 检查访问口令
        code_valid = _check_access_code()
        if not code_valid:
            errors.append('访问口令无效或缺失')

        if errors:
            return _unauthorized_response('编辑操作需要同时满足：已登录 + 正确访问口令。（' + '，'.join(errors) + '）')

        request.auth_method = 'session+access_code'
        return f(*args, **kwargs)

    return decorated
