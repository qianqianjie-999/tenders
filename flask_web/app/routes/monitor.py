"""
爬虫监控路由
提供实时监控API和页面
"""
from flask import Blueprint, render_template, jsonify, request
from app.services.monitor_service import MonitorService

monitor_bp = Blueprint('monitor', __name__, url_prefix='/monitor')


@monitor_bp.route('/')
def index():
    """监控页面"""
    return render_template('monitor.html')


@monitor_bp.route('/api/resources')
def api_resources():
    """API: 获取系统资源"""
    return jsonify(MonitorService.get_system_resources())


@monitor_bp.route('/api/processes')
def api_processes():
    """API: 获取运行的爬虫进程"""
    return jsonify(MonitorService.get_spider_processes())


@monitor_bp.route('/api/logs')
def api_logs():
    """API: 获取日志文件"""
    lines = request.args.get('lines', 50, type=int)
    date_filter = request.args.get('date', 'today')  # 默认只显示当天日志
    # 如果传入 name 参数，则代理到单文件按页读取
    name = request.args.get('name')
    if name:
        offset = request.args.get('offset', 0, type=int)
        result = MonitorService.get_log_file_content(name, lines=lines, offset=offset)
    else:
        result = MonitorService.get_log_files(lines=lines, date_filter=date_filter)

    # 柔性序列化：将不可序列化对象 fallback 为字符串，避免 500 错误
    import json
    from flask import Response

    return Response(json.dumps(result, default=str, ensure_ascii=False), mimetype='application/json')


@monitor_bp.route('/api/error-logs')
def api_error_logs():
    """API: 获取错误日志（管理员查看）"""
    spider_name = request.args.get('spider_name')
    limit = request.args.get('limit', 200, type=int)
    q = request.args.get('q')
    since = request.args.get('since')
    until = request.args.get('until')
    return jsonify(MonitorService.get_error_logs(spider_name=spider_name, limit=limit, q=q, since=since, until=until))


@monitor_bp.route('/api/stats')
def api_stats():
    """API: 获取爬虫统计"""
    return jsonify(MonitorService.get_spider_stats())


@monitor_bp.route('/api/spiders')
def api_spiders():
    """API: 获取所有爬虫列表"""
    spiders = [
        {'name': 'jining_get', 'description': '济宁公共资源交易网', 'source': 'https://www.jnsggzy.cn',
         'schedule': '每天 6/8/10/12/14/16/18/20/22 点整', 'category': '济宁专区'},
        {'name': 'sd_post', 'description': '山东省政府采购网', 'source': 'http://www.ccgp-shandong.gov.cn',
         'schedule': '每天奇数点 55 分', 'category': '省级'},
        {'name': 'jinan_post', 'description': '济南公共资源交易网', 'source': 'https://jnggzy.jinan.gov.cn',
         'schedule': '每天偶数点 45 分', 'category': '市级'},
        {'name': 'taian_post', 'description': '泰安公共资源交易网', 'source': 'http://www.taggzyjy.com.cn',
         'schedule': '每天奇数点 15 分', 'category': '市级'},
        {'name': 'zibo_post', 'description': '淄博公共资源交易网', 'source': 'http://ggzyjy.zibo.gov.cn',
         'schedule': '每天偶数点 30 分', 'category': '市级'}
    ]
    # 获取运行状态与最近统计（包含失败检测）
    processes = MonitorService.get_spider_processes()
    stats_result = MonitorService.get_spider_stats()

    running_names = set()
    if processes.get('success'):
        running_names = {p['spider_name'] for p in processes['processes'] if p.get('spider_name')}

    stats = {}
    last_runs = {}
    if isinstance(stats_result, dict) and stats_result.get('success'):
        stats = stats_result.get('stats', {})
        last_runs = stats.get('last_runs', {})

    for spider in spiders:
        name = spider['name']

        # 优先标记运行中
        if name in running_names:
            spider['status'] = 'running'
        else:
            # 若有最近运行记录，则使用记录中状态（success/failed/not_run/warning）
            run_info = last_runs.get(name)
            if run_info:
                # map run_info.status -> 前端状态
                rstatus = run_info.get('status', '')
                if rstatus == 'failed':
                    spider['status'] = 'failed'
                elif rstatus == 'warning':
                    spider['status'] = 'warning'
                elif rstatus == 'success':
                    spider['status'] = 'stopped'
                else:
                    spider['status'] = rstatus or 'stopped'

                # 附加错误信息与最后运行时间，便于前端展示
                if run_info.get('error_msg'):
                    spider['error_msg'] = run_info.get('error_msg')
                if run_info.get('time'):
                    spider['last_time'] = run_info.get('time')
            else:
                # 今日没有运行记录
                spider['status'] = 'not_run'
                spider['error_msg'] = '今日尚未运行'

    return jsonify({
        'success': True,
        'spiders': spiders
    })


@monitor_bp.route('/api/start', methods=['POST'])
def api_start():
    """API: 启动爬虫"""
    data = request.get_json()
    if not data or 'spider_name' not in data:
        return jsonify({'success': False, 'message': '缺少 spider_name 参数'}), 400
    
    spider_name = data['spider_name']
    args = data.get('args', [])
    
    result = MonitorService.execute_spider(spider_name, args)
    return jsonify(result)


@monitor_bp.route('/api/stop', methods=['POST'])
def api_stop():
    """API: 停止爬虫"""
    data = request.get_json()
    if not data or 'pid' not in data:
        return jsonify({'success': False, 'message': '缺少 pid 参数'}), 400
    
    pid = data['pid']
    result = MonitorService.stop_spider(pid)
    return jsonify(result)


@monitor_bp.route('/api/dashboard')
def api_dashboard():
    """API: 获取监控仪表板完整数据"""
    return jsonify({
        'success': True,
        'data': {
            'resources': MonitorService.get_system_resources(),
            'processes': MonitorService.get_spider_processes(),
            'stats': MonitorService.get_spider_stats()
        }
    })


@monitor_bp.route('/api/overview')
def api_overview():
    """API: 获取今日概览数据（运行次数、获取数据量、超时次数）"""
    return jsonify(MonitorService.get_today_overview())


@monitor_bp.route('/api/timeout-logs')
def api_timeout_logs():
    """API: 获取超时日志"""
    spider_name = request.args.get('spider_name')
    limit = request.args.get('limit', 50, type=int)
    return jsonify(MonitorService.get_timeout_logs(spider_name, limit))


@monitor_bp.route('/api/timeout-logs/<int:log_id>', methods=['PUT'])
def api_resolve_timeout(log_id):
    """API: 标记超时日志为已解决"""
    try:
        from app.extensions import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE spider_timeout_logs
            SET resolved = TRUE, updated_time = NOW()
            WHERE id = %s
        """, (log_id,))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        
        if affected > 0:
            return jsonify({'success': True, 'message': '已标记为已解决'})
        else:
            return jsonify({'success': False, 'message': '记录不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@monitor_bp.route('/api/run-history')
def api_run_history():
    """API: 获取爬虫运行历史"""
    spider_name = request.args.get('spider_name')
    days = request.args.get('days', 7, type=int)
    return jsonify(MonitorService.get_spider_run_history(spider_name, days))
