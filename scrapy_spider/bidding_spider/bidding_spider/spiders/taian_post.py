import scrapy
import json
import datetime
import time
from pathlib import Path
from urllib.parse import urlencode
from bidding_spider.items import BiddingItem
from twisted.internet.error import TimeoutError, TCPTimedOutError, DNSLookupError

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class TaianPostSpider(scrapy.Spider):
    name = 'taian_post'
    allowed_domains = ['taggzyjy.com.cn']

    # API配置
    LIST_API_URL = 'http://www.taggzyjy.com.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew'
    DETAIL_BASE_URL = 'http://www.taggzyjy.com.cn/projectInfo.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 初始化统计信息
        self.timeout_errors = 0
        self.slow_requests = 0
        self.dns_errors = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.items_crawled = 0
        
        # 初始化监控数据库
        self.monitor = None
        self.monitor_run_id = None
        if get_monitor:
            try:
                self.monitor = get_monitor(spider_name=self.name)
                self.logger.info(f"[Monitor] 监控数据库模块已加载")
            except Exception as e:
                self.logger.warning(f"[Monitor] 监控数据库初始化失败: {e}")

    def start_requests(self):
        """生成POST请求 - 只抓取系统当天的数据"""
        # 记录爬虫运行开始
        if self.monitor:
            try:
                log_dir = Path('logs')
                log_dir.mkdir(exist_ok=True)
                log_file = str(log_dir / f'bidding_spider_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.log')
                stats_file = str(log_dir / f'spider_stats_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.json')
                
                self.monitor_run_id = self.monitor.start_run(self.name, log_file, stats_file)
                self.logger.info(f"[Monitor] 运行记录ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行开始失败: {e}")
        
        today_date = datetime.datetime.now().strftime('%Y-%m-%d')

        # 开始时间和结束时间都是今天
        start_date = today_date + " 00:00:00"
        end_date = today_date + " 23:59:59"

        self.logger.info(f"抓取泰安公共资源当天数据: {today_date}")

        configs = [
            # 1. 建设工程招标计划
            {
                'name': '建设工程招标计划',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002007007",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '建设工程招标计划',
                'source': '泰安市'
            },
            # 2. 建设工程招标公告
            {
                'name': '建设工程招标公告',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002007001",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '建设工程招标公告',
                'source': '泰安市'
            },
            # 3. 政府采购需求公开
            {
                'name': '政府采购需求公开',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002008006",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '需求公示',
                'source': '泰安市'
            },
            # 4. 政府采购公告
            {
                'name': '政府采购公告',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002008001",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '采购公告',
                'source': '泰安市'
            },
            # 5. 社会类工程类招标公告
            {
                'name': '社会类工程类招标公告',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002015001002",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '泰安社会类工程',
                'source': '泰安市'
            },
            # 6. 社会类采购类需求公示
            {
                'name': '社会类采购类需求公示',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002015002001",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '泰安社会类采购需求',
                'source': '泰安市'
            },
            # 7. 社会类采购类采购公告
            {
                'name': '社会类采购类采购公告',
                'payload': {
                    "token": "",
                    "pn": 0,
                    "rn": 50,
                    "sdt": "",
                    "edt": "",
                    "wd": " ",
                    "inc_wd": "",
                    "exc_wd": "",
                    "fields": "title",
                    "cnum": "001",
                    "sort": "{\"webdate\":0}",
                    "ssort": "title",
                    "cl": 200,
                    "terminal": "",
                    "condition": [{
                        "fieldName": "categorynum",
                        "equal": "002015002002",
                        "notEqual": None,
                        "equalList": None,
                        "notEqualList": None,
                        "isLike": True,
                        "likeType": 2
                    }],
                    "time": [{
                        "fieldName": "webdate",
                        "startTime": start_date,
                        "endTime": end_date
                    }],
                    "highlights": "title",
                    "statistics": None,
                    "unionCondition": None,
                    "accuracy": "",
                    "noParticiple": "0",
                    "searchRange": None,
                    "isBusiness": "1"
                },
                'category': '泰安社会类采购公告',
                'source': '泰安市'
            }
        ]

        self.logger.info(f"共有 {len(configs)} 个配置项")

        for i, config in enumerate(configs):
            self.logger.info(f"处理配置 {i + 1}: {config['name']}")
            yield scrapy.Request(
                url=self.LIST_API_URL,
                method='POST',
                body=json.dumps(config['payload']),
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                callback=self.parse_api_response,
                meta={
                    'config': config,
                    'today_date': today_date,
                    'page_num': 0,
                    'item_index': 0
                },
                errback=self.handle_error,
                dont_filter=True
            )

    def parse_api_response(self, response):
        """解析API响应 - 只处理当天的数据"""
        self.logger.info(f"解析API响应，URL: {response.url}")

        today_date = response.meta['today_date']
        page_num = response.meta['page_num']
        item_index = response.meta['item_index']

        try:
            data = json.loads(response.text)

            # 检查外层响应
            if response.status != 200:
                self.logger.error(f"HTTP错误: {response.status}")
                return

            # 检查result是否存在
            result_data = data.get('result', {})
            if not result_data:
                self.logger.error(f"API返回数据格式异常: {data.get('error', '未知错误')}")
                return

            # 获取实际数据
            items = result_data.get('records', [])
            total_count = int(result_data.get('totalcount', 0))
            current_pn = response.meta['config']['payload']['pn']
            rn = response.meta['config']['payload']['rn']

            self.logger.info(f"第{current_pn // rn + 1}页: {len(items)}条原始数据，共{total_count}条")

            if not items:
                self.logger.info("本页没有数据，停止翻页")
                return

            found_today_data = False
            today_count = 0

            for idx, item_data in enumerate(items):
                item_index += 1

                # 提取基础信息
                publish_time = item_data.get('webdate', '')
                publish_date = publish_time.split(' ')[0] if publish_time else ''

                # 检查是否为当天的数据
                if publish_date:
                    try:
                        pub_date = datetime.datetime.strptime(publish_date, '%Y-%m-%d').date()
                        today = datetime.datetime.strptime(today_date, '%Y-%m-%d').date()

                        # 判断是否为当天数据
                        if pub_date == today:
                            found_today_data = True
                            today_count += 1

                            # 创建Item
                            item = BiddingItem()

                            # 提取基础信息
                            item['project_name'] = item_data.get('title', item_data.get('titlenew', '')).strip()
                            item['publish_date'] = publish_date

                            # 构建详情链接 - 根据提供的格式构造
                            info_id = item_data.get('id', '')
                            # 处理id，去掉"_001"后缀
                            if info_id and '_' in info_id:
                                info_id = info_id.split('_')[0]

                            category_num = item_data.get('categorynum', '')
                            relation_guid = item_data.get('relationguid', '')

                            # 构造详情页URL
                            if info_id and category_num and relation_guid:
                                detail_params = {
                                    'infoid': info_id,
                                    'categorynum': category_num,
                                    'relationguid': relation_guid
                                }
                                item['detail_url'] = f"{self.DETAIL_BASE_URL}?{urlencode(detail_params)}"
                            else:
                                # 如果没有完整参数，使用linkurl字段
                                linkurl = item_data.get('linkurl', '')
                                if linkurl and not linkurl.startswith('http'):
                                    item['detail_url'] = f"http://www.taggzyjy.com.cn{linkurl}"
                                else:
                                    item['detail_url'] = linkurl or ''

                            item['project_source'] = response.meta['config']['source']
                            item['project_category'] = response.meta['config']['category']

                            # 设置爬虫元数据
                            item['data_source'] = '泰安公共资源交易中心'
                            item['page_num'] = current_pn // rn + 1
                            item['item_index'] = item_index
                            item['crawl_time'] = datetime.datetime.now()

                            self.logger.info(
                                f"发现当天数据 [{publish_date}]: {item['project_name'][:50]}...")
                            self.logger.debug(f"详情链接: {item['detail_url']}")

                            yield item
                        else:
                            self.logger.debug(
                                f"跳过非当天数据 [{publish_date}]: {item_data.get('title', '')[:30]}...")
                    except Exception as e:
                        self.logger.warning(f"日期处理失败: {publish_date}, 错误: {e}")
                else:
                    self.logger.warning(f"无发布日期信息: {item_data.get('title', '')[:30]}...")

            self.logger.info(f"本页共有 {today_count} 条当天数据")

            # 翻页逻辑：如果当前页有当天数据，并且还有更多数据，则继续翻页
            if found_today_data and (current_pn + rn) < total_count:
                next_payload = response.meta['config']['payload'].copy()
                next_payload['pn'] = current_pn + rn

                self.logger.info(f"当前页有当天数据，继续翻页到第{next_payload['pn'] // rn + 1}页")

                yield scrapy.Request(
                    url=self.LIST_API_URL,
                    method='POST',
                    body=json.dumps(next_payload),
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    },
                    callback=self.parse_api_response,
                    meta={
                        'config': response.meta['config'],
                        'today_date': today_date,
                        'page_num': next_payload['pn'],
                        'item_index': item_index
                    },
                    errback=self.handle_error,
                    dont_filter=True
                )
            else:
                if not found_today_data:
                    self.logger.info(f"当前页没有当天数据，停止翻页")
                elif (current_pn + rn) >= total_count:
                    self.logger.info(f"已达到最后一页")

        except json.JSONDecodeError as e:
            self.logger.error(f'JSON解析失败: {e}')
            self.logger.error(f'响应内容: {response.text[:500]}')
        except Exception as e:
            self.logger.error(f'解析API响应时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())

    def handle_error(self, failure):
        """处理请求错误"""
        self.logger.error(f"请求失败: {failure.value}")
        
        request = failure.request
        url = request.url
        retry_count = request.meta.get('retry_count', 0)
        
        # 处理超时错误
        if failure.check(TimeoutError, TCPTimedOutError):
            self.timeout_errors += 1
            self.logger.error(f"⏰ 超时错误 #{self.timeout_errors} | URL: {url}")
            
            # 记录到监控数据库
            if self.monitor:
                try:
                    timeout_seconds = 60
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
        elif failure.check(DNSLookupError):
            self.dns_errors += 1
            self.logger.error("DNS解析失败")
    
    def closed(self, reason):
        """爬虫关闭时的处理"""
        if self.monitor and self.monitor_run_id:
            try:
                status = 'success' if reason == 'finished' else 'failed'
                self.monitor.end_run(
                    run_id=self.monitor_run_id,
                    status=status,
                    items_crawled=self.items_crawled,
                    # items_stored 不传，让数据库保持 Pipeline 累积的值
                    error_count=self.timeout_errors + self.dns_errors,
                    warning_count=self.slow_requests,
                    timeout_count=self.timeout_errors,
                    close_reason=reason
                )
                self.logger.info(f"[Monitor] 运行记录已更新，ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行结束失败: {e}")