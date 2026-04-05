from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import get_db_connection
from app.utils.helpers import format_date_for_display
from app.decorators import require_auth, require_auth_write
from datetime import datetime
import json

bidding_bp = Blueprint('bidding', __name__, url_prefix='/bidding')


def get_status_text(status):
    mapping = {
        'pending': '进行中',
        'won': '中标',
        'lost': '未中标'
    }
    return mapping.get(status, '进行中')


@bidding_bp.route('/')
@login_required
def index():
    """投标项目页面"""
    return render_template('bidding.html')


@bidding_bp.route('/api/list')
@require_auth
def api_list():
    """获取投标项目列表"""
    try:
        keyword = request.args.get('keyword', '')
        status = request.args.get('status', 'all')
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

        if status != 'all':
            conditions.append("final_status = %s")
            params.append(status)

        where_clause = " AND ".join(conditions)

        # 查询数据
        cursor.execute(f"""
            SELECT b.*, a.decision as analysis_decision
            FROM bidding_projects b
            LEFT JOIN analysis_projects a ON b.analysis_project_id = a.id
            WHERE {where_clause}
            ORDER BY b.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM bidding_projects b WHERE {where_clause}", params)
        total = cursor.fetchone()['total']

        # 统计
        cursor.execute("SELECT final_status, COUNT(*) as count FROM bidding_projects GROUP BY final_status")
        stats = {row['final_status'] or 'pending': row['count'] for row in cursor.fetchall()}

        cursor.close()

        data = []
        for row in rows:
            bid_prices = json.loads(row['bid_prices']) if row['bid_prices'] else []
            data.append({
                'id': row['id'],
                'analysis_project_id': row['analysis_project_id'],
                'project_name': row['project_name'],
                'project_source': row['project_source'],
                'project_category': row['project_category'] or '未分类',
                'publish_date': format_date_for_display(row['publish_date']),
                'detail_url': row['detail_url'],
                'tenderer': row['tenderer'] or '-',
                'control_price': float(row['control_price']) if row['control_price'] else None,
                'bid_document_creator': row['bid_document_creator'] or '-',
                'bid_document_key_points': row['bid_document_key_points'] or '',
                'bid_prices': bid_prices,
                'final_status': row['final_status'] or 'pending',
                'final_status_text': get_status_text(row['final_status']),
                'summary_reason': row['summary_reason'] or '',
                'operator': row['operator'] or '系统',
                'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M') if row['created_at'] else '',
                'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M') if row['updated_at'] else ''
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


@bidding_bp.route('/api/convert/<int:analysis_id>', methods=['POST'])
@require_auth_write
def convert_from_analysis(analysis_id):
    """从分析标书转为投标项目"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT id FROM bidding_projects WHERE analysis_project_id = %s", (analysis_id,))
        if cursor.fetchone():
            cursor.close()
            return jsonify({'success': False, 'message': '该项目已存在投标记录，请勿重复转换'}), 400

        # 获取分析标书数据
        cursor.execute("""
            SELECT project_name, project_source, project_category, publish_date,
                   detail_url, tenderer, control_price, bid_open_date
            FROM analysis_projects
            WHERE id = %s
        """, (analysis_id,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            return jsonify({'success': False, 'message': '分析标书不存在'}), 404

        # 插入投标项目
        cursor.execute("""
            INSERT INTO bidding_projects (
                analysis_project_id, project_name, project_source,
                project_category, publish_date, detail_url, tenderer,
                control_price, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            analysis_id, row['project_name'], row['project_source'],
            row['project_category'], row['publish_date'], row['detail_url'],
            row['tenderer'], row['control_price']
        ))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()

        return jsonify({
            'success': True,
            'message': '转换成功',
            'data': {'id': new_id}
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bidding_bp.route('/api/detail/<int:bidding_id>')
@require_auth
def api_detail(bidding_id):
    """获取投标项目详情"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bidding_projects WHERE id = %s", (bidding_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return jsonify({'success': False, 'message': '记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': {
                'id': row['id'],
                'project_name': row['project_name'],
                'project_source': row['project_source'],
                'project_category': row['project_category'],
                'publish_date': format_date_for_display(row['publish_date']),
                'detail_url': row['detail_url'],
                'tenderer': row['tenderer'] or '',
                'control_price': float(row['control_price']) if row['control_price'] else '',
                'bid_document_creator': row['bid_document_creator'] or '',
                'bid_document_key_points': row['bid_document_key_points'] or '',
                'bid_prices': json.loads(row['bid_prices']) if row['bid_prices'] else [],
                'final_status': row['final_status'] or 'pending',
                'summary_reason': row['summary_reason'] or '',
                'operator': row['operator'] or ''
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bidding_bp.route('/api/update/<int:bidding_id>', methods=['PUT'])
@require_auth_write
def api_update(bidding_id):
    """更新投标项目"""
    try:
        data = request.get_json()
        conn = get_db_connection()
        cursor = conn.cursor()

        # 构造更新字段
        fields = []
        params = []

        field_mapping = {
            'bid_document_creator': 'bid_document_creator',
            'bid_document_key_points': 'bid_document_key_points',
            'bid_prices': 'bid_prices',
            'final_status': 'final_status',
            'summary_reason': 'summary_reason',
            'operator': 'operator'
        }

        for key, db_field in field_mapping.items():
            if key in data:
                if key == 'bid_prices':
                    # JSON 序列化报价信息
                    value = json.dumps(data[key], ensure_ascii=False) if data[key] else None
                else:
                    value = data[key] if data[key] != '' else None

                fields.append(f"{db_field} = %s")
                params.append(value)

        # 如果没有指定 operator，使用当前认证用户
        if 'operator' not in data and hasattr(request, 'auth_user') and request.auth_user:
            fields.append("operator = %s")
            params.append(request.auth_user)

        if not fields:
            return jsonify({'success': False, 'message': '无更新内容'}), 400

        params.append(bidding_id)

        cursor.execute(f"""
            UPDATE bidding_projects
            SET {', '.join(fields)}, updated_at = NOW()
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
# bidding.py
@bidding_bp.route('/api/verify', methods=['POST'])
def verify_access_code():
    """独立验证访问口令（供前端模态框使用）"""
    data = request.get_json()
    access_code = data.get('access_code', '')
    config_code = current_app.config.get('ANALYSIS_ACCESS_CODE', '')
    
    if config_code and access_code == config_code:
        return jsonify({'success': True, 'message': '验证通过'})
    else:
        return jsonify({'success': False, 'message': '口令错误'}), 403