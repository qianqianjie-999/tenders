from flask import Blueprint, jsonify

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')

@audit_bp.route('/api/list')
def api_list():
    """项目跟踪审计模块占位 - 返回空数据"""
    return jsonify({
        'success': True,
        'data': [],
        'total': 0,
        'statistics': {}
    })