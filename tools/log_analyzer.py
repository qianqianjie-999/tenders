#!/usr/bin/env python3
"""
日志分析工具
用于分析结构化日志并生成报告
"""
import json
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_file=None):
        self.log_file = log_file
        self.logs = []
    
    def load_logs(self, log_file=None):
        """加载日志文件"""
        file_path = log_file or self.log_file
        
        if not file_path or not Path(file_path).exists():
            print(f"错误: 日志文件不存在 - {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        # 尝试解析JSON格式日志
                        try:
                            log_entry = json.loads(line)
                            # 处理可能的JSON数组
                            if isinstance(log_entry, list):
                                # 只添加有效的字典条目
                                for item in log_entry:
                                    if isinstance(item, dict):
                                        self.logs.append(item)
                            elif isinstance(log_entry, dict):
                                self.logs.append(log_entry)
                        except json.JSONDecodeError:
                            # 如果不是JSON，尝试解析普通日志
                            parsed = self._parse_plain_log(line)
                            if parsed and isinstance(parsed, dict):
                                self.logs.append(parsed)
            
            print(f"✓ 已加载 {len(self.logs)} 条日志")
            return True
            
        except Exception as e:
            print(f"错误: 加载日志失败 - {e}")
            return False
    
    def _parse_plain_log(self, line):
        """解析普通格式日志"""
        # 尝试匹配方括号格式的日志
        pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] \[(.*?)\] (.*)'
        match = re.match(pattern, line)
        
        if match:
            return {
                'timestamp': match.group(1),
                'level': match.group(2),
                'logger': match.group(3),
                'message': match.group(4)
            }
        
        # 尝试匹配其他常见日志格式
        pattern2 = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (\w+) - (.+)'
        match2 = re.match(pattern2, line)
        
        if match2:
            return {
                'timestamp': match2.group(1),
                'logger': match2.group(2),
                'level': match2.group(3),
                'message': match2.group(4)
            }
        
        return None
    
    def analyze_by_level(self):
        """按日志级别分析"""
        level_counter = Counter(log.get('level', 'UNKNOWN') for log in self.logs)
        
        print("\n" + "=" * 60)
        print("日志级别统计")
        print("=" * 60)
        
        for level, count in level_counter.most_common():
            print(f"{level:10s}: {count:5d} 条")
        
        return level_counter
    
    def analyze_by_logger(self):
        """按日志器分析"""
        logger_counter = Counter(log.get('logger', 'UNKNOWN') for log in self.logs)
        
        print("\n" + "=" * 60)
        print("日志器统计 (Top 10)")
        print("=" * 60)
        
        for logger, count in logger_counter.most_common(10):
            print(f"{logger:30s}: {count:5d} 条")
        
        return logger_counter
    
    def analyze_by_time(self, interval='hour'):
        """按时间分析"""
        time_counter = Counter()
        
        for log in self.logs:
            timestamp = log.get('timestamp')
            if timestamp:
                try:
                    # 解析时间戳
                    if isinstance(timestamp, str):
                        dt = datetime.fromisoformat(timestamp.replace(',', '.'))
                    else:
                        dt = timestamp
                    
                    # 按间隔分组
                    if interval == 'hour':
                        key = dt.strftime('%Y-%m-%d %H:00')
                    elif interval == 'day':
                        key = dt.strftime('%Y-%m-%d')
                    else:
                        key = dt.strftime('%Y-%m-%d %H:%M')
                    
                    time_counter[key] += 1
                except:
                    pass
        
        print("\n" + "=" * 60)
        print(f"时间分布统计 (按{interval})")
        print("=" * 60)
        
        for time_key, count in sorted(time_counter.items()):
            print(f"{time_key}: {count:5d} 条")
        
        return time_counter
    
    def find_errors(self, limit=20):
        """查找错误日志"""
        errors = [log for log in self.logs if log.get('level') in ['ERROR', 'CRITICAL']]
        
        print("\n" + "=" * 60)
        print(f"错误日志 (最近 {min(limit, len(errors))} 条)")
        print("=" * 60)
        
        for i, error in enumerate(errors[-limit:], 1):
            print(f"\n{i}. [{error.get('level')}] {error.get('timestamp', 'N/A')}")
            print(f"   Logger: {error.get('logger', 'N/A')}")
            print(f"   Message: {error.get('message', 'N/A')}")
            
            # 显示额外信息
            extra = error.get('extra')
            if extra:
                print(f"   Extra: {json.dumps(extra, ensure_ascii=False)}")
        
        return errors
    
    def find_patterns(self):
        """查找日志模式"""
        message_patterns = Counter()
        
        for log in self.logs:
            message = log.get('message', '')
            # 简化消息（去除数字、ID等变量）
            simplified = re.sub(r'\d+', 'N', message)
            simplified = re.sub(r'0x[0-9a-fA-F]+', 'ADDR', simplified)
            message_patterns[simplified] += 1
        
        print("\n" + "=" * 60)
        print("常见日志模式 (Top 10)")
        print("=" * 60)
        
        for pattern, count in message_patterns.most_common(10):
            print(f"\n[{count} 次] {pattern[:100]}")
        
        return message_patterns
    
    def search_logs(self, keyword, level=None, logger=None):
        """搜索日志"""
        results = []
        
        for log in self.logs:
            # 关键词匹配
            if keyword.lower() not in log.get('message', '').lower():
                continue
            
            # 级别过滤
            if level and log.get('level') != level:
                continue
            
            # 日志器过滤
            if logger and log.get('logger') != logger:
                continue
            
            results.append(log)
        
        print("\n" + "=" * 60)
        print(f"搜索结果 (关键词: '{keyword}')")
        print("=" * 60)
        print(f"找到 {len(results)} 条匹配日志\n")
        
        for i, log in enumerate(results[:20], 1):  # 只显示前20条
            print(f"{i}. [{log.get('level')}] {log.get('timestamp', 'N/A')}")
            print(f"   {log.get('message', 'N/A')}")
        
        if len(results) > 20:
            print(f"\n... 还有 {len(results) - 20} 条结果未显示")
        
        return results
    
    def generate_report(self, output_file='log_analysis_report.json'):
        """生成分析报告"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_logs': len(self.logs),
            'by_level': dict(Counter(log.get('level', 'UNKNOWN') for log in self.logs)),
            'by_logger': dict(Counter(log.get('logger', 'UNKNOWN') for log in self.logs).most_common(10)),
            'errors_count': len([log for log in self.logs if log.get('level') in ['ERROR', 'CRITICAL']]),
            'warnings_count': len([log for log in self.logs if log.get('level') == 'WARNING'])
        }
        
        # 保存报告
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ 分析报告已生成: {output_file}")
        return report
    
    def interactive_analysis(self):
        """交互式分析"""
        print("=" * 60)
        print("日志分析工具")
        print("=" * 60)
        
        while True:
            print("\n选项:")
            print("1. 按日志级别分析")
            print("2. 按日志器分析")
            print("3. 按时间分析")
            print("4. 查找错误日志")
            print("5. 查找日志模式")
            print("6. 搜索日志")
            print("7. 生成分析报告")
            print("8. 退出")
            print()
            
            choice = input("请选择 (1-8): ")
            
            if choice == '1':
                self.analyze_by_level()
            
            elif choice == '2':
                self.analyze_by_logger()
            
            elif choice == '3':
                interval = input("选择时间间隔 (hour/day/minute): ")
                self.analyze_by_time(interval or 'hour')
            
            elif choice == '4':
                limit = input("显示数量 (默认20): ")
                self.find_errors(int(limit) if limit else 20)
            
            elif choice == '5':
                self.find_patterns()
            
            elif choice == '6':
                keyword = input("输入搜索关键词: ")
                level = input("日志级别 (可选): ") or None
                logger = input("日志器 (可选): ") or None
                self.search_logs(keyword, level, logger)
            
            elif choice == '7':
                output = input("输出文件名 (默认: log_analysis_report.json): ")
                self.generate_report(output or 'log_analysis_report.json')
            
            elif choice == '8':
                print("\n再见!")
                break
            
            else:
                print("错误: 无效的选择")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='日志分析工具')
    parser.add_argument('log_file', help='日志文件路径')
    parser.add_argument('--level', action='store_true', help='按级别分析')
    parser.add_argument('--logger', action='store_true', help='按日志器分析')
    parser.add_argument('--errors', action='store_true', help='查找错误日志')
    parser.add_argument('--search', help='搜索关键词')
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer(args.log_file)
    
    if not analyzer.load_logs():
        return
    
    if args.level:
        analyzer.analyze_by_level()
    elif args.logger:
        analyzer.analyze_by_logger()
    elif args.errors:
        analyzer.find_errors()
    elif args.search:
        analyzer.search_logs(args.search)
    else:
        analyzer.interactive_analysis()


if __name__ == '__main__':
    main()
