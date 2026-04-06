#!/usr/bin/env python3
"""
系统优化功能测试脚本
用于验证所有优化功能是否正常工作
"""
import sys
import os
import time
import requests
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))

class OptimizationTester:
    """优化功能测试器"""
    
    def __init__(self, base_url='http://localhost:5000'):
        self.base_url = base_url
        self.test_results = []
        
    def add_result(self, test_name, success, message='', details=None):
        """添加测试结果"""
        result = {
            'test_name': test_name,
            'success': success,
            'message': message,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        # 打印结果
        status = '✅ PASS' if success else '❌ FAIL'
        print(f"{status} - {test_name}: {message}")
        if details and not success:
            print(f"   Details: {details}")
    
    def test_health_check(self):
        """测试健康检查接口"""
        try:
            response = requests.get(f'{self.base_url}/api/monitor/health', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['healthy', 'degraded']:
                    self.add_result(
                        '健康检查接口',
                        True,
                        f"系统状态: {data.get('status')}"
                    )
                else:
                    self.add_result(
                        '健康检查接口',
                        False,
                        f"系统状态异常: {data.get('status')}"
                    )
            else:
                self.add_result(
                    '健康检查接口',
                    False,
                    f"HTTP状态码: {response.status_code}"
                )
        except Exception as e:
            self.add_result('健康检查接口', False, f'请求失败: {str(e)}')
    
    def test_system_metrics(self):
        """测试系统性能指标接口"""
        try:
            response = requests.get(f'{self.base_url}/api/monitor/system', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and 'data' in data:
                    metrics = data['data']
                    self.add_result(
                        '系统性能指标',
                        True,
                        f"CPU: {metrics.get('cpu_percent', 0):.1f}%, "
                        f"内存: {metrics.get('memory_percent', 0):.1f}%"
                    )
                else:
                    self.add_result('系统性能指标', False, '数据格式错误')
            else:
                self.add_result(
                    '系统性能指标',
                    False,
                    f"HTTP状态码: {response.status_code}"
                )
        except Exception as e:
            self.add_result('系统性能指标', False, f'请求失败: {str(e)}')
    
    def test_alerts_api(self):
        """测试告警接口"""
        try:
            response = requests.get(f'{self.base_url}/api/monitor/alerts', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    alerts_count = data.get('total', 0)
                    self.add_result(
                        '告警接口',
                        True,
                        f"当前告警数: {alerts_count}"
                    )
                else:
                    self.add_result('告警接口', False, '数据格式错误')
            else:
                self.add_result(
                    '告警接口',
                    False,
                    f"HTTP状态码: {response.status_code}"
                )
        except Exception as e:
            self.add_result('告警接口', False, f'请求失败: {str(e)}')
    
    def test_cache_functionality(self):
        """测试缓存功能"""
        try:
            from app import create_app
            from app.utils.helpers import cache
            
            app = create_app()
            with app.app_context():
                # 测试缓存写入
                cache.set('test_key', 'test_value', timeout=10)
                
                # 测试缓存读取
                value = cache.get('test_key')
                
                if value == 'test_value':
                    self.add_result('缓存功能', True, '缓存读写正常')
                else:
                    self.add_result('缓存功能', False, f'缓存值不匹配: {value}')
                    
        except Exception as e:
            self.add_result('缓存功能', False, f'测试失败: {str(e)}')
    
    def test_bloom_filter(self):
        """测试布隆过滤器"""
        try:
            from pybloom_live import ScalableBloomFilter
            
            # 创建布隆过滤器
            bf = ScalableBloomFilter(initial_capacity=1000, error_rate=0.001)
            
            # 添加元素
            test_items = ['item1', 'item2', 'item3']
            for item in test_items:
                bf.add(item)
            
            # 检查元素是否存在
            all_exist = all(item in bf for item in test_items)
            
            if all_exist:
                self.add_result('布隆过滤器', True, '布隆过滤器工作正常')
            else:
                self.add_result('布隆过滤器', False, '元素检测失败')
                
        except Exception as e:
            self.add_result('布隆过滤器', False, f'测试失败: {str(e)}')
    
    def test_password_validation(self):
        """测试密码强度验证"""
        try:
            from tools.generate_password import validate_password_strength
            
            # 测试弱密码
            weak_passwords = [
                '123456',
                'password',
                'abc123',
                'Password1'
            ]
            
            # 测试强密码
            strong_password = 'StrongPass123!@#'
            
            # 验证弱密码应该失败
            weak_fail = all(
                not validate_password_strength(pwd)[0] 
                for pwd in weak_passwords
            )
            
            # 验证强密码应该成功
            strong_pass, errors = validate_password_strength(strong_password)
            
            if weak_fail and strong_pass:
                self.add_result('密码强度验证', True, '密码验证逻辑正确')
            else:
                self.add_result(
                    '密码强度验证',
                    False,
                    f'验证逻辑错误 - 弱密码: {not weak_fail}, 强密码: {strong_pass}'
                )
                
        except Exception as e:
            self.add_result('密码强度验证', False, f'测试失败: {str(e)}')
    
    def test_exception_handling(self):
        """测试异常处理机制"""
        try:
            from app.utils.exceptions import ValidationError, NotFoundError
            
            # 测试异常创建
            try:
                raise ValidationError('测试验证错误')
            except ValidationError as e:
                error_dict = e.to_dict()
                if error_dict.get('success') == False and error_dict.get('message'):
                    self.add_result('异常处理机制', True, '异常处理正常')
                else:
                    self.add_result('异常处理机制', False, '异常格式错误')
                    
        except Exception as e:
            self.add_result('异常处理机制', False, f'测试失败: {str(e)}')
    
    def test_structured_logging(self):
        """测试结构化日志"""
        try:
            from app.utils.enhanced_monitor import get_structured_logger
            import logging
            import io
            
            # 创建字符串IO捕获日志
            log_stream = io.StringIO()
            handler = logging.StreamHandler(log_stream)
            
            logger = get_structured_logger('test_logger')
            logger.logger.addHandler(handler)
            logger.logger.setLevel(logging.INFO)
            
            # 记录测试日志
            logger.info('测试消息', extra_field='test_value')
            
            # 获取日志内容
            log_content = log_stream.getvalue()
            
            # 验证是否为JSON格式
            try:
                log_data = json.loads(log_content.strip())
                if log_data.get('message') == '测试消息':
                    self.add_result('结构化日志', True, '日志格式正确')
                else:
                    self.add_result('结构化日志', False, '日志内容错误')
            except json.JSONDecodeError:
                self.add_result('结构化日志', False, '日志不是JSON格式')
                
        except Exception as e:
            self.add_result('结构化日志', False, f'测试失败: {str(e)}')
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始系统优化功能测试")
        print("=" * 60)
        print()
        
        # 运行测试
        self.test_health_check()
        self.test_system_metrics()
        self.test_alerts_api()
        self.test_cache_functionality()
        self.test_bloom_filter()
        self.test_password_validation()
        self.test_exception_handling()
        self.test_structured_logging()
        
        # 统计结果
        print()
        print("=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r['success'])
        failed = total - passed
        
        print(f"总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"通过率: {passed/total*100:.1f}%")
        print()
        
        # 显示失败详情
        if failed > 0:
            print("失败的测试:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test_name']}: {result['message']}")
                    if result['details']:
                        print(f"    {result['details']}")
        
        return self.test_results


def main():
    """主函数"""
    # 从命令行参数获取服务器地址
    base_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5000'
    
    print(f"测试服务器: {base_url}")
    print()
    
    tester = OptimizationTester(base_url)
    results = tester.run_all_tests()
    
    # 返回退出码
    failed_count = sum(1 for r in results if not r['success'])
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == '__main__':
    main()
