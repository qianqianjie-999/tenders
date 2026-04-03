from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import get_db_connection
from app.utils.helpers import format_date_for_display
from datetime import datetime

analysis_bp = Blueprint('analysis', __name__, url_prefix='/analysis')


def get_decision_text(decision):
    mapping = {
        'pending': '待定',
        'bid': '投标',
        'nobid': '不投',
        'investigating': '调研中'
    }
    return mapping.get(decision, '待定')


@analysis_bp.route('/')
@login_required
def index():
    """分析标书页面"""
    return render_template('analysis.html')


@analysis_bp.route('/api/list')
def api_list():
    """获取分析标书列表"""
    try:
        keyword = request.args.get('keyword', '')
        decision = request.args.get('decision', 'all')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        offset = (page - 1) * page_size

        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = ["1=1"]
        params = []

        if keyword:
            conditions.append("project_name LIKE %s")
            params.append(f'%{keyword}%')

        if decision != 'all':
            conditions.append("decision = %s")
            params.append(decision)

        where_clause = " AND ".join(conditions)

        # 查询数据
        cursor.execute(f"""
            SELECT id, project_name, publish_date, project_source, project_category,
                   detail_url, bid_open_date, tenderer, control_price, decision,
                   decision_reason, analysis_content, import_time, operator
            FROM analysis_projects
            WHERE {where_clause}
            ORDER BY import_time DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM analysis_projects WHERE {where_clause}", params)
        total = cursor.fetchone()['total']

        # 统计各状态数量
        cursor.execute("SELECT decision, COUNT(*) as count FROM analysis_projects GROUP BY decision")
        stats = {row['decision']: row['count'] for row in cursor.fetchall()}

        cursor.close()

        data = []
        for row in rows:
            data.append({
                'id': row['id'],
                'project_name': row['project_name'],
                'publish_date': format_date_for_display(row['publish_date']),
                'project_source': row['project_source'],
                'project_category': row['project_category'] or '未分类',
                'detail_url': row['detail_url'],
                'bid_open_date': format_date_for_display(row['bid_open_date']) if row['bid_open_date'] else '-',
                'tenderer': row['tenderer'] or '-',
                'control_price': float(row['control_price']) if row['control_price'] else None,
                'decision': row['decision'] or 'pending',
                'decision_text': get_decision_text(row['decision']),
                'decision_reason': row['decision_reason'] or '',
                'analysis_content': row['analysis_content'] or '',
                'import_time': row['import_time'].strftime('%Y-%m-%d %H:%M') if row['import_time'] else '',
                'operator': row['operator'] or '系统'
            })

        return jsonify({
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            },
            'statistics': stats
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@analysis_bp.route('/api/detail/<int:analysis_id>')
def api_detail(analysis_id):
    """获取详情"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analysis_projects WHERE id = %s", (analysis_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return jsonify({'success': False, 'message': '记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': {
                'id': row['id'],
                'project_name': row['project_name'],
                'publish_date': format_date_for_display(row['publish_date']),
                'project_source': row['project_source'],
                'project_category': row['project_category'],
                'detail_url': row['detail_url'],
                'bid_open_date': row['bid_open_date'].strftime('%Y-%m-%d') if row['bid_open_date'] else '',
                'tenderer': row['tenderer'] or '',
                'control_price': float(row['control_price']) if row['control_price'] else '',
                'decision': row['decision'] or 'pending',
                'decision_reason': row['decision_reason'] or '',
                'analysis_content': row['analysis_content'] or '',
                'operator': row['operator'] or ''
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@analysis_bp.route('/api/update/<int:analysis_id>', methods=['PUT'])
def api_update(analysis_id):
    """更新分析信息"""
    try:
        data = request.get_json()

        fields = []
        params = []

        field_mapping = {
            'bid_open_date': 'bid_open_date',
            'tenderer': 'tenderer',
            'control_price': 'control_price',
            'decision': 'decision',
            'decision_reason': 'decision_reason',
            'analysis_content': 'analysis_content',
            'operator': 'operator'
        }

        for key, db_field in field_mapping.items():
            if key in data:
                fields.append(f"{db_field} = %s")
                params.append(data[key] if data[key] != '' else None)

        # 如果没有指定 operator，使用当前登录用户
        if 'operator' not in data and current_user.is_authenticated:
            fields.append("operator = %s")
            params.append(current_user.username)

        if not fields:
            return jsonify({'success': False, 'message': '无更新内容'}), 400

        params.append(analysis_id)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE analysis_projects
            SET {', '.join(fields)}, updated_time = NOW()
            WHERE id = %s
        """, params)
        conn.commit()
        affected = cursor.rowcount
        cursor.close()

        if affected > 0:
            return jsonify({'success': True, 'message': '更新成功'})
        else:
            return jsonify({'success': False, 'message': '记录不存在'}), 404

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@analysis_bp.route('/api/delete/<int:analysis_id>', methods=['DELETE'])
def api_delete(analysis_id):
    """删除记录"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM analysis_projects WHERE id = %s", (analysis_id,))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()

        if affected > 0:
            return jsonify({'success': True, 'message': '删除成功'})
        else:
            return jsonify({'success': False, 'message': '记录不存在'}), 404

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500