from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
from app.extensions import get_db_connection

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
def index():
    return render_template('dashboard.html')


@dashboard_bp.route('/api/dashboard')
def api_dashboard():
    conn = None
    cursor = None
    try:
        range_days = int(request.args.get('range', 7))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=range_days)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM bidding_projects")
        bidding_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM bidding_projects
            WHERE final_status = 'pending' OR final_status IS NULL
        """)
        bidding_pending = cursor.fetchone()['count']

        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM bidding_projects
            WHERE created_at >= %s
            GROUP BY DATE(created_at)
            ORDER BY date
        """, (start_date,))
        bidding_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as count FROM analysis_projects")
        analysis_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM analysis_projects
            WHERE decision = 'pending' OR decision IS NULL
        """)
        analysis_pending = cursor.fetchone()['count']

        cursor.execute("""
            SELECT DATE(import_time) as date, COUNT(*) as count
            FROM analysis_projects
            WHERE import_time >= %s
            GROUP BY DATE(import_time)
            ORDER BY date
        """, (start_date,))
        analysis_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as count FROM focus_projects")
        focus_count = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM focus_projects
            WHERE status = 'active'
        """)
        focus_active = cursor.fetchone()['count']

        cursor.execute("""
            SELECT DATE(focus_time) as date, COUNT(*) as count
            FROM focus_projects
            WHERE focus_time >= %s
            GROUP BY DATE(focus_time)
            ORDER BY date
        """, (start_date,))
        focus_trend = {row['date'].strftime('%m-%d'): row['count'] for row in cursor.fetchall()}

        from app.services.keyword_service import KeywordService
        keywords = KeywordService.get_all_keywords()

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM bidding_info
            WHERE project_source LIKE %s OR project_source LIKE %s
        """, ('%济宁%', '%jining%'))
        jining_total = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM bidding_info
            WHERE (project_source LIKE %s OR project_source LIKE %s)
            AND DATE(created_time) = CURDATE()
        """, ('%济宁%', '%jining%'))
        jining_today = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM bidding_info")
        total_info = cursor.fetchone()['count']
        jining_percent = round((jining_total / total_info * 100), 1) if total_info > 0 else 0

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

        if keywords:
            keyword_conditions = " OR ".join(["project_name LIKE %s" for _ in keywords])
            keyword_params = [f'%{kw}%' for kw in keywords]

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
                keywords_found = [kw for kw in keywords if kw in row['project_name']]
                jining_projects.append({
                    'name': row['project_name'][:30] + '...' if len(row['project_name']) > 30 else row['project_name'],
                    'full_name': row['project_name'],
                    'date': row['publish_date'].strftime('%m-%d') if row['publish_date'] else '',
                    'keywords': keywords_found,
                    'url': row['detail_url']
                })
        else:
            jining_projects = []

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

        recent_activities = []

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

        recent_activities.sort(key=lambda x: x['time'] or datetime.min, reverse=True)
        recent_activities = recent_activities[:10]

        for item in recent_activities:
            if item['time']:
                item['time'] = item['time'].strftime('%m-%d %H:%M')
            else:
                item['time'] = ''

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
                'bidding': {'count': bidding_count, 'pending': bidding_pending},
                'analysis': {'count': analysis_count, 'pending': analysis_pending},
                'focus': {'count': focus_count, 'active': focus_active},
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
                    'rank': 1,
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
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
