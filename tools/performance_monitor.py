#!/usr/bin/env python3
"""
性能监控脚本
持续监控系统性能并生成报告
"""
import time
import json
import requests
from datetime import datetime
from collections import deque
import matplotlib.pyplot as plt
import pandas as pd


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, base_url='http://localhost:5000', history_size=100):
        self.base_url = base_url
        self.history_size = history_size
        self.metrics_history = deque(maxlen=history_size)
        self.alerts_history = deque(maxlen=history_size)
        
    def collect_metrics(self):
        """收集性能指标"""
        try:
            # 使用健康检查接口，避免登录认证
            response = requests.get(f'{self.base_url}/api/monitor/health', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['healthy', 'degraded']:
                    metrics = data.get('metrics', {})
                    metrics['timestamp'] = datetime.now().isoformat()
                    self.metrics_history.append(metrics)
                    return metrics
                    
        except Exception as e:
            print(f"收集指标失败: {e}")
            
        return None
    
    def collect_alerts(self):
        """收集告警信息"""
        try:
            response = requests.get(f'{self.base_url}/api/monitor/alerts', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    alerts = data.get('data', [])
                    self.alerts_history.extend(alerts)
                    return alerts
                    
        except Exception as e:
            print(f"收集告警失败: {e}")
            
        return []
    
    def analyze_performance(self):
        """分析性能数据"""
        if len(self.metrics_history) < 2:
            return None
        
        # 转换为DataFrame
        df = pd.DataFrame(list(self.metrics_history))
        
        analysis = {
            'cpu': {
                'current': df['cpu_percent'].iloc[-1],
                'avg': df['cpu_percent'].mean(),
                'max': df['cpu_percent'].max(),
                'min': df['cpu_percent'].min()
            },
            'memory': {
                'current': df['memory_percent'].iloc[-1],
                'avg': df['memory_percent'].mean(),
                'max': df['memory_percent'].max(),
                'min': df['memory_percent'].min()
            },
            'disk': {
                'current': df['disk_percent'].iloc[-1],
                'avg': df['disk_percent'].mean(),
                'max': df['disk_percent'].max(),
                'min': df['disk_percent'].min()
            },
            'alerts_count': len(self.alerts_history)
        }
        
        return analysis
    
    def generate_report(self, output_file='performance_report.json'):
        """生成性能报告"""
        analysis = self.analyze_performance()
        
        if not analysis:
            print("数据不足，无法生成报告")
            return
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'monitoring_period': {
                'start': self.metrics_history[0]['timestamp'] if self.metrics_history else None,
                'end': self.metrics_history[-1]['timestamp'] if self.metrics_history else None,
                'data_points': len(self.metrics_history)
            },
            'performance_analysis': analysis,
            'alerts': list(self.alerts_history),
            'recommendations': self._generate_recommendations(analysis)
        }
        
        # 保存报告
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"性能报告已生成: {output_file}")
        return report
    
    def _generate_recommendations(self, analysis):
        """生成优化建议"""
        recommendations = []
        
        # CPU建议
        if analysis['cpu']['avg'] > 70:
            recommendations.append({
                'type': 'cpu',
                'level': 'warning',
                'message': 'CPU平均使用率较高，建议检查计算密集型任务',
                'value': analysis['cpu']['avg']
            })
        
        # 内存建议
        if analysis['memory']['avg'] > 80:
            recommendations.append({
                'type': 'memory',
                'level': 'warning',
                'message': '内存平均使用率较高，建议检查内存泄漏或增加内存',
                'value': analysis['memory']['avg']
            })
        
        # 磁盘建议
        if analysis['disk']['current'] > 85:
            recommendations.append({
                'type': 'disk',
                'level': 'error',
                'message': '磁盘使用率过高，建议清理磁盘空间',
                'value': analysis['disk']['current']
            })
        
        # 告警建议
        if analysis['alerts_count'] > 10:
            recommendations.append({
                'type': 'alerts',
                'level': 'warning',
                'message': f'告警数量较多({analysis["alerts_count"]})，建议检查系统问题',
                'value': analysis['alerts_count']
            })
        
        return recommendations
    
    def plot_metrics(self, output_file='performance_chart.png'):
        """绘制性能图表"""
        if len(self.metrics_history) < 2:
            print("数据不足，无法绘制图表")
            return
        
        df = pd.DataFrame(list(self.metrics_history))
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('系统性能监控', fontsize=16)
        
        # CPU使用率
        axes[0, 0].plot(df['cpu_percent'], label='CPU %', color='blue')
        axes[0, 0].set_title('CPU使用率')
        axes[0, 0].set_ylabel('百分比 (%)')
        axes[0, 0].legend()
        axes[0, 0].grid(True)
        
        # 内存使用率
        axes[0, 1].plot(df['memory_percent'], label='Memory %', color='green')
        axes[0, 1].set_title('内存使用率')
        axes[0, 1].set_ylabel('百分比 (%)')
        axes[0, 1].legend()
        axes[0, 1].grid(True)
        
        # 磁盘使用率
        axes[1, 0].plot(df['disk_percent'], label='Disk %', color='red')
        axes[1, 0].set_title('磁盘使用率')
        axes[1, 0].set_ylabel('百分比 (%)')
        axes[1, 0].legend()
        axes[1, 0].grid(True)
        
        # 进程数量
        axes[1, 1].plot(df['process_count'], label='Processes', color='purple')
        axes[1, 1].set_title('进程数量')
        axes[1, 1].set_ylabel('数量')
        axes[1, 1].legend()
        axes[1, 1].grid(True)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"性能图表已生成: {output_file}")
        plt.close()
    
    def monitor(self, interval=60, duration=3600):
        """
        持续监控
        
        Args:
            interval: 监控间隔（秒）
            duration: 监控时长（秒）
        """
        print(f"开始性能监控 (间隔: {interval}秒, 时长: {duration}秒)")
        print("=" * 60)
        
        start_time = time.time()
        iteration = 0
        
        while time.time() - start_time < duration:
            iteration += 1
            print(f"\n第 {iteration} 次采集 [{datetime.now().strftime('%H:%M:%S')}]")
            
            # 收集指标
            metrics = self.collect_metrics()
            if metrics:
                print(f"  CPU: {metrics['cpu_percent']:.1f}% | "
                      f"内存: {metrics['memory_percent']:.1f}% | "
                      f"磁盘: {metrics['disk_percent']:.1f}%")
            
            # 收集告警
            alerts = self.collect_alerts()
            if alerts:
                print(f"  新告警: {len(alerts)} 条")
            
            # 等待下次采集
            time.sleep(interval)
        
        print("\n监控结束")
        print("=" * 60)
        
        # 生成报告和图表
        self.generate_report()
        self.plot_metrics()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='系统性能监控工具')
    parser.add_argument('--url', default='http://localhost:5000', help='服务器地址')
    parser.add_argument('--interval', type=int, default=60, help='监控间隔（秒）')
    parser.add_argument('--duration', type=int, default=3600, help='监控时长（秒）')
    parser.add_argument('--report', action='store_true', help='仅生成报告')
    
    args = parser.parse_args()
    
    monitor = PerformanceMonitor(base_url=args.url)
    
    if args.report:
        # 仅生成报告模式
        print("收集数据中...")
        for _ in range(10):  # 收集10次数据
            monitor.collect_metrics()
            monitor.collect_alerts()
            time.sleep(5)
        
        monitor.generate_report()
        monitor.plot_metrics()
    else:
        # 持续监控模式
        monitor.monitor(interval=args.interval, duration=args.duration)


if __name__ == '__main__':
    main()
