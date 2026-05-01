import scrapy
from scrapy.http import Request
from urllib.parse import urljoin
import datetime
from bidding_spider.items import BiddingItem
import re
import logging
from scrapy.exceptions import CloseSpider
from twisted.internet.error import TimeoutError, TCPTimedOutError, DNSLookupError
import time
from pathlib import Path

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class JiningGetSpider(scrapy.Spider):
    name = 'jining_get'
    allowed_domains = ['jnsggzy.cn']

    # 爬虫配置常量
    MAX_TIMEOUT_ERRORS = 100  # 最大超时错误次数
    MAX_SLOW_REQUESTS = 50 # 最大慢请求次数
    DEFAULT_TIMEOUT = 60  # 默认超时时间(秒)
    MAX_RETRIES = 5  # 最大重试次数
    SLOW_REQUEST_THRESHOLD = 10000  # 慢请求阈值(毫秒)

    # 基于实际HTML结构的CSS选择器配置
    SELECTORS = {
        'list_item': 'li.list-group-item',
        'title': 'a::text',
        'detail_url': 'a::attr(href)',
        'date': 'span.time::text',
        'next_page': 'li.PagedList-skipToNext a::attr(href)',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 初始化统计信息
        self.timeout_errors = 0
        self.slow_requests = 0
        self.dns_errors = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.items_crawled = 0  # 爬取的项目数量

        # 设置专门的日志记录器
        self.timeout_logger = logging.getLogger('timeout')
        self.stats_logger = logging.getLogger('stats')

        # 记录爬虫开始时间
        self.start_time = time.time()

        # 超时URL记录（用于去重）
        self.timeout_urls = set()

        # 初始化监控数据库
        self.monitor = None
        self.monitor_run_id = None
        if get_monitor:
            try:
                self.monitor = get_monitor(spider_name=self.name)
                self.logger.info(f"[Monitor] 监控数据库模块已加载")
            except Exception as e:
                self.logger.warning(f"[Monitor] 监控数据库初始化失败: {e}")

        self.logger.info(f"""
        🚀 爬虫 {self.name} 初始化完成
        =================================
        配置参数:
        - 超时时间: {self.DEFAULT_TIMEOUT}秒
        - 最大重试次数: {self.MAX_RETRIES}
        - 慢请求阈值: {self.SLOW_REQUEST_THRESHOLD}毫秒
        - 最大超时错误数: {self.MAX_TIMEOUT_ERRORS}
        - 最大慢请求数: {self.MAX_SLOW_REQUESTS}
        =================================
        """)

    def start_requests(self):
        """生成所有GET请求的起始URL"""
        # 记录爬虫运行开始
        if self.monitor:
            try:
                # 构建日志文件路径（使用绝对路径）
                from bidding_spider.settings import LOG_DIR
                current_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                log_file = str(LOG_DIR / f'bidding_spider_{self.name}_{current_time}.log')
                stats_file = str(LOG_DIR / f'spider_stats_{self.name}_{current_time}.json')
                
                self.monitor_run_id = self.monitor.start_run(self.name, log_file, stats_file)
                self.logger.info(f"[Monitor] 运行记录ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行开始失败: {e}")
        
        # JSON接口URL列表（新的接口格式）
        url_configs = [
            # 济宁市
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/536/newest.json', 'region': '济宁市',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/503000/newest.json', 'region': '济宁市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/551001/newest.json', 'region': '济宁市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/551003/newest.json', 'region': '济宁市',
             'category': '济宁市其他交易'},

            # 汶上县
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/536/newest.json', 'region': '汶上县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/503000/newest.json', 'region': '汶上县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/551001/newest.json', 'region': '汶上县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/551003/newest.json', 'region': '汶上县',
             'category': '汶上县其他交易'},

            # 泗水县
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/536/newest.json', 'region': '泗水县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/503000/newest.json', 'region': '泗水县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/551001/newest.json', 'region': '泗水县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/551003/newest.json', 'region': '泗水县',
             'category': '泗水县其他交易'},

            # 高新区
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/536/newest.json', 'region': '高新区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/503000/newest.json', 'region': '高新区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/551001/newest.json', 'region': '高新区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/551003/newest.json', 'region': '高新区',
             'category': '高新区其他交易'},

            # 太白湖新区
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/536/newest.json', 'region': '太白湖新区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/503000/newest.json', 'region': '太白湖新区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/551001/newest.json', 'region': '太白湖新区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/551003/newest.json', 'region': '太白湖新区',
             'category': '太白湖新区其他交易'},

            # 梁山县
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/536/newest.json', 'region': '梁山县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/503000/newest.json', 'region': '梁山县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/551001/newest.json', 'region': '梁山县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/551003/newest.json', 'region': '梁山县',
             'category': '梁山县其他交易'},

            # 任城区
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/536/newest.json', 'region': '任城区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/503000/newest.json', 'region': '任城区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/551001/newest.json', 'region': '任城区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/551003/newest.json', 'region': '任城区',
             'category': '任城区其他交易'},

            # 经开区
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/536/newest.json', 'region': '经开区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/503000/newest.json', 'region': '经开区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/551001/newest.json', 'region': '经开区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/551003/newest.json', 'region': '经开区',
             'category': '经开区其他交易'},

            # 邹城市
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/536/newest.json', 'region': '邹城市',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/503000/newest.json', 'region': '邹城市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/551001/newest.json', 'region': '邹城市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/551003/newest.json', 'region': '邹城市',
             'category': '邹城市其他交易'},

            # 曲阜市
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/536/newest.json', 'region': '曲阜市',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/503000/newest.json', 'region': '曲阜市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/551001/newest.json', 'region': '曲阜市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/551003/newest.json', 'region': '曲阜市',
             'category': '曲阜市其他交易'},

            # 兖州区
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/536/newest.json', 'region': '兖州区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/503000/newest.json', 'region': '兖州区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/551001/newest.json', 'region': '兖州区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/551003/newest.json', 'region': '兖州区',
             'category': '兖州区其他交易'},

            # 嘉祥县
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/536/newest.json', 'region': '嘉祥县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/503000/newest.json', 'region': '嘉祥县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/551001/newest.json', 'region': '嘉祥县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/551003/newest.json', 'region': '嘉祥县',
             'category': '嘉祥县其他交易'},

            # 金乡县
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/536/newest.json', 'region': '金乡县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/503000/newest.json', 'region': '金乡县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/551001/newest.json', 'region': '金乡县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/551003/newest.json', 'region': '金乡县',
             'category': '金乡县其他交易'},

            # 鱼台县
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/536/newest.json', 'region': '鱼台县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/503000/newest.json', 'region': '鱼台县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/551001/newest.json', 'region': '鱼台县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/551003/newest.json', 'region': '鱼台县',
             'category': '鱼台县其他交易'},

            # 微山县
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/536/newest.json', 'region': '微山县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/503000/newest.json', 'region': '微山县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/551001/newest.json', 'region': '微山县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/551003/newest.json', 'region': '微山县',
             'category': '微山县其他交易'},
        ]

        for config in url_configs:
            import time
            timestamp = int(time.time() * 1000)
            url_with_timestamp = f"{config['url']}?t={timestamp}"
            region_path = '/' + config['url'].split('/')[4]
            meta = {
                'region': config['region'],
                'category': config['category'],
                'page_num': 1,
                'region_path': region_path,
                'retry_count': 0,
                'max_retries': self.MAX_RETRIES,
                'download_timeout': self.DEFAULT_TIMEOUT,
                'start_time': time.time(),
            }

            self.total_requests += 1

            yield scrapy.Request(
                url_with_timestamp,
                callback=self.parse_json_list,
                meta=meta,
                errback=self.handle_error,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': 'https://www.jnsggzy.cn/',
                    'Origin': 'https://www.jnsggzy.cn',
                },
                dont_filter=True,
                priority=10
            )

    def parse_json_list(self, response):
        """解析JSON列表页 - 适配新的JSON接口"""
        self.successful_requests += 1

        start_time = response.meta.get('start_time', time.time())
        response_time = (time.time() - start_time) * 1000

        if response_time > self.SLOW_REQUEST_THRESHOLD:
            self.slow_requests += 1
            self.logger.warning(
                f"🐌 慢请求检测 - URL: {response.url} | "
                f"耗时: {response_time:.0f}ms | "
                f"状态码: {response.status}"
            )
            self._log_slow_request(response.url, response_time, response.status)

            if self.slow_requests > self.MAX_SLOW_REQUESTS:
                self.logger.warning(f"慢请求已达{self.slow_requests}次")

        self.logger.info(f"📄 开始解析JSON列表页 [{response_time:.0f}ms]: {response.url}")

        try:
            json_data = response.json()
        except Exception as e:
            self.logger.error(f"❌ JSON解析失败: {e}, URL: {response.url}")
            if get_monitor and self.monitor:
                self.monitor.log_interface_warning(
                    self.name, response.url, 'json_error',
                    response_status=response.status,
                    error_message=f"JSON解析失败: {e}"
                )
            return

        items = json_data.get('data', [])
        if not items:
            self.logger.warning(f"⚠️ 未找到列表项: {response.url}")
            if get_monitor and self.monitor:
                self.monitor.log_interface_warning(
                    self.name, response.url, 'empty_response',
                    response_status=response.status,
                    item_count=0
                )
            return

        self.logger.info(f"✅ 找到 {len(items)} 个列表项")

        today_date = datetime.date.today()
        three_days_ago = today_date - datetime.timedelta(days=2)

        self.logger.info(f"📅 抓取日期范围: {three_days_ago} 到 {today_date}")

        found_recent_data = False
        last_item_date = None

        for index, item in enumerate(items):
            try:
                publish_date = item.get('date', '').strip()
                if not publish_date:
                    continue

                if index == len(items) - 1:
                    last_item_date = publish_date
                    self.logger.debug(f"📅 当前页最后一个项目日期: {last_item_date}")

                try:
                    pub_date = datetime.datetime.strptime(publish_date, '%Y-%m-%d').date()

                    if three_days_ago <= pub_date <= today_date:
                        found_recent_data = True

                        bidding_item = BiddingItem()
                        bidding_item['publish_date'] = publish_date
                        bidding_item['project_source'] = response.meta['region']
                        bidding_item['project_category'] = response.meta['category']

                        title_text = item.get('title', '').strip()
                        bidding_item['project_name'] = title_text

                        item_url = item.get('url', '')
                        if item_url:
                            region_path = response.meta.get('region_path', '')
                            detail_url = f"https://www.jnsggzy.cn{region_path}/Posts/Detail?id={item_url}"
                            bidding_item['detail_url'] = detail_url
                        else:
                            bidding_item['detail_url'] = ''

                        bidding_item['data_source'] = self.name
                        bidding_item['page_num'] = response.meta['page_num']
                        bidding_item['item_index'] = index + 1
                        bidding_item['crawl_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        yield bidding_item
                        self.items_crawled += 1

                        if self.monitor and self.monitor_run_id:
                            try:
                                self.monitor.log_item(
                                    spider_name=self.name,
                                    spider_run_id=self.monitor_run_id,
                                    item=bidding_item
                                )
                            except Exception as e:
                                self.logger.warning(f"[Monitor] 记录条目失败: {e}")

                except Exception as e:
                    self.logger.warning(f"📅 日期处理失败: {publish_date}, 错误: {e}")

            except Exception as e:
                self.logger.error(f"❌ 解析列表项时出错: {e}")

        should_continue = False
        if last_item_date:
            try:
                last_date = datetime.datetime.strptime(last_item_date, '%Y-%m-%d').date()
                if three_days_ago <= last_date <= today_date:
                    should_continue = True
                    self.logger.info(f"📄 最后一页日期 {last_item_date} 在最近3天内，继续翻页")
                else:
                    self.logger.info(f"🛑 最后一页日期 {last_item_date} 不在最近3天内，停止翻页")
            except:
                self.logger.warning(f"⚠️ 无法解析最后一页日期: {last_item_date}")

        # 如果当前页有最近3天的数据，并且最后一页日期也在最近3天内，才继续翻页
        if found_recent_data and should_continue:
            next_page = response.css(self.SELECTORS['next_page']).get()
            if next_page:
                next_page_url = urljoin(response.url, next_page)
                meta = response.meta.copy()
                meta['page_num'] += 1
                meta['start_time'] = time.time()  # 重置开始时间
                meta['retry_count'] = 0  # 重置重试计数

                # 控制最大翻页数
                max_pages = getattr(self, 'max_pages', 10)
                if meta['page_num'] <= max_pages:
                    self.logger.info(f"⏭️ 继续翻页到第 {meta['page_num']} 页")

                    # 更新请求计数
                    self.total_requests += 1

                    yield Request(
                        next_page_url,
                        callback=self.parse_json_list,
                        meta=meta,
                        errback=self.handle_error,
                        priority=5  # 翻页请求优先级较低
                    )
                else:
                    self.logger.info(f"🛑 已达到最大翻页数 {max_pages}")
            else:
                self.logger.info(f"🛑 没有找到下一页链接")
        else:
            if not found_recent_data:
                self.logger.info(f"🛑 当前页没有最近3天的数据，停止翻页")
            elif not should_continue:
                self.logger.info(f"🛑 最后一页日期不在最近3天内，停止翻页")

    def parse_date(self, date_text):
        """解析日期"""
        try:
            # 移除可能的空格和特殊字符
            date_text = date_text.strip()
            return datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y-%m-%d')
        except Exception as e:
            self.logger.warning(f"📅 日期解析失败: {date_text}, 错误: {e}")
            return ''

    def handle_error(self, failure):
        """处理请求错误"""
        request = failure.request
        url = request.url
        retry_count = request.meta.get('retry_count', 0)
        max_retries = request.meta.get('max_retries', self.MAX_RETRIES)

        # 计算请求耗时
        start_time = request.meta.get('start_time', time.time())
        request_time = (time.time() - start_time) * 1000

        # 处理超时错误
        if failure.check(TimeoutError, TCPTimedOutError):
            self.timeout_errors += 1
            self.timeout_urls.add(url)  # 记录超时的URL

            error_msg = (
                f"⏰ 超时错误 #{self.timeout_errors} | "
                f"URL: {url} | "
                f"耗时: {request_time:.0f}ms | "
                f"超时设置: {request.meta.get('download_timeout', self.DEFAULT_TIMEOUT)}s | "
                f"重试: {retry_count}/{max_retries} | "
                f"错误: {failure.value}"
            )

            # 记录到超时日志
            self.timeout_logger.error(error_msg)
            self.logger.error(f"❌ {error_msg}")
            
            # 记录到监控数据库
            if self.monitor:
                try:
                    timeout_seconds = request.meta.get('download_timeout', self.DEFAULT_TIMEOUT)
                    error_message = str(failure.value)[:500]  # 限制长度
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

            # 检查是否超过最大错误限制
            if self.timeout_errors >= self.MAX_TIMEOUT_ERRORS:
                raise CloseSpider(
                    f"🚨 超时错误过多 ({self.timeout_errors}次)，停止爬虫以保护系统"
                )

            # 如果有重试机会，返回重试请求
            if retry_count < max_retries:
                self.logger.info(
                    f"🔄 准备重试请求 ({retry_count + 1}/{max_retries}): {url}"
                )

                # 创建新的请求，增加超时时间（指数退避）
                new_timeout = min(
                    request.meta.get('download_timeout', self.DEFAULT_TIMEOUT) * 1.5,
                    120  # 最大120秒
                )

                new_request = request.copy()
                new_request.meta['retry_count'] = retry_count + 1
                new_request.meta['download_timeout'] = new_timeout
                new_request.meta['start_time'] = time.time()
                new_request.dont_filter = True
                new_request.priority = request.priority - 1  # 降低重试优先级

                # 等待一段时间后再重试（指数退避）
                import random
                delay = (2 ** retry_count) + random.uniform(0, 1)
                self.logger.info(f"⏱️ 等待 {delay:.1f} 秒后重试")

                yield new_request

            else:
                self.logger.error(
                    f"💥 已达到最大重试次数，放弃请求: {url}"
                )

        # 处理DNS错误
        elif failure.check(DNSLookupError):
            self.dns_errors += 1

            error_msg = (
                f"🌐 DNS错误 #{self.dns_errors} | "
                f"URL: {url} | "
                f"错误: {failure.value}"
            )

            self.logger.error(f"❌ {error_msg}")

            # 如果是DNS错误，可以尝试使用备用DNS或代理
            if retry_count < max_retries:
                self.logger.warning(f"🌐 DNS错误，尝试重试: {url}")

                new_request = request.copy()
                new_request.meta['retry_count'] = retry_count + 1
                new_request.meta['start_time'] = time.time()
                new_request.dont_filter = True

                yield new_request

        # 处理其他类型的错误
        else:
            # 修复这里：直接使用 failure.type.__name__ 而不是 failure.type().__name__
            error_type = failure.type.__name__
            self.logger.error(
                f"⚠️ 其他错误 | URL: {url} | "
                f"类型: {error_type} | "
                f"错误: {failure.value}"
            )

    def _log_slow_request(self, url, response_time, status_code):
        """记录慢请求到专门的日志文件"""
        try:
            from pathlib import Path
            import os

            log_dir = Path('logs')
            if not log_dir.exists():
                log_dir.mkdir(exist_ok=True)

            slow_log_file = log_dir / 'scrapy_slow.log'

            log_entry = (
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"[SLOW] Spider: {self.name} | "
                f"URL: {url} | "
                f"耗时: {response_time:.0f}ms | "
                f"状态码: {status_code}\n"
            )

            with open(slow_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

        except Exception as e:
            self.logger.error(f"❌ 写入慢请求日志失败: {e}")

    def closed(self, reason):
        """爬虫关闭时的清理和统计"""
        # 计算总运行时间
        total_time = time.time() - self.start_time

        # 计算成功率
        success_rate = 0
        if self.total_requests > 0:
            success_rate = (self.successful_requests / self.total_requests) * 100

        # 输出详细的统计报告
        stats_summary = f"""
        📊 {'=' * 60}
        📊 爬虫运行统计报告 - {self.name}
        📊 {'=' * 60}
        📊 关闭原因: {reason}
        📊 总运行时间: {total_time:.2f}秒
        📊 总请求数: {self.total_requests}
        📊 成功请求数: {self.successful_requests}
        📊 请求成功率: {success_rate:.1f}%
        📊 超时错误数: {self.timeout_errors}
        📊 慢请求数: {self.slow_requests}
        📊 DNS错误数: {self.dns_errors}
        📊 唯一超时URL数: {len(self.timeout_urls)}
        📊 {'=' * 60}
        """

        self.logger.info(stats_summary)

        # 记录到统计日志文件
        self.stats_logger.info(
            f"爬虫 {self.name} 结束 | "
            f"原因: {reason} | "
            f"总请求: {self.total_requests} | "
            f"成功: {self.successful_requests} | "
            f"超时: {self.timeout_errors} | "
            f"慢请求: {self.slow_requests}"
        )

        # 如果错误过多，发出警告
        if self.timeout_errors > 10:
            warning_msg = (
                f"⚠️ 警告: 爬虫 {self.name} 检测到 {self.timeout_errors} 次超时错误\n"
                f"  建议检查以下事项:\n"
                f"  1. 目标网站 https://www.jnsggzy.cn 是否可访问\n"
                f"  2. 网络连接是否稳定\n"
                f"  3. 当前超时时间: {self.DEFAULT_TIMEOUT}秒是否合理\n"
                f"  4. 是否需要使用代理服务器\n"
                f"  5. 是否需要调整并发请求数"
            )
            self.logger.warning(warning_msg)

        # 保存详细的统计信息到文件
        self._save_detailed_stats(reason, total_time)
        
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
                    # items_stored 不传，让数据库保持 Pipeline 累积的值
                    error_count=self.timeout_errors + self.dns_errors,
                    warning_count=self.slow_requests,
                    timeout_count=self.timeout_errors,
                    close_reason=reason
                )
                self.logger.info(f"[Monitor] 运行记录已更新，ID: {self.monitor_run_id}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行结束失败: {e}")

    def _save_detailed_stats(self, reason, total_time):
        """保存详细统计信息到JSON文件"""
        try:
            import json
            from pathlib import Path
            import os

            log_dir = Path('logs')
            if not log_dir.exists():
                log_dir.mkdir(exist_ok=True)

            stats_file = log_dir / f'spider_stats_{self.name}_{time.strftime("%Y%m%d_%H%M%S")}.json'

            stats_data = {
                'spider_name': self.name,
                'close_reason': reason,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_time_seconds': round(total_time, 2),
                'requests': {
                    'total': self.total_requests,
                    'successful': self.successful_requests,
                    'success_rate': round(
                        (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0, 1),
                },
                'errors': {
                    'timeout': self.timeout_errors,
                    'slow_requests': self.slow_requests,
                    'dns': self.dns_errors,
                    'unique_timeout_urls': list(self.timeout_urls)[:10],  # 只保存前10个
                },
                'configuration': {
                    'max_timeout_errors': self.MAX_TIMEOUT_ERRORS,
                    'max_slow_requests': self.MAX_SLOW_REQUESTS,
                    'default_timeout': self.DEFAULT_TIMEOUT,
                    'max_retries': self.MAX_RETRIES,
                    'slow_request_threshold': self.SLOW_REQUEST_THRESHOLD,
                }
            }

            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"📝 详细统计信息已保存到: {stats_file}")

        except Exception as e:
            self.logger.error(f"❌ 保存统计信息失败: {e}")
