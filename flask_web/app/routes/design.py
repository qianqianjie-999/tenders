from flask import Blueprint, jsonify

design_bp = Blueprint('design', __name__, url_prefix='/design')

@design_bp.route('/api/list')
def api_list():
    """方案设计模块占位 - 返回空数据"""
    return jsonify({
        'success': True,
        'data': [],
        'total': 0,
        'statistics': {}
    })