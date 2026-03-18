import scrapy
import json
import datetime
import re
import time
from pathlib import Path
from bidding_spider.items import BiddingItem
from twisted.internet.error import TimeoutError, TCPTimedOutError, DNSLookupError

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class JiangsuPostSpider(scrapy.Spider):
    name = 'jiangsu_post'
    allowed_domains = ['jsggzy.jszwfw.gov.cn']

    # API 配置
    API_URL = 'http://jsggzy.jszwfw.gov.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew'

    # 详情页基础 URL
    DETAIL_BASE_URL = 'http://jsggzy.jszwfw.gov.cn'

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
                self.logger.warning(f"[Monitor] 监控数据库初始化失败：{e}")

    def start_requests(self):
        """生成 POST 请求 - 只抓取系统当天的数据"""
        # 记录爬虫运行开始
        if self.monitor:
            try:
                log_dir = Path('logs')
                log_dir.mkdir(exist_ok=True)
                log_file = str(log_dir / f'bidding_spider_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.log')
                stats_file = str(log_dir / f'spider_stats_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.json')

                self.monitor_run_id = self.monitor.start_run(self.name, log_file, stats_file)
                self.logger.info(f"[Monitor] 运行记录 ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行开始失败：{e}")

        today_date = datetime.datetime.now().strftime('%Y-%m-%d')
        today_start = f'{today_date} 00:00:00'
        today_end = f'{today_date} 23:59:59'

        self.logger.info(f"抓取江苏省公共资源当天数据：{today_date}")

        # 各类别配置
        configs = [
            # 1. 政府采购公告
            {
                'name': '政府采购公告',
                'category_num': '003004002',
                'category': '政府采购公告',
                'source': '省级',
            },
            # 2. 交通工程招标计划
            {
                'name': '交通工程招标计划',
                'category_num': '003002005',
                'category': '交通工程招标计划',
                'source': '省级',
            },
            # 3. 交通工程提前公示
            {
                'name': '交通工程提前公示',
                'category_num': '003002010',
                'category': '交通工程提前公示',
                'source': '省级',
            },
            # 4. 交通工程招标公告
            {
                'name': '交通工程招标公告',
                'category_num': '003002001',
                'category': '交通工程招标公告',
                'source': '省级',
            },
            # 5. 建设工程招标计划
            {
                'name': '建设工程招标计划',
                'category_num': '003001010',
                'category': '建设工程招标计划',
                'source': '省级',
            },
            # 6. 建设工程招标公告
            {
                'name': '建设工程招标公告',
                'category_num': '003001001',
                'category': '建设工程招标公告',
                'source': '省级',
            },
        ]

        self.logger.info(f"共有 {len(configs)} 个配置项")

        for config in configs:
            # 构建请求 Payload
            payload = {
                "token": "",
                "pn": "0",
                "rn": "20",
                "sdt": "",
                "edt": "",
                "wd": "",
                "inc_wd": "",
                "exc_wd": "",
                "fields": "title",
                "cnum": "001",
                "sort": '{"infodatepx":"0"}',
                "ssort": "title",
                "cl": "200",
                "terminal": "",
                "condition": '[{"fieldName":"categorynum","isLike":true,"likeType":2,"equal":"' + config['category_num'] + '"}]',
                "time": '[{"fieldName":"infodatepx","startTime":"' + today_start + '","endTime":"' + today_end + '"}]',
                "highlights": "title",
                "statistics": "null",
                "unionCondition": "[]",
                "accuracy": "",
                "noParticiple": "1",
                "searchRange": "null",
                "isBusiness": "1"
            }

            self.logger.info(f"处理配置：{config['name']} (categorynum: {config['category_num']})")

            # 将 payload 转为 JSON 字符串作为请求体
            body_json = json.dumps(payload, separators=(',', ':'))

            yield scrapy.Request(
                url=self.API_URL,
                method='POST',
                body=body_json,
                headers={
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'http://jsggzy.jszwfw.gov.cn',
                    'Referer': 'http://jsggzy.jszwfw.gov.cn/'
                },
                callback=self.parse_api_response,
                meta={
                    'config': config,
                    'today_date': today_date,
                    'today_start': today_start,
                    'today_end': today_end,
                    'page_num': 0,
                    'item_index': 0,
                    'payload': payload
                },
                errback=self.handle_error,
                dont_filter=True
            )

    def parse_api_response(self, response):
        """解析 API 响应 - 只处理当天的数据"""
        self.logger.info(f"解析 API 响应，URL: {response.url}")

        today_date = response.meta['today_date']
        today_start = response.meta['today_start']
        today_end = response.meta['today_end']
        config = response.meta['config']
        item_index = response.meta['item_index']
        page_num = response.meta['page_num']
        payload = response.meta['payload']

        try:
            data = json.loads(response.text)

            # 获取返回结果
            result = data.get('result', {})
            if not result:
                self.logger.warning("API 返回数据格式异常：缺少 result 字段")
                return

            # 获取总数和列表数据
            total_count = int(result.get('totalcount', 0))
            records = result.get('records', [])

            self.logger.info(f"第{page_num + 1}页：共{total_count}条数据，返回{len(records)}条")

            if not records:
                self.logger.info("本页没有数据，停止翻页")
                return

            found_today_data = False
            today_count = 0

            for record in records:
                item_index += 1
                title = record.get('title', '').strip()
                linkurl = record.get('linkurl', '')
                infodate = record.get('infodate', '')
                infodateformat = record.get('infodateformat', '')
                zhuanzai = record.get('zhuanzai', '')

                # 确定地区
                if zhuanzai and zhuanzai != '省级':
                    project_source = zhuanzai.rstrip('市')
                else:
                    project_source = '省级'

                # 构建详情页链接
                if linkurl and not linkurl.startswith('http'):
                    detail_url = self.DETAIL_BASE_URL + linkurl
                else:
                    detail_url = linkurl

                # 检查是否为当天的数据
                if infodateformat:
                    pub_date_str = infodateformat.strip()

                    # 判断是否为当天数据
                    if pub_date_str == today_date:
                        found_today_data = True
                        today_count += 1

                        # 创建 Item
                        item = BiddingItem()

                        item['project_name'] = title
                        item['publish_date'] = pub_date_str
                        item['detail_url'] = detail_url
                        item['project_source'] = project_source
                        item['project_category'] = config['category']
                        item['data_source'] = '江苏省公共资源交易中心'
                        item['page_num'] = page_num + 1
                        item['item_index'] = item_index
                        item['crawl_time'] = datetime.datetime.now()

                        self.logger.info(
                            f"发现当天数据 [{pub_date_str}]: {item['project_name'][:50]}...")
                        self.logger.debug(f"详情链接：{item['detail_url']}")

                        yield item
                        self.items_crawled += 1
                    else:
                        self.logger.debug(
                            f"跳过非当天数据 [{pub_date_str}]: {title[:30]}...")

            self.logger.info(f"本页共有 {today_count} 条当天数据")

            # 翻页逻辑：只要本页有当天数据，就一直翻页，直到不是当日的
            if found_today_data:
                next_page = page_num + 1
                next_payload = payload.copy()
                next_payload['pn'] = str(next_page * 20)  # pn 是偏移量

                self.logger.info(f"当前页有当天数据，继续翻页到第{next_page + 1}页")

                # 将 payload 转为 JSON 字符串作为请求体
                next_body_json = json.dumps(next_payload, separators=(',', ':'))

                yield scrapy.Request(
                    url=self.API_URL,
                    method='POST',
                    body=next_body_json,
                    headers={
                        'Content-Type': 'application/json; charset=UTF-8',
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Origin': 'http://jsggzy.jszwfw.gov.cn',
                        'Referer': 'http://jsggzy.jszwfw.gov.cn/'
                    },
                    callback=self.parse_api_response,
                    meta={
                        'config': config,
                        'today_date': today_date,
                        'today_start': today_start,
                        'today_end': today_end,
                        'page_num': next_page,
                        'item_index': item_index,
                        'payload': next_payload
                    },
                    errback=self.handle_error,
                    dont_filter=True
                )
            else:
                self.logger.info(f"当前页没有当天数据，停止翻页")

        except json.JSONDecodeError as e:
            self.logger.error(f'JSON 解析失败：{e}')
            self.logger.error(f'响应内容：{response.text[:500]}')
        except Exception as e:
            self.logger.error(f'解析 API 响应时出错：{e}')
            import traceback
            self.logger.error(traceback.format_exc())

    def handle_error(self, failure):
        """处理请求错误"""
        self.logger.error(f"请求失败：{failure.value}")

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
                    self.logger.warning(f"[Monitor] 记录超时日志失败：{e}")
        elif failure.check(DNSLookupError):
            self.dns_errors += 1
            self.logger.error("DNS 解析失败")

    def closed(self, reason):
        """爬虫关闭时的处理"""
        if self.monitor and self.monitor_run_id:
            try:
                status = 'success' if reason == 'finished' else 'failed'
                self.monitor.end_run(
                    run_id=self.monitor_run_id,
                    status=status,
                    items_crawled=self.items_crawled,
                    error_count=self.timeout_errors + self.dns_errors,
                    warning_count=self.slow_requests,
                    timeout_count=self.timeout_errors,
                    close_reason=reason
                )
                self.logger.info(f"[Monitor] 运行记录已更新，ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行结束失败：{e}")
