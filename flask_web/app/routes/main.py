from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required
from datetime import date
from app.services.bidding_service import BiddingService
from app.services.keyword_service import KeywordService  # 新增导入
from app.utils.helpers import highlight_keywords, format_date_for_display
from app.extensions import get_db_connection
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    today = date.today().strftime('%Y-%m-%d')
    return render_template('index.html', default_date=today)


@main_bp.route('/api/data')
def api_data():
    try:
        # 支持单日期或日期范围
        query_date = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        category = request.args.get('category', '全部')
        source = request.args.get('source', '全部')
        keyword = request.args.get('keyword', '')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        highlight_only = request.args.get('highlight_only', 'false') == 'true'

        # 确定日期范围
        if start_date and end_date:
            # 使用提供的日期范围
            date_filter_type = 'range'
            date_params = [start_date, end_date]
        elif query_date:
            # 使用单个日期（兼容原有逻辑）
            date_filter_type = 'single'
            date_params = [query_date]
        else:
            # 默认今天
            query_date = date.today().strftime('%Y-%m-%d')
            date_filter_type = 'single'
            date_params = [query_date]

        # 获取数据（修改BiddingService支持范围查询）
        data, total = BiddingService.get_data(
            date_filter_type=date_filter_type,
            date_params=date_params,
            category=category,
            source=source,
            keyword=keyword,
            highlight_only=highlight_only,
            page=page,
            page_size=page_size
        )

        # 处理高亮显示...
        keywords = current_app.config['HIGHLIGHT_KEYWORDS']
        processed_data = []
        for item in data:
            item['original_name'] = item['project_name']
            item['project_name'] = highlight_keywords(item['project_name'], keywords)
            item['project_key'] = f"{item['original_name']}||{item['publish_date']}||{item['project_source']}"
            processed_data.append(item)

        # 统计数据（也需要支持范围）
        if date_filter_type == 'range':
            stats = BiddingService.get_statistics_range(start_date, end_date)
        else:
            stats = BiddingService.get_statistics(query_date)

        return jsonify({
            'success': True,
            'data': processed_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            },
            'statistics': stats,
            'highlight_keywords': keywords,
            'date_filter': {
                'type': date_filter_type,
                'params': date_params
            }
        })

    except Exception as e:
        import traceback
        print(f"API ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/categories')
def api_categories():
    try:
        categories = BiddingService.get_categories()
        return jsonify({'success': True, 'categories': categories})
    except Exception as e:
        import traceback
        print(f"Categories ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/sources')
def api_sources():
    try:
        sources = BiddingService.get_sources()
        return jsonify({'success': True, 'sources': sources})
    except Exception as e:
        import traceback
        print(f"Sources ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500



@main_bp.route('/api/keywords', methods=['GET', 'POST'])
def api_keywords():
    """
    GET: 获取关键词列表
    POST: 添加新关键词
    """
    if request.method == 'GET':
        try:
            # 支持两种模式：简单列表 或 带统计的详细列表
            detailed = request.args.get('detailed', 'false') == 'true'

            if detailed:
                keywords = KeywordService.get_keywords_with_stats()
            else:
                keywords = KeywordService.get_all_keywords()

            return jsonify({
                'success': True,
                'keywords': keywords,
                'total': len(keywords)
            })
        except Exception as e:
            import traceback
            print(f"[API] 获取关键词失败: {e}")
            print(traceback.format_exc())
            return jsonify({'success': False, 'message': str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

            keyword = data.get('keyword', '').strip()
            category = data.get('category', 'general')

            success, message = KeywordService.add_keyword(keyword, category)

            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message}), 400

        except Exception as e:
            import traceback
            print(f"[API] 添加关键词失败: {e}")
            print(traceback.format_exc())
            return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/keywords/<keyword>', methods=['PUT', 'DELETE'])
def api_keyword_detail(keyword):
    """
    PUT: 修改关键词
    DELETE: 删除关键词
    """
    if request.method == 'DELETE':
        try:
            success, message = KeywordService.delete_keyword(keyword)
            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message}), 400
        except Exception as e:
            import traceback
            print(f"[API] 删除关键词失败: {e}")
            print(traceback.format_exc())
            return jsonify({'success': False, 'message': str(e)}), 500

    elif request.method == 'PUT':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

            new_keyword = data.get('new_keyword', '').strip()
            new_category = data.get('new_category')  # 可选

            success, message = KeywordService.update_keyword(
                keyword, new_keyword, new_category
            )

            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message}), 400

        except Exception as e:
            import traceback
            print(f"[API] 修改关键词失败: {e}")
            print(traceback.format_exc())
            return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/keyword-categories')
def api_keyword_categories():
    """获取关键词分类列表"""
    try:
        categories = KeywordService.get_categories()
        return jsonify({
            'success': True,
            'categories': categories
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/dates')
def api_dates():
    """获取有数据的日期列表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT publish_date 
            FROM bidding_info 
            ORDER BY publish_date DESC
            LIMIT 30
        """)
        rows = cursor.fetchall()
        dates = [row['publish_date'].strftime('%Y-%m-%d') for row in rows]
        cursor.close()
        return jsonify({'success': True, 'dates': dates})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/export')
def api_export():
    """导出CSV功能（从原代码迁移）"""
    try:
        from datetime import datetime
        import csv
        import io
        import urllib.parse

        query_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
        category = request.args.get('category', '全部')
        source = request.args.get('source', '全部')
        keyword = request.args.get('keyword', '')
        highlight_only = request.args.get('highlight_only', 'false')

        conn = get_db_connection()
        cursor = conn.cursor()

        # 构建查询条件
        conditions = ["publish_date = %s"]
        params = [query_date]

        if category != '全部' and category:
            conditions.append("project_category = %s")
            params.append(category)

        if source != '全部' and source:
            conditions.append("project_source = %s")
            params.append(source)

        if keyword:
            conditions.append("project_name LIKE %s")
            params.append(f'%{keyword}%')

        if highlight_only == 'true':
            highlight_conditions = []
            for kw in current_app.config['HIGHLIGHT_KEYWORDS']:
                highlight_conditions.append("project_name LIKE %s")
                params.append(f'%{kw}%')
            if highlight_conditions:
                conditions.append("(" + " OR ".join(highlight_conditions) + ")")

        where_clause = " AND ".join(conditions)

        sql = f"""
        SELECT 
            id,
            project_name,
            publish_date,
            detail_url,
            project_source,
            COALESCE(project_category, '未分类') as project_category,
            DATE(crawl_time) as crawl_date,
            created_time
        FROM bidding_info 
        WHERE {where_clause}
        ORDER BY publish_date DESC, id DESC
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # 生成CSV
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            '序号', '项目名称', '发布日期', '详情链接', '项目来源',
            '项目分类', '爬取日期', '创建时间', '是否包含关键词'
        ])

        for idx, row in enumerate(rows, 1):
            project_name = row['project_name']
            has_keyword = any(kw in project_name for kw in current_app.config['HIGHLIGHT_KEYWORDS'])

            writer.writerow([
                idx,
                project_name,
                row['publish_date'].strftime('%Y-%m-%d') if row['publish_date'] else '',
                row['detail_url'] or '',
                row['project_source'] or '',
                row['project_category'] or '未分类',
                row['crawl_date'].strftime('%Y-%m-%d') if row['crawl_date'] else '',
                row['created_time'].strftime('%Y-%m-%d %H:%M:%S') if row['created_time'] else '',
                '是' if has_keyword else '否'
            ])

        output.seek(0)

        # 构建文件名
        filter_desc = []
        if category != '全部':
            filter_desc.append(f"分类_{category}")
        if source != '全部':
            filter_desc.append(f"来源_{source}")
        if keyword:
            short_keyword = keyword[:10] + "..." if len(keyword) > 10 else keyword
            filter_desc.append(f"搜索_{short_keyword}")
        if highlight_only == 'true':
            filter_desc.append("仅高亮")

        filter_suffix = "_" + "_".join(filter_desc) if filter_desc else ""
        filename = f"招标数据_{query_date}{filter_suffix}.csv"
        encoded_filename = urllib.parse.quote(filename, encoding='utf-8')

        from flask import Response
        response = Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )

        cursor.close()
        return response

    except Exception as e:
        import traceback
        print(f"Export ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/keyword-projects')
def api_keyword_projects():
    """获取指定关键词近N天的项目列表（支持分页）"""
    try:
        keyword = request.args.get('keyword', '').strip()
        days = int(request.args.get('days', 30))
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 50))  # 默认50条

        if not keyword:
            return jsonify({'success': False, 'message': '关键词不能为空'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询总数
        cursor.execute("""
            SELECT COUNT(*) as total 
            FROM bidding_info 
            WHERE project_name LIKE %s 
            AND publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """, (f'%{keyword}%', days))
        total = cursor.fetchone()['total']

        # 分页查询
        offset = (page - 1) * page_size
        cursor.execute("""
            SELECT 
                id,
                project_name,
                publish_date,
                detail_url,
                project_source,
                COALESCE(project_category, '未分类') as project_category,
                crawl_time
            FROM bidding_info 
            WHERE project_name LIKE %s 
            AND publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY publish_date DESC, id DESC
            LIMIT %s OFFSET %s
        """, (f'%{keyword}%', days, page_size, offset))

        rows = cursor.fetchall()
        cursor.close()

        # 处理数据...
        keywords = KeywordService.get_all_keywords()
        processed_data = []

        for row in rows:
            is_highlighted = any(kw in row['project_name'] for kw in keywords)
            processed_data.append({
                'id': row['id'],
                'project_name': highlight_keywords(row['project_name'], keywords),
                'original_name': row['project_name'],
                'publish_date': format_date_for_display(row['publish_date']),
                'detail_url': row['detail_url'],
                'project_source': row['project_source'],
                'project_category': row['project_category'],
                'crawl_time': row['crawl_time'].strftime('%Y-%m-%d %H:%M:%S') if row['crawl_time'] else '',
                'is_highlighted': is_highlighted
            })

        return jsonify({
            'success': True,
            'data': processed_data,
            'keyword': keyword,
            'days': days,
            'total': total,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,  # 添加总数
                'total_pages': (total + page_size - 1) // page_size
            }
        })

    except Exception as e:
        import traceback
        print(f"[API] 获取关键词项目失败: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500