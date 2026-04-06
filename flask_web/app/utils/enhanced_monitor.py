"""
增强的监控系统模块
提供系统性能监控、告警机制、结构化日志等功能
"""
import os
import time
import psutil
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum


class AlertLevel(Enum):
    """告警级别"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


@dataclass
class SystemMetrics:
    """系统性能指标"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    process_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpiderMetrics:
    """爬虫性能指标"""
    spider_name: str
    run_id: int
    timestamp: str
    items_crawled: int
    items_stored: int
    items_per_second: float
    error_rate: float
    avg_response_time: float
    duration_seconds: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Alert:
    """告警信息"""
    level: str
    source: str
    message: str
    timestamp: str
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnhancedMonitor:
    """增强的监控类"""
    
    def __init__(self):
        self.logger = logging.getLogger('enhanced_monitor')
        self.alerts: List[Alert] = []
        self.metrics_history: List[SystemMetrics] = []
        self.max_history_size = 100
        
        # 告警阈值配置
        self.thresholds = {
            'cpu_percent': float(os.getenv('ALERT_CPU_THRESHOLD', 80.0)),
            'memory_percent': float(os.getenv('ALERT_MEMORY_THRESHOLD', 85.0)),
            'disk_percent': float(os.getenv('ALERT_DISK_THRESHOLD', 90.0)),
            'error_rate': float(os.getenv('ALERT_ERROR_RATE_THRESHOLD', 10.0)),
            'items_per_second_min': float(os.getenv('ALERT_MIN_ITEMS_PER_SECOND', 0.1))
        }
    
    def collect_system_metrics(self) -> SystemMetrics:
        """收集系统性能指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            
            # 网络IO
            network = psutil.net_io_counters()
            
            # 进程数量
            process_count = len(psutil.pids())
            
            metrics = SystemMetrics(
                timestamp=datetime.now().isoformat(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / 1024 / 1024,
                memory_total_mb=memory.total / 1024 / 1024,
                disk_percent=disk.percent,
                disk_used_gb=disk.used / 1024 / 1024 / 1024,
                disk_total_gb=disk.total / 1024 / 1024 / 1024,
                network_bytes_sent=network.bytes_sent,
                network_bytes_recv=network.bytes_recv,
                process_count=process_count
            )
            
            # 添加到历史记录
            self.metrics_history.append(metrics)
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history.pop(0)
            
            # 检查告警
            self._check_system_alerts(metrics)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"收集系统指标失败: {e}")
            return None
    
    def _check_system_alerts(self, metrics: SystemMetrics):
        """检查系统告警"""
        # CPU告警
        if metrics.cpu_percent > self.thresholds['cpu_percent']:
            self.create_alert(
                level=AlertLevel.WARNING,
                source='system',
                message=f"CPU使用率过高: {metrics.cpu_percent:.1f}%",
                details={'cpu_percent': metrics.cpu_percent}
            )
        
        # 内存告警
        if metrics.memory_percent > self.thresholds['memory_percent']:
            self.create_alert(
                level=AlertLevel.WARNING,
                source='system',
                message=f"内存使用率过高: {metrics.memory_percent:.1f}%",
                details={
                    'memory_percent': metrics.memory_percent,
                    'memory_used_mb': metrics.memory_used_mb
                }
            )
        
        # 磁盘告警
        if metrics.disk_percent > self.thresholds['disk_percent']:
            self.create_alert(
                level=AlertLevel.ERROR,
                source='system',
                message=f"磁盘使用率过高: {metrics.disk_percent:.1f}%",
                details={
                    'disk_percent': metrics.disk_percent,
                    'disk_used_gb': metrics.disk_used_gb
                }
            )
    
    def check_spider_alerts(self, spider_metrics: SpiderMetrics):
        """检查爬虫告警"""
        # 错误率告警
        if spider_metrics.error_rate > self.thresholds['error_rate']:
            self.create_alert(
                level=AlertLevel.ERROR,
                source='spider',
                message=f"爬虫错误率过高: {spider_metrics.spider_name} - {spider_metrics.error_rate:.1f}%",
                details={
                    'spider_name': spider_metrics.spider_name,
                    'error_rate': spider_metrics.error_rate
                }
            )
        
        # 爬取速度告警
        if (spider_metrics.items_per_second < self.thresholds['items_per_second_min'] 
            and spider_metrics.duration_seconds > 60):
            self.create_alert(
                level=AlertLevel.WARNING,
                source='spider',
                message=f"爬虫速度过慢: {spider_metrics.spider_name}",
                details={
                    'spider_name': spider_metrics.spider_name,
                    'items_per_second': spider_metrics.items_per_second
                }
            )
    
    def create_alert(self, level: AlertLevel, source: str, message: str, 
                     details: Dict[str, Any] = None):
        """创建告警"""
        alert = Alert(
            level=level.value,
            source=source,
            message=message,
            timestamp=datetime.now().isoformat(),
            details=details or {}
        )
        
        self.alerts.append(alert)
        
        # 记录日志
        log_message = f"[ALERT][{level.value.upper()}] {source}: {message}"
        if level == AlertLevel.CRITICAL:
            self.logger.critical(log_message)
        elif level == AlertLevel.ERROR:
            self.logger.error(log_message)
        elif level == AlertLevel.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
        
        return alert
    
    def get_alerts(self, level: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取告警列表"""
        alerts = self.alerts
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        # 返回最近的告警
        alerts = alerts[-limit:]
        
        return [alert.to_dict() for alert in alerts]
    
    def clear_alerts(self):
        """清除所有告警"""
        self.alerts.clear()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        if not self.metrics_history:
            return {}
        
        recent_metrics = self.metrics_history[-10:]  # 最近10次
        
        return {
            'avg_cpu_percent': sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics),
            'avg_memory_percent': sum(m.memory_percent for m in recent_metrics) / len(recent_metrics),
            'avg_disk_percent': sum(m.disk_percent for m in recent_metrics) / len(recent_metrics),
            'total_alerts': len(self.alerts),
            'alerts_by_level': {
                'critical': len([a for a in self.alerts if a.level == 'critical']),
                'error': len([a for a in self.alerts if a.level == 'error']),
                'warning': len([a for a in self.alerts if a.level == 'warning']),
                'info': len([a for a in self.alerts if a.level == 'info'])
            }
        }


class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.name = name
    
    def _format_log(self, level: str, message: str, **kwargs) -> str:
        """格式化结构化日志"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'logger': self.name,
            'level': level,
            'message': message
        }
        
        # 添加额外字段
        if kwargs:
            log_data['extra'] = kwargs
        
        return json.dumps(log_data, ensure_ascii=False)
    
    def info(self, message: str, **kwargs):
        """记录INFO日志"""
        self.logger.info(self._format_log('INFO', message, **kwargs))
    
    def warning(self, message: str, **kwargs):
        """记录WARNING日志"""
        self.logger.warning(self._format_log('WARNING', message, **kwargs))
    
    def error(self, message: str, **kwargs):
        """记录ERROR日志"""
        self.logger.error(self._format_log('ERROR', message, **kwargs))
    
    def critical(self, message: str, **kwargs):
        """记录CRITICAL日志"""
        self.logger.critical(self._format_log('CRITICAL', message, **kwargs))
    
    def debug(self, message: str, **kwargs):
        """记录DEBUG日志"""
        self.logger.debug(self._format_log('DEBUG', message, **kwargs))


# 全局监控实例
enhanced_monitor = EnhancedMonitor()


def get_structured_logger(name: str) -> StructuredLogger:
    """获取结构化日志记录器"""
    return StructuredLogger(name)
