from flask import Blueprint, render_template, request, jsonify, current_app
from app.services.focus_service import FocusService
from app.utils.helpers import format_date_for_display
from app.extensions import get_db_connection


focus_bp = Blueprint('focus', __name__, url_prefix='/focus')


@focus_bp.route('/')
def index():
    """重点关注页面"""
    return render_template('focus.html')


@focus_bp.route('/api/list')
def api_list():
    """API: 获取关注列表"""
    try:
        status = request.args.get('status', 'all')
        keyword = request.args.get('keyword', '')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))

        rows, total, stats = FocusService.get_list(status, keyword, page, page_size)

        data = []
        for row in rows:
            data.append({
                'id': row['id'],
                'project_name': row['project_name'],
                'publish_date': format_date_for_display(row['publish_date']),
                'project_source': row['project_source'],
                'project_category': row['project_category'] or '未分类',
                'detail_url': row['detail_url'],
                'focus_time': row['focus_time'].strftime('%Y-%m-%d %H:%M') if row['focus_time'] else '',
                'status': row['status'],
                'status_text': current_app.config['PROJECT_STATUS'].get(row['status'], '未知'),
                'remark': row['remark'] or ''
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
            'statistics': {
                'total': total,
                'by_status': stats
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/add', methods=['POST'])
def api_add():
    """API: 添加关注"""
    try:
        data = request.get_json()
        if not all(k in data for k in ['project_name', 'publish_date', 'project_source']):
            return jsonify({'success': False, 'message': '缺少必要字段'}), 400

        success, result = FocusService.add(data)
        if success:
            return jsonify({'success': True, 'message': '添加成功', 'id': result})
        else:
            return jsonify({'success': False, 'message': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/update/<int:focus_id>', methods=['PUT'])
def api_update(focus_id):
    """API: 更新状态"""
    try:
        data = request.get_json()
        status = data.get('status')
        remark = data.get('remark')

        if not status:
            return jsonify({'success': False, 'message': '状态不能为空'}), 400

        if FocusService.update_status(focus_id, status, remark):
            return jsonify({'success': True, 'message': '更新成功'})
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/delete', methods=['DELETE'])
def api_delete():
    """API: 取消关注"""
    try:
        data = request.get_json()
        focus_id = data.get('id')
        if not focus_id:
            return jsonify({'success': False, 'message': 'ID不能为空'}), 400

        if FocusService.delete(focus_id):
            return jsonify({'success': True, 'message': '已取消关注'})
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/tracks/<int:focus_id>')
def api_tracks(focus_id):
    """API: 获取跟踪记录"""
    try:
        tracks = FocusService.get_tracks(focus_id)
        data = [{
            'id': t['id'],
            'content': t['record_content'],
            'time': t['record_time'].strftime('%Y-%m-%d %H:%M'),
            'type': t['record_type'] or '其他',
            'operator': t['operator'] or '系统'
        } for t in tracks]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/tracks/<int:focus_id>', methods=['POST'])
def api_add_track(focus_id):
    """API: 添加跟踪记录"""
    try:
        data = request.get_json()
        content = data.get('content')
        record_type = data.get('type', '其他')

        if not content:
            return jsonify({'success': False, 'message': '内容不能为空'}), 400

        track_id = FocusService.add_track(focus_id, content, record_type)
        return jsonify({'success': True, 'message': '添加成功', 'id': track_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/check')
def api_check():
    """检查项目是否已关注"""
    try:
        keys = request.args.get('keys', '').split(',')
        keys = [k for k in keys if k]
        focused = FocusService.check_exists(keys)
        return jsonify({'success': True, 'focused': focused})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@focus_bp.route('/api/move-to-analysis', methods=['POST'])
def api_move_to_analysis():
    """将关注项目转入分析标书表（默认复制模式，保留原记录）"""
    try:
        from datetime import datetime

        data = request.get_json()
        focus_id = data.get('focus_id')
        # ⭐ 关键修改：默认改为 False，保留原记录
        remove_from_focus = data.get('remove_from_focus', False)

        if not focus_id:
            return jsonify({'success': False, 'message': '缺少focus_id'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. 查询原关注记录
        cursor.execute("""
            SELECT project_name, publish_date, project_source, project_category, detail_url
            FROM focus_projects WHERE id = %s
        """, (focus_id,))
        focus = cursor.fetchone()

        if not focus:
            cursor.close()
            return jsonify({'success': False, 'message': '原关注记录不存在'}), 404

        # 2. 检查是否已存在于分析表（避免重复）
        cursor.execute("""
            SELECT id FROM analysis_projects 
            WHERE project_name = %s AND publish_date = %s AND project_source = %s
        """, (focus['project_name'], focus['publish_date'], focus['project_source']))

        if cursor.fetchone():
            cursor.close()
            return jsonify({
                'success': False,
                'message': '该项目已在分析标书列表中'
            }), 400

        # 3. 插入到分析标书表
        cursor.execute("""
            INSERT INTO analysis_projects 
            (project_name, publish_date, project_source, project_category, detail_url, 
             focus_id, import_time, decision, operator, created_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', '系统导入', NOW())
        """, (
            focus['project_name'],
            focus['publish_date'],
            focus['project_source'],
            focus['project_category'],
            focus['detail_url'],
            focus_id,
            datetime.now()
        ))

        analysis_id = cursor.lastrowid

        # 4. 根据参数决定是否删除原记录（默认保留）
        action_msg = '已复制到分析标书模块（原项目仍保留在关注列表）'
        if remove_from_focus:
            cursor.execute("DELETE FROM focus_projects WHERE id = %s", (focus_id,))
            action_msg = '已移动到分析标书模块（已从关注列表移除）'

        conn.commit()
        cursor.close()

        return jsonify({
            'success': True,
            'message': action_msg,
            'analysis_id': analysis_id,
            'retained_in_focus': not remove_from_focus
        })

    except Exception as e:
        import traceback
        current_app.logger.error(f"转入分析标书失败: {str(e)}")
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'}), 500