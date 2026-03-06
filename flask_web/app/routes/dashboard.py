from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
from app.extensions import get_db_connection

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
def index():
    return render_template('dashboard.html')


@dashboard_bp.route('/api/dashboard')
def api_dashboard():
    try:
        range_days = int(request.args.get('range', 7))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=range_days)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. 投标项目统计 (bidding_projects表)
        cursor.execute("SELECT COUNT(*) as count FROM bidding_projects")
        bidding_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM bidding_projects 
            WHERE final_status = 'pending' OR final_status IS NULL
        """)
        bidding_pending = cursor.fetchone()['count']

        # 投标项目趋势（最近7天每天新增数量）
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM bidding_projects 
            WHERE created_at >= %s 
            GROUP BY DATE(created_at) 
            ORDER BY date
        """, (start_date,))
        bidding_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        # 2. 分析标书统计 (analysis_projects表)
        cursor.execute("SELECT COUNT(*) as count FROM analysis_projects")
        analysis_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM analysis_projects 
            WHERE decision = 'pending' OR decision IS NULL
        """)
        analysis_pending = cursor.fetchone()['count']

        # 分析标书趋势
        cursor.execute("""
            SELECT DATE(import_time) as date, COUNT(*) as count 
            FROM analysis_projects 
            WHERE import_time >= %s 
            GROUP BY DATE(import_time) 
            ORDER BY date
        """, (start_date,))
        analysis_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        # 3. 重点关注统计 (focus_projects表)
        cursor.execute("SELECT COUNT(*) as count FROM focus_projects")
        focus_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM focus_projects 
            WHERE status = 'active'
        """)
        focus_active = cursor.fetchone()['count']

        # 重点关注趋势（按关注时间）
        cursor.execute("""
            SELECT DATE(focus_time) as date, COUNT(*) as count 
            FROM focus_projects 
            WHERE focus_time >= %s 
            GROUP BY DATE(focus_time) 
            ORDER BY date
        """, (start_date,))
        focus_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        # 4. 济宁公共资源统计 (从bidding_info表查询)
        from flask import current_app
        keywords = current_app.config.get('HIGHLIGHT_KEYWORDS', ['济宁', '济南'])

        # 修复：使用参数化查询避免%冲突
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM bidding_info 
            WHERE project_source LIKE %s OR project_source LIKE %s
        """, ('%济宁%', '%jining%'))
        jining_total = cursor.fetchone()['count']

        # 今日新增
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM bidding_info 
            WHERE (project_source LIKE %s OR project_source LIKE %s) 
            AND DATE(created_time) = CURDATE()
        """, ('%济宁%', '%jining%'))
        jining_today = cursor.fetchone()['count']

        # 计算在总数据中的占比
        cursor.execute("SELECT COUNT(*) as count FROM bidding_info")
        total_info = cursor.fetchone()['count']
        jining_percent = round((jining_total / total_info * 100), 1) if total_info > 0 else 0

        # 计算济宁含关键词的项目数（用于统计卡片展示）
        if keywords:
            keyword_conditions = " OR ".join(["project_name LIKE %s" for _ in keywords])
            keyword_params = [f'%{kw}%' for kw in keywords]

            cursor.execute(f"""
                SELECT COUNT(*) as count 
                FROM bidding_info 
                WHERE (project_source LIKE %s OR project_source LIKE %s) 
                AND ({keyword_conditions})
            """, ('%济宁%', '%jining%') + tuple(keyword_params))
            jining_highlight = cursor.fetchone()['count']
        else:
            jining_highlight = 0

        # 济宁项目排名（最近的项目）- 只显示触发关键词的
        if keywords:
            # 构建关键词查询条件
            keyword_conditions = " OR ".join(["project_name LIKE %s" for _ in keywords])
            keyword_params = [f'%{kw}%' for kw in keywords]

            # 查询同时满足：来源是济宁 且 包含关键词 的项目

            sql = f"""
                SELECT project_name, publish_date, created_time, detail_url
                FROM bidding_info 
                WHERE (project_source LIKE %s OR project_source LIKE %s)
                AND ({keyword_conditions})
                ORDER BY created_time DESC 
                LIMIT 5
            """
            cursor.execute(sql, ('%济宁%', '%jining%') + tuple(keyword_params))

            jining_projects = []
            for row in cursor.fetchall():
                # 找出匹配了哪些关键词（用于前端标签展示）
                keywords_found = [kw for kw in keywords if kw in row['project_name']]
                jining_projects.append({
                    'name': row['project_name'][:30] + '...' if len(row['project_name']) > 30 else row['project_name'],
                    'full_name': row['project_name'],  # 保留完整名称用于title
                    'date': row['publish_date'].strftime('%m-%d') if row['publish_date'] else '',
                    'keywords': keywords_found,
                    'url': row['detail_url']  # 使用 detail_url
                })
        else:
            # 如果没有配置关键词，则显示空或提示
            jining_projects = []

        # 5. 数据来源分布统计（全部数据）
        cursor.execute("""
            SELECT project_source as name, COUNT(*) as count 
            FROM bidding_info 
            GROUP BY project_source 
            ORDER BY count DESC 
            LIMIT 10
        """)
        sources = cursor.fetchall()
        total_sources = sum([s['count'] for s in sources])
        sources_list = [{
            'name': s['name'],
            'count': s['count'],
            'percent': round((s['count'] / total_sources * 100), 1) if total_sources > 0 else 0
        } for s in sources]

        # 6. 最新动态（分别查询三个表，避免 UNION 的 collation 冲突）
        recent_activities = []

        # 查询投标项目最近3条
        cursor.execute("""
            SELECT project_name, '投标' as source, created_at as time 
            FROM bidding_projects 
            ORDER BY created_at DESC 
            LIMIT 3
        """)
        for row in cursor.fetchall():
            recent_activities.append({
                'name': row['project_name'][:20] + '...' if len(row['project_name']) > 20 else row['project_name'],
                'source': row['source'],
                'time': row['time']
            })

        # 查询分析标书最近3条
        cursor.execute("""
            SELECT project_name, '分析' as source, import_time as time 
            FROM analysis_projects 
            ORDER BY import_time DESC 
            LIMIT 3
        """)
        for row in cursor.fetchall():
            recent_activities.append({
                'name': row['project_name'][:20] + '...' if len(row['project_name']) > 20 else row['project_name'],
                'source': row['source'],
                'time': row['time']
            })

        # 查询重点关注最近3条
        cursor.execute("""
            SELECT project_name, '关注' as source, focus_time as time 
            FROM focus_projects 
            ORDER BY focus_time DESC 
            LIMIT 3
        """)
        for row in cursor.fetchall():
            recent_activities.append({
                'name': row['project_name'][:20] + '...' if len(row['project_name']) > 20 else row['project_name'],
                'source': row['source'],
                'time': row['time']
            })

        # 按时间排序并取前10条
        recent_activities.sort(key=lambda x: x['time'] or datetime.min, reverse=True)
        recent_activities = recent_activities[:10]

        # 格式化时间字符串
        for item in recent_activities:
            if item['time']:
                item['time'] = item['time'].strftime('%m-%d %H:%M')
            else:
                item['time'] = ''

        cursor.close()

        # 生成趋势图的日期标签和数据
        dates = []
        bidding_trend_data = []
        analysis_trend_data = []
        focus_trend_data = []

        for i in range(range_days - 1, -1, -1):
            date_obj = end_date - timedelta(days=i)
            date_str = date_obj.strftime('%m-%d')
            dates.append(date_str)
            bidding_trend_data.append(bidding_trend.get(date_str, 0))
            analysis_trend_data.append(analysis_trend.get(date_str, 0))
            focus_trend_data.append(focus_trend.get(date_str, 0))

        return jsonify({
            'success': True,
            'data': {
                'bidding': {
                    'count': bidding_count,
                    'pending': bidding_pending
                },
                'analysis': {
                    'count': analysis_count,
                    'pending': analysis_pending
                },
                'focus': {
                    'count': focus_count,
                    'active': focus_active
                },
                'trend': {
                    'labels': dates,
                    'bidding': bidding_trend_data,
                    'analysis': analysis_trend_data,
                    'focus': focus_trend_data
                },
                'jining_detail': {
                    'total': jining_total,
                    'today': jining_today,
                    'highlight': jining_highlight,
                    'avg': round(jining_total / max(range_days, 1), 1),
                    'percent': jining_percent,
                    'rank': 1,  # 可根据实际逻辑计算
                    'top_projects': jining_projects
                },
                'sources': sources_list,
                'recent': recent_activities
            }
        })
    except Exception as e:
        import traceback
        print(f"Dashboard API Error: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500