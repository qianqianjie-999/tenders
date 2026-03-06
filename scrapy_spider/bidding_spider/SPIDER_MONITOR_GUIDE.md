# 爬虫监控埋点改造指南

本文档说明如何为其他爬虫添加监控埋点功能。

## 已完成的改造

1. ✅ `monitor_db.py` - 数据库操作模块
2. ✅ `jining_get_spider.py` - 济宁爬虫已完成改造
3. ✅ `pipelines.py` - Pipeline已支持更新入库数量

## 其他爬虫改造步骤

### 第一步：导入监控模块

在爬虫文件顶部添加：

```python
from pathlib import Path
import time

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None
```

### 第二步：在 __init__ 中初始化监控

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    
    # 初始化统计信息
    self.timeout_errors = 0
    self.slow_requests = 0
    self.dns_errors = 0
    self.total_requests = 0
    self.successful_requests = 0
    self.items_crawled = 0  # 爬取的项目数量
    
    # 初始化监控数据库
    self.monitor = None
    self.monitor_run_id = None
    if get_monitor:
        try:
            self.monitor = get_monitor()
            self.logger.info(f"[Monitor] 监控数据库模块已加载")
        except Exception as e:
            self.logger.warning(f"[Monitor] 监控数据库初始化失败: {e}")
```

### 第三步：在 start_requests 中记录运行开始

```python
def start_requests(self):
    """生成起始请求"""
    # 记录爬虫运行开始
    if self.monitor:
        try:
            log_dir = Path('logs')
            log_file = str(log_dir / f'bidding_spider_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.log')
            stats_file = str(log_dir / f'spider_stats_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.json')
            
            self.monitor_run_id = self.monitor.start_run(self.name, log_file, stats_file)
            self.logger.info(f"[Monitor] 运行记录ID: {self.monitor_run_id}")
        except Exception as e:
            self.logger.warning(f"[Monitor] 记录运行开始失败: {e}")
    
    # ... 原有代码 ...
```

### 第四步：在 parse 方法中统计爬取数量

在 yield item 的地方增加计数：

```python
def parse(self, response):
    # ... 原有解析代码 ...
    
    for item_data in items:
        item = YourItem()
        # ... 填充item ...
        yield item
        self.items_crawled += 1  # 增加爬取计数
```

### 第五步：在错误处理中记录超时日志

在 `handle_error` 或 errback 方法中：

```python
def handle_error(self, failure):
    request = failure.request
    url = request.url
    retry_count = request.meta.get('retry_count', 0)
    
    if failure.check(TimeoutError, TCPTimedOutError):
        self.timeout_errors += 1
        
        # 记录到监控数据库
        if self.monitor:
            try:
                timeout_seconds = request.meta.get('download_timeout', self.DEFAULT_TIMEOUT)
                error_message = str(failure.value)[:500]
                self.monitor.log_timeout(
                    spider_name=self.name,
                    url=url,
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    error_message=error_message,
                    spider_run_id=self.monitor_run_id
                )
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录超时日志失败: {e}")
        
        # ... 原有重试逻辑 ...
```

### 第六步：在 closed 方法中记录运行结束

```python
def closed(self, reason):
    """爬虫关闭时的处理"""
    # ... 原有统计代码 ...
    
    # 记录到监控数据库
    if self.monitor and self.monitor_run_id:
        try:
            # 根据关闭原因判断状态
            if reason == 'finished':
                status = 'success'
            elif 'timeout' in reason.lower() or '错误' in reason:
                status = 'failed'
            else:
                status = 'stopped'
            
            self.monitor.end_run(
                run_id=self.monitor_run_id,
                status=status,
                items_crawled=self.items_crawled,
                items_stored=0,  # Pipeline会自动更新
                error_count=self.timeout_errors + self.dns_errors,
                warning_count=self.slow_requests,
                timeout_count=self.timeout_errors,
                close_reason=reason
            )
            self.logger.info(f"[Monitor] 运行记录已更新，ID: {self.monitor_run_id}")
        except Exception as e:
            self.logger.warning(f"[Monitor] 记录运行结束失败: {e}")
```

## 快速复制模板

以下是一个完整的改造示例，可以直接复制到爬虫中修改：

```python
import scrapy
import time
from pathlib import Path
from twisted.internet.error import TimeoutError, TCPTimedOutError, DNSLookupError

try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class YourSpider(scrapy.Spider):
    name = 'your_spider'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout_errors = 0
        self.slow_requests = 0
        self.dns_errors = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.items_crawled = 0
        
        self.monitor = None
        self.monitor_run_id = None
        if get_monitor:
            try:
                self.monitor = get_monitor()
            except Exception as e:
                self.logger.warning(f"[Monitor] 初始化失败: {e}")
    
    def start_requests(self):
        # 记录运行开始
        if self.monitor:
            try:
                log_dir = Path('logs')
                log_file = str(log_dir / f'bidding_spider_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.log')
                stats_file = str(log_dir / f'spider_stats_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.json')
                self.monitor_run_id = self.monitor.start_run(self.name, log_file, stats_file)
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行开始失败: {e}")
        
        # ... 原有代码 ...
    
    def parse(self, response):
        # ... 解析逻辑 ...
        # yield item 时增加: self.items_crawled += 1
        pass
    
    def handle_error(self, failure):
        request = failure.request
        
        if failure.check(TimeoutError, TCPTimedOutError):
            self.timeout_errors += 1
            
            if self.monitor:
                try:
                    self.monitor.log_timeout(
                        spider_name=self.name,
                        url=request.url,
                        timeout_seconds=request.meta.get('download_timeout', 60),
                        retry_count=request.meta.get('retry_count', 0),
                        error_message=str(failure.value)[:500],
                        spider_run_id=self.monitor_run_id
                    )
                except Exception as e:
                    self.logger.warning(f"[Monitor] 记录超时失败: {e}")
        
        # ... 原有错误处理 ...
    
    def closed(self, reason):
        if self.monitor and self.monitor_run_id:
            try:
                status = 'success' if reason == 'finished' else 'failed'
                self.monitor.end_run(
                    run_id=self.monitor_run_id,
                    status=status,
                    items_crawled=self.items_crawled,
                    items_stored=0,
                    error_count=self.timeout_errors,
                    warning_count=0,
                    timeout_count=self.timeout_errors,
                    close_reason=reason
                )
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行结束失败: {e}")
```

## 环境变量配置

确保爬虫运行时设置了正确的数据库环境变量：

```bash
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=bidding_user
export DB_PASSWORD=your_password
export DB_NAME=bidding_db
```

或者在爬虫启动前在代码中设置：

```python
import os
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_PASSWORD'] = 'your_password'
```

## 验证埋点是否生效

运行爬虫后，检查数据库中是否有记录：

```sql
-- 查看今日运行记录
SELECT * FROM spider_run_logs 
WHERE run_date = CURDATE() 
ORDER BY start_time DESC;

-- 查看超时日志
SELECT * FROM spider_timeout_logs 
WHERE DATE(occurred_at) = CURDATE() 
ORDER BY occurred_at DESC;

-- 查看每日统计
SELECT * FROM spider_daily_stats 
WHERE stat_date = CURDATE();
```

## 其他爬虫列表

需要改造的其他爬虫：

- [ ] `sd_post_spider.py` - 山东省政府采购
- [ ] `jinan_post.py` - 济南公共资源
- [ ] `taian_post.py` - 泰安公共资源
- [ ] `zibo_post.py` - 淄博公共资源

建议按以上步骤逐个改造。
