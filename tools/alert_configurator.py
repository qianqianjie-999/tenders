#!/usr/bin/env python3
"""
告警配置工具
用于配置和管理告警阈值
"""
import os
import json
from datetime import datetime


class AlertConfigurator:
    """告警配置器"""
    
    def __init__(self, env_file='.env'):
        self.env_file = env_file
        self.config = self._load_config()
    
    def _load_config(self):
        """加载当前配置"""
        config = {
            'ALERT_CPU_THRESHOLD': float(os.getenv('ALERT_CPU_THRESHOLD', 80.0)),
            'ALERT_MEMORY_THRESHOLD': float(os.getenv('ALERT_MEMORY_THRESHOLD', 85.0)),
            'ALERT_DISK_THRESHOLD': float(os.getenv('ALERT_DISK_THRESHOLD', 90.0)),
            'ALERT_ERROR_RATE_THRESHOLD': float(os.getenv('ALERT_ERROR_RATE_THRESHOLD', 10.0)),
            'ALERT_MIN_ITEMS_PER_SECOND': float(os.getenv('ALERT_MIN_ITEMS_PER_SECOND', 0.1))
        }
        return config
    
    def show_current_config(self):
        """显示当前配置"""
        print("=" * 60)
        print("当前告警配置")
        print("=" * 60)
        print()
        
        descriptions = {
            'ALERT_CPU_THRESHOLD': 'CPU使用率告警阈值 (%)',
            'ALERT_MEMORY_THRESHOLD': '内存使用率告警阈值 (%)',
            'ALERT_DISK_THRESHOLD': '磁盘使用率告警阈值 (%)',
            'ALERT_ERROR_RATE_THRESHOLD': '错误率告警阈值 (%)',
            'ALERT_MIN_ITEMS_PER_SECOND': '最小爬取速度 (项/秒)'
        }
        
        for key, value in self.config.items():
            desc = descriptions.get(key, key)
            print(f"{desc}: {value}")
        
        print()
    
    def update_config(self, key, value):
        """更新配置"""
        if key not in self.config:
            print(f"错误: 未知的配置项 '{key}'")
            return False
        
        try:
            self.config[key] = float(value)
            print(f"✓ 已更新 {key} = {value}")
            return True
        except ValueError:
            print(f"错误: 无效的数值 '{value}'")
            return False
    
    def save_to_env(self):
        """保存配置到.env文件"""
        try:
            # 读取现有.env文件
            env_lines = []
            if os.path.exists(self.env_file):
                with open(self.env_file, 'r', encoding='utf-8') as f:
                    env_lines = f.readlines()
            
            # 更新或添加配置
            updated_keys = set()
            new_lines = []
            
            for line in env_lines:
                stripped = line.strip()
                if '=' in stripped and not stripped.startswith('#'):
                    key = stripped.split('=')[0]
                    if key in self.config:
                        # 更新现有配置
                        new_lines.append(f"{key}={self.config[key]}\n")
                        updated_keys.add(key)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            # 添加新配置
            if updated_keys != set(self.config.keys()):
                if new_lines and new_lines[-1].strip():
                    new_lines.append('\n')
                
                new_lines.append('# ========================================\n')
                new_lines.append('# 告警配置\n')
                new_lines.append('# ========================================\n')
                
                for key, value in self.config.items():
                    if key not in updated_keys:
                        new_lines.append(f"{key}={value}\n")
            
            # 写入文件
            with open(self.env_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            print(f"\n✓ 配置已保存到 {self.env_file}")
            return True
            
        except Exception as e:
            print(f"错误: 保存配置失败 - {e}")
            return False
    
    def recommend_config(self, system_type='general'):
        """
        推荐配置
        
        Args:
            system_type: 系统类型 (general, high_performance, low_resource)
        """
        recommendations = {
            'general': {
                'ALERT_CPU_THRESHOLD': 80.0,
                'ALERT_MEMORY_THRESHOLD': 85.0,
                'ALERT_DISK_THRESHOLD': 90.0,
                'ALERT_ERROR_RATE_THRESHOLD': 10.0,
                'ALERT_MIN_ITEMS_PER_SECOND': 0.1
            },
            'high_performance': {
                'ALERT_CPU_THRESHOLD': 90.0,
                'ALERT_MEMORY_THRESHOLD': 90.0,
                'ALERT_DISK_THRESHOLD': 85.0,
                'ALERT_ERROR_RATE_THRESHOLD': 5.0,
                'ALERT_MIN_ITEMS_PER_SECOND': 1.0
            },
            'low_resource': {
                'ALERT_CPU_THRESHOLD': 70.0,
                'ALERT_MEMORY_THRESHOLD': 75.0,
                'ALERT_DISK_THRESHOLD': 95.0,
                'ALERT_ERROR_RATE_THRESHOLD': 15.0,
                'ALERT_MIN_ITEMS_PER_SECOND': 0.05
            }
        }
        
        if system_type not in recommendations:
            print(f"错误: 未知的系统类型 '{system_type}'")
            print("可用类型: general, high_performance, low_resource")
            return
        
        print("=" * 60)
        print(f"推荐配置 - {system_type}")
        print("=" * 60)
        print()
        
        recommended = recommendations[system_type]
        
        for key, value in recommended.items():
            current = self.config[key]
            status = '✓' if current == value else '→'
            print(f"{status} {key}: {current} → {value}")
        
        print()
        
        # 应用推荐配置
        choice = input("是否应用推荐配置? (y/n): ")
        if choice.lower() == 'y':
            self.config.update(recommended)
            print("✓ 已应用推荐配置")
    
    def test_alerts(self):
        """测试告警功能"""
        print("=" * 60)
        print("测试告警功能")
        print("=" * 60)
        print()
        
        try:
            from app.utils.enhanced_monitor import enhanced_monitor, AlertLevel
            
            # 创建测试告警
            test_alerts = [
                (AlertLevel.INFO, 'system', '测试信息告警'),
                (AlertLevel.WARNING, 'system', '测试警告告警'),
                (AlertLevel.ERROR, 'spider', '测试错误告警'),
                (AlertLevel.CRITICAL, 'database', '测试严重告警')
            ]
            
            for level, source, message in test_alerts:
                alert = enhanced_monitor.create_alert(level, source, message)
                print(f"✓ 创建告警: [{level.value.upper()}] {message}")
            
            print()
            print(f"当前告警总数: {len(enhanced_monitor.alerts)}")
            
            # 清除测试告警
            choice = input("\n是否清除测试告警? (y/n): ")
            if choice.lower() == 'y':
                enhanced_monitor.clear_alerts()
                print("✓ 测试告警已清除")
            
        except Exception as e:
            print(f"错误: 测试失败 - {e}")
    
    def interactive_config(self):
        """交互式配置"""
        print("=" * 60)
        print("告警配置工具")
        print("=" * 60)
        print()
        
        while True:
            print("\n选项:")
            print("1. 查看当前配置")
            print("2. 修改配置")
            print("3. 应用推荐配置")
            print("4. 测试告警功能")
            print("5. 保存配置")
            print("6. 退出")
            print()
            
            choice = input("请选择 (1-6): ")
            
            if choice == '1':
                self.show_current_config()
            
            elif choice == '2':
                self.show_current_config()
                print("\n可配置项:")
                for i, key in enumerate(self.config.keys(), 1):
                    print(f"{i}. {key}")
                
                key_choice = input("\n选择配置项 (1-5): ")
                try:
                    key_idx = int(key_choice) - 1
                    key = list(self.config.keys())[key_idx]
                    value = input(f"输入新值 (当前: {self.config[key]}): ")
                    self.update_config(key, value)
                except (ValueError, IndexError):
                    print("错误: 无效的选择")
            
            elif choice == '3':
                print("\n系统类型:")
                print("1. general - 通用配置")
                print("2. high_performance - 高性能服务器")
                print("3. low_resource - 低资源环境")
                
                type_choice = input("选择系统类型 (1-3): ")
                type_map = {'1': 'general', '2': 'high_performance', '3': 'low_resource'}
                system_type = type_map.get(type_choice)
                
                if system_type:
                    self.recommend_config(system_type)
                else:
                    print("错误: 无效的选择")
            
            elif choice == '4':
                self.test_alerts()
            
            elif choice == '5':
                self.save_to_env()
            
            elif choice == '6':
                print("\n再见!")
                break
            
            else:
                print("错误: 无效的选择")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='告警配置工具')
    parser.add_argument('--env', default='.env', help='.env文件路径')
    parser.add_argument('--show', action='store_true', help='显示当前配置')
    parser.add_argument('--recommend', choices=['general', 'high_performance', 'low_resource'],
                        help='应用推荐配置')
    
    args = parser.parse_args()
    
    configurator = AlertConfigurator(env_file=args.env)
    
    if args.show:
        configurator.show_current_config()
    elif args.recommend:
        configurator.recommend_config(args.recommend)
        configurator.save_to_env()
    else:
        configurator.interactive_config()


if __name__ == '__main__':
    main()
