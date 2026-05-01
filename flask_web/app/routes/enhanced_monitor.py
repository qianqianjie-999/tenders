"""
增强的监控API路由
提供系统性能监控、告警信息等API接口
"""
from flask import Blueprint, jsonify
from app.utils.enhanced_monitor import enhanced_monitor
from app.utils.helpers import handle_api_errors
from flask_login import login_required

enhanced_monitor_bp = Blueprint('enhanced_monitor', __name__, url_prefix='/api/monitor')


@enhanced_monitor_bp.route('/system')
@login_required
@handle_api_errors
def get_system_metrics():
    """获取系统性能指标"""
    metrics = enhanced_monitor.collect_system_metrics()
    
    if metrics:
        return jsonify({
            'success': True,
            'data': metrics.to_dict()
        })
    else:
        return jsonify({
            'success': False,
            'message': '无法获取系统指标'
        }), 500


@enhanced_monitor_bp.route('/alerts')
@login_required
@handle_api_errors
def get_alerts():
    """获取告警列表"""
    level = request.args.get('level')
    limit = int(request.args.get('limit', 50))
    
    alerts = enhanced_monitor.get_alerts(level=level, limit=limit)
    
    return jsonify({
        'success': True,
        'data': alerts,
        'total': len(alerts)
    })


@enhanced_monitor_bp.route('/alerts/clear', methods=['POST'])
@login_required
@handle_api_errors
def clear_alerts():
    """清除所有告警"""
    enhanced_monitor.clear_alerts()
    
    return jsonify({
        'success': True,
        'message': '告警已清除'
    })


@enhanced_monitor_bp.route('/summary')
@login_required
@handle_api_errors
def get_metrics_summary():
    """获取指标摘要"""
    summary = enhanced_monitor.get_metrics_summary()
    
    return jsonify({
        'success': True,
        'data': summary
    })


@enhanced_monitor_bp.route('/health')
def health_check():
    """健康检查接口（无需登录）"""
    try:
        metrics = enhanced_monitor.collect_system_metrics()
        
        if not metrics:
            return jsonify({
                'status': 'unhealthy',
                'message': '无法获取系统指标'
            }), 503
        
        # 检查关键指标
        issues = []
        
        if metrics.cpu_percent > 90:
            issues.append(f"CPU使用率过高: {metrics.cpu_percent:.1f}%")
        
        if metrics.memory_percent > 90:
            issues.append(f"内存使用率过高: {metrics.memory_percent:.1f}%")
        
        if metrics.disk_percent > 95:
            issues.append(f"磁盘使用率过高: {metrics.disk_percent:.1f}%")
        
        if issues:
            return jsonify({
                'status': 'degraded',
                'message': '系统性能下降',
                'issues': issues,
                'metrics': metrics.to_dict()
            }), 200
        else:
            return jsonify({
                'status': 'healthy',
                'message': '系统运行正常',
                'metrics': metrics.to_dict()
            }), 200
            
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'message': '健康检查失败'
        }), 503


from flask import request
