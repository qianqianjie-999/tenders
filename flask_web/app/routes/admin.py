"""
管理员功能路由蓝图（2026-10-21 新增，参考采购系统模式）

包含用户管理：列表、创建、编辑、启用/禁用、重置密码、删除。
CSRF：不豁免，前端 AJAX 统一带 X-CSRFToken 头，走全局 CSRFProtect。
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.services.user_service import UserService

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@login_required
def require_admin():
    """仅管理员可访问本蓝图"""
    if not current_user.is_administrator():
        flash('您没有权限访问此页面', 'error')
        return redirect(url_for('main.index'))


def _user_dict(row):
    return {
        'id': row['id'],
        'username': row['username'],
        'full_name': row.get('full_name'),
        'email': row.get('email'),
        'department': row.get('department'),
        'role': row.get('role') or 'user',
        'is_active': bool(row.get('is_active', 1)),
        'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None,
    }


@admin_bp.route('/users')
def users():
    """用户管理页面"""
    return render_template('admin/users.html', users=UserService.list_all())


@admin_bp.route('/users/create', methods=['POST'])
def create_user():
    """创建用户"""
    data = request.get_json(silent=True) or {}

    username = data.get('username', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    department = data.get('department', '').strip()
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({'success': False, 'message': '用户名长度应为 3-20 个字符'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少 6 位'}), 400
    if role not in ['user', 'admin']:
        return jsonify({'success': False, 'message': '无效的角色'}), 400
    if UserService.username_exists(username):
        return jsonify({'success': False, 'message': '用户名已存在'}), 400
    if email and UserService.email_exists(email):
        return jsonify({'success': False, 'message': '邮箱已被使用'}), 400

    UserService.create(username, password, role=role, full_name=full_name,
                       email=email, department=department)
    return jsonify({'success': True, 'message': f'用户 {username} 创建成功'})


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """获取单个用户详情（供编辑模态框填充）"""
    row = UserService.get_by_id(user_id)
    if not row:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    return jsonify({'success': True, 'user': _user_dict(row)})


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """更新用户信息（姓名、邮箱、部门、角色、状态、可选新密码）"""
    row = UserService.get_by_id(user_id)
    if not row:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    data = request.get_json(silent=True) or {}
    fields = {}

    if 'full_name' in data:
        fields['full_name'] = data['full_name'].strip() or None

    if 'email' in data:
        new_email = data['email'].strip()
        if new_email and UserService.email_exists(new_email, exclude_id=user_id):
            return jsonify({'success': False, 'message': '邮箱已被使用'}), 400
        fields['email'] = new_email or None

    if 'department' in data:
        fields['department'] = data['department'].strip() or None

    if 'role' in data:
        new_role = data['role']
        if new_role not in ['user', 'admin']:
            return jsonify({'success': False, 'message': '无效的角色'}), 400
        if user_id == current_user.id and new_role != 'admin':
            return jsonify({'success': False, 'message': '不能取消自己的管理员角色'}), 400
        fields['role'] = new_role

    if 'is_active' in data:
        if user_id == current_user.id and not data['is_active']:
            return jsonify({'success': False, 'message': '不能禁用自己的账户'}), 400
        fields['is_active'] = 1 if data['is_active'] else 0

    if fields:
        UserService.update(user_id, fields)

    new_password = data.get('new_password')
    if new_password:
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': '密码长度至少 6 位'}), 400
        UserService.set_password(user_id, new_password)

    return jsonify({'success': True, 'message': '用户更新成功',
                    'user': _user_dict(UserService.get_by_id(user_id))})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """删除用户（不能删自己；tenders 其他表不引用 users.id，无关联删除限制）"""
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': '不能删除自己的账户'}), 400

    row = UserService.get_by_id(user_id)
    if not row:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    UserService.delete(user_id)
    return jsonify({'success': True, 'message': f'用户 {row["username"]} 已删除'})


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
def reset_user_password(user_id):
    """重置用户密码"""
    row = UserService.get_by_id(user_id)
    if not row:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '')

    if not new_password:
        return jsonify({'success': False, 'message': '新密码不能为空'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少 6 位'}), 400

    UserService.set_password(user_id, new_password)
    return jsonify({'success': True, 'message': '密码重置成功'})
