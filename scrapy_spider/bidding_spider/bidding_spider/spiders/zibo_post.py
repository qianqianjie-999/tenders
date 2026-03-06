import scrapy
import json
import datetime
import re
import html
import time
from pathlib import Path
from urllib.parse import urljoin
from bidding_spider.items import BiddingItem
from twisted.internet.error import TimeoutError, TCPTimedOutError

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class ZiboPostSpider(scrapy.Spider):
    name = 'zibo_post'
    allowed_domains = ['ggzyjy.zibo.gov.cn']

    # API基础URL
    API_BASE_URL = 'http://ggzyjy.zibo.gov.cn:8082/EpointWebBuilder_zbggzy/rest/frontAppCustomAction/getPageInfoListNew'

    # 详情页基础URL
    DETAIL_BASE_URL = 'http://ggzyjy.zibo.gov.cn:8082/gonggongziyuan-content.html'

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

        self.logger.info(f"抓取淄博公共资源当天数据: {today_date}")

        # 各类别配置（根据您提供的数据）
        configs = [
            # 1. 建设工程计划 (categoryNum: 002001007)
            {
                'name': '建设工程计划',
                'category_num': '002001007',
                'category': '建设工程计划',
                'source': '淄博市',
                'count': 1933
            },
            # 2. 建设工程招标公告 (categoryNum: 002001001)
            {
                'name': '建设工程招标公告',
                'category_num': '002001001',
                'category': '建设工程招标公告',
                'source': '淄博市',
                'count': 6024
            },
            # 3. 政府采购公告 (categoryNum: 002002002)
            {
                'name': '政府采购公告',
                'category_num': '002002002',
                'category': '政府采购公告',
                'source': '淄博市',
                'count': 12999
            },
            # 4. 国有企业采购意向 (categoryNum: 002009001)
            {
                'name': '国有企业采购意向',
                'category_num': '002009001',
                'category': '国有企业采购意向',
                'source': '淄博市',
                'count': 525
            },
            # 5. 国有企业采购公告 (categoryNum: 002009002)
            {
                'name': '国有企业采购公告',
                'category_num': '002009002',
                'category': '国有企业采购公告',
                'source': '淄博市',
                'count': 633
            },
            # 6. 其他采购意向 (categoryNum: 002008001)
            {
                'name': '其他采购意向',
                'category_num': '002008001',
                'category': '其他采购意向',
                'source': '淄博市',
                'count': 364
            },
            # 7. 其他采购公告 (categoryNum: 002008002)
            {
                'name': '其他采购公告',
                'category_num': '002008002',
                'category': '其他采购公告',
                'source': '淄博市',
                'count': 601
            }
        ]

        self.logger.info(f"共有 {len(configs)} 个配置项")

        for config in configs:
            # 构建请求参数
            params = {
                "siteGuid": "7eb5f7f1-9041-43ad-8e13-8fcb82ea831a",
                "categoryNum": config['category_num'],
                "kw": "",
                "startDate": "",
                "endDate": "",
                "jystauts": "",
                "areacode": "",
                "pageIndex": 0,
                "pageSize": 14
            }

            # 将参数转换为JSON字符串
            params_json = json.dumps(params, separators=(',', ':'))

            self.logger.info(f"处理配置: {config['name']} (categoryNum: {config['category_num']})")

            yield scrapy.FormRequest(
                url=self.API_BASE_URL,
                formdata={'params': params_json},
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'http://ggzyjy.zibo.gov.cn:8082',
                    'Referer': 'http://ggzyjy.zibo.gov.cn:8082/'
                },
                callback=self.parse_api_response,
                meta={
                    'config': config,
                    'today_date': today_date,
                    'page_index': 0,
                    'item_index': 0,
                    'params': params
                },
                errback=self.handle_error,
                dont_filter=True
            )

    def parse_api_response(self, response):
        """解析API响应 - 只处理当天的数据"""
        self.logger.info(f"解析API响应，URL: {response.url}")

        today_date = response.meta['today_date']
        config = response.meta['config']
        item_index = response.meta['item_index']
        page_index = response.meta['page_index']
        params = response.meta['params']

        try:
            data = json.loads(response.text)

            # 检查响应状态
            status = data.get('status', {})
            if status.get('code') != 1:
                self.logger.error(f"API返回错误: {status.get('text', '未知错误')}")
                return

            custom_data = data.get('custom', {})
            if not custom_data:
                self.logger.error("API返回数据格式异常: 缺少custom字段")
                return

            # 获取总数和列表数据
            total_count = int(custom_data.get('count', 0))
            info_list = custom_data.get('infodata', [])

            self.logger.info(f"第{page_index + 1}页: 共{total_count}条数据，本页{len(info_list)}条")

            if not info_list:
                self.logger.info("本页没有数据，停止翻页")
                return

            found_today_data = False
            today_count = 0

            for idx, info in enumerate(info_list):
                item_index += 1

                # 提取发布日期
                infodate = info.get('infodate', '')
                publish_date = infodate.strip() if infodate else ''

                # 检查是否为当天的数据
                if publish_date:
                    try:
                        # 判断是否为当天数据
                        if publish_date == today_date:
                            found_today_data = True
                            today_count += 1

                            # 创建Item
                            item = BiddingItem()

                            # 提取标题（清理HTML标签）
                            real_title = info.get('realtitle', '')
                            title = self.clean_html_tags(real_title)

                            # 构建详情链接
                            infoid = info.get('infoid', '')
                            relationguid = info.get('relationguid', '')
                            categorynum = info.get('categorynum', '')

                            detail_url = f"{self.DETAIL_BASE_URL}?infoid={infoid}&relationguid={relationguid}&categorynum={categorynum}"

                            item['project_name'] = title
                            item['publish_date'] = publish_date
                            item['detail_url'] = detail_url
                            item['project_source'] = config['source']
                            item['project_category'] = config['category']
                            item['data_source'] = '淄博市公共资源交易中心'
                            item['page_num'] = page_index + 1
                            item['item_index'] = item_index
                            item['crawl_time'] = datetime.datetime.now()

                            self.logger.info(f"发现当天数据 [{publish_date}]: {item['project_name'][:50]}...")
                            self.logger.debug(f"详情链接: {item['detail_url']}")

                            yield item
                            self.items_crawled += 1
                        else:
                            self.logger.debug(f"跳过非当天数据 [{publish_date}]: {info.get('realtitle', '')[:30]}...")
                    except Exception as e:
                        self.logger.warning(f"日期处理失败: {publish_date}, 错误: {e}")
                else:
                    self.logger.warning(f"无发布日期信息: {info.get('realtitle', '')[:30]}...")

            self.logger.info(f"本页共有 {today_count} 条当天数据")

            # 翻页逻辑：如果本页有当天数据且还有下一页，则继续翻页
            if found_today_data and len(info_list) == 14:  # 每页14条，如果满页说明可能还有下一页
                next_page = page_index + 1
                next_params = params.copy()
                next_params['pageIndex'] = next_page

                next_params_json = json.dumps(next_params, separators=(',', ':'))

                self.logger.info(f"当前页有当天数据，继续翻页到第{next_page + 1}页")

                yield scrapy.FormRequest(
                    url=self.API_BASE_URL,
                    formdata={'params': next_params_json},
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'X-Requested-With': 'XMLHttpRequest',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Origin': 'http://ggzyjy.zibo.gov.cn:8082',
                        'Referer': 'http://ggzyjy.zibo.gov.cn:8082/'
                    },
                    callback=self.parse_api_response,
                    meta={
                        'config': config,
                        'today_date': today_date,
                        'page_index': next_page,
                        'item_index': item_index,
                        'params': next_params
                    },
                    errback=self.handle_error,
                    dont_filter=True
                )
            else:
                if not found_today_data:
                    self.logger.info(f"当前页没有当天数据，停止翻页")
                elif len(info_list) < 14:
                    self.logger.info(f"已到达最后一页")

        except json.JSONDecodeError as e:
            self.logger.error(f'JSON解析失败: {e}')
            self.logger.error(f'响应内容: {response.text[:500]}')
        except Exception as e:
            self.logger.error(f'解析API响应时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())

    def clean_html_tags(self, text):
        """清理HTML标签和特殊字符"""
        if not text:
            return ""

        # 解码HTML实体
        text = html.unescape(text)

        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)

        # 移除多余空白
        text = text.strip()

        return text

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
        elif failure.check(scrapy.exceptions.DNSLookupError):
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
            self.logger.error("请求超时")
        elif failure.check(scrapy.exceptions.TCPTimedOutError):
            self.logger.error("TCP连接超时")