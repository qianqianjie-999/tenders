import scrapy
import json
import datetime
import re
import html
import time
from pathlib import Path
from urllib.parse import quote
from bidding_spider.items import BiddingItem
from twisted.internet.error import TimeoutError, TCPTimedOutError, DNSLookupError

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class JinanPostSpider(scrapy.Spider):
    name = 'jinan_post'
    allowed_domains = ['jnggzy.jinan.gov.cn']

    # API配置
    SEARCH_API_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/search.do'
    TENDERING_LIST_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/tendering/list.do'
    SOA_LIST_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/assets/querySoaList.do'

    # 详情页基础URL
    TENDERING_DETAIL_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/tendering/info.do'
    NOTICE_DETAIL_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/showNotice.do'
    SOA_DETAIL_URL = 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/assets/soaInfo.do'

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

        self.logger.info(f"抓取济南公共资源当天数据: {today_date}")

        configs = [
            # 1. 政府采购公告
            {
                'name': '政府采购公告',
                'url': self.SEARCH_API_URL,
                'payload': {
                    'area': '',
                    'type': '1',
                    'xuanxiang': '招标公告',
                    'subheading': '',
                    'pagenum': '1'
                },
                'category': '政府采购公告',
                'source': '济南市',
                'api_type': 'search',
                'detail_type': 'notice'
            },
            # 2. 建设工程招标计划
            {
                'name': '建设工程招标计划',
                'url': self.TENDERING_LIST_URL,
                'payload': {
                    'index': '1',
                    'pageSize': '10',
                    'type': '0'
                },
                'category': '建设工程招标计划',
                'source': '济南市',
                'api_type': 'tendering',
                'detail_type': 'tendering'
            },
            # 3. 建设工程招标公告
            {
                'name': '建设工程招标公告',
                'url': self.SEARCH_API_URL,
                'payload': {
                    'area': '',
                    'type': '0',
                    'xuanxiang': '招标公告',
                    'subheading': '',
                    'pagenum': '1'
                },
                'category': '建设工程招标公告',
                'source': '济南市',
                'api_type': 'search',
                'detail_type': 'notice'
            },
            # 4. 交通工程招标计划
            {
                'name': '交通工程招标计划',
                'url': self.TENDERING_LIST_URL,
                'payload': {
                    'index': '1',
                    'pageSize': '10',
                    'type': '6'
                },
                'category': '交通工程招标计划',
                'source': '济南市',
                'api_type': 'tendering',
                'detail_type': 'tendering'
            },
            # 5. 交通工程招标公告
            {
                'name': '交通工程招标公告',
                'url': self.SEARCH_API_URL,
                'payload': {
                    'area': '',
                    'type': '6',
                    'xuanxiang': '招标公告',
                    'subheading': '',
                    'pagenum': '1'
                },
                'category': '交通工程招标公告',
                'source': '济南市',
                'api_type': 'search',
                'detail_type': 'notice'
            },
            # 6. 国有企业采购公告
            {
                'name': '国有企业采购公告',
                'url': self.SOA_LIST_URL,
                'payload': {
                    'index': '1',
                    'pageSize': '15',
                    'type': '2'
                },
                'category': '国有企业采购公告',
                'source': '济南市',
                'api_type': 'soa',
                'detail_type': 'soa'
            },
            # 7. 其他采购公告
            {
                'name': '其他采购公告',
                'url': self.SEARCH_API_URL,
                'payload': {
                    'area': '',
                    'type': '7',
                    'xuanxiang': '招标公告',
                    'subheading': '',
                    'pagenum': '1'
                },
                'category': '其他采购公告',
                'source': '济南市',
                'api_type': 'search',
                'detail_type': 'notice'
            }
        ]

        self.logger.info(f"共有 {len(configs)} 个配置项")

        for i, config in enumerate(configs):
            self.logger.info(f"处理配置 {i + 1}: {config['name']}")
            yield scrapy.FormRequest(
                url=config['url'],
                formdata=config['payload'],
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'https://jnggzy.jinan.gov.cn',
                    'Referer': 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/'
                },
                callback=self.parse_api_response,
                meta={
                    'config': config,
                    'today_date': today_date,
                    'page_num': 1,
                    'item_index': 0
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
        page_num = response.meta['page_num']

        try:
            data = json.loads(response.text)

            # 检查响应状态
            if not data.get('success', False) and data.get('code') is not None:
                self.logger.error(f"API返回错误: {data.get('message', '未知错误')}")
                return

            params = data.get('params', {})
            if not params:
                self.logger.error("API返回数据格式异常: 缺少params字段")
                return

            # 获取HTML内容和分页信息
            html_str = params.get('str', '')
            pagesum = int(params.get('pagesum', 0))

            self.logger.info(f"第{page_num}页: 共{pagesum}页数据")

            if not html_str:
                self.logger.info("本页没有数据，停止翻页")
                return

            # 解析HTML提取项目信息
            items = self.parse_html_items(html_str, config['api_type'], config['detail_type'])

            self.logger.info(f"解析到 {len(items)} 条原始数据")

            found_today_data = False
            today_count = 0

            for idx, item_data in enumerate(items):
                item_index += 1
                publish_date = item_data.get('publish_date', '')

                # 检查是否为当天的数据
                if publish_date:
                    try:
                        # 标准化日期格式
                        pub_date_str = publish_date.strip()

                        # 判断是否为当天数据
                        if pub_date_str == today_date:
                            found_today_data = True
                            today_count += 1

                            # 创建Item
                            item = BiddingItem()

                            item['project_name'] = item_data.get('title', '').strip()
                            item['publish_date'] = pub_date_str
                            item['detail_url'] = item_data.get('detail_url', '')
                            item['project_source'] = config['source']
                            item['project_category'] = config['category']
                            item['data_source'] = '济南市公共资源交易中心'
                            item['page_num'] = page_num
                            item['item_index'] = item_index
                            item['crawl_time'] = datetime.datetime.now()

                            self.logger.info(
                                f"发现当天数据 [{pub_date_str}]: {item['project_name'][:50]}...")
                            self.logger.debug(f"详情链接: {item['detail_url']}")

                            yield item
                            self.items_crawled += 1
                        else:
                            self.logger.debug(
                                f"跳过非当天数据 [{pub_date_str}]: {item_data.get('title', '')[:30]}...")
                    except Exception as e:
                        self.logger.warning(f"日期处理失败: {publish_date}, 错误: {e}")
                else:
                    self.logger.warning(f"无发布日期信息: {item_data.get('title', '')[:30]}...")

            self.logger.info(f"本页共有 {today_count} 条当天数据")

            # 翻页逻辑
            if found_today_data and page_num < pagesum:
                next_page = page_num + 1
                next_payload = config['payload'].copy()

                # 根据不同API类型设置页码参数
                if config['api_type'] == 'tendering' or config['api_type'] == 'soa':
                    next_payload['index'] = str(next_page)
                else:
                    next_payload['pagenum'] = str(next_page)

                self.logger.info(f"当前页有当天数据，继续翻页到第{next_page}页")

                yield scrapy.FormRequest(
                    url=config['url'],
                    formdata=next_payload,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'X-Requested-With': 'XMLHttpRequest',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Origin': 'https://jnggzy.jinan.gov.cn',
                        'Referer': 'https://jnggzy.jinan.gov.cn/jnggzyztb/front/'
                    },
                    callback=self.parse_api_response,
                    meta={
                        'config': config,
                        'today_date': today_date,
                        'page_num': next_page,
                        'item_index': item_index
                    },
                    errback=self.handle_error,
                    dont_filter=True
                )
            else:
                if not found_today_data:
                    self.logger.info(f"当前页没有当天数据，停止翻页")
                elif page_num >= pagesum:
                    self.logger.info(f"已达到最后一页")

        except json.JSONDecodeError as e:
            self.logger.error(f'JSON解析失败: {e}')
            self.logger.error(f'响应内容: {response.text[:500]}')
        except Exception as e:
            self.logger.error(f'解析API响应时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())

    def parse_html_items(self, html_str, api_type, detail_type):
        """
        解析HTML字符串提取项目信息

        Args:
            html_str: HTML内容
            api_type: API类型 (search/tendering/soa)
            detail_type: 详情页类型 (notice/tendering/soa)

        Returns:
            list: 项目信息列表
        """
        items = []

        if api_type == 'search':
            # 解析search.do返回的HTML
            # 格式: <li><span class="span1">[区域]</span><a href="javascript:void(0);" onclick="showview('ID',1,'招标公告')" title="...">标题</a><span class="span2">日期</span></li>

            # 提取所有列表项
            li_pattern = r'<li[^>]*>(.*?)</li>'
            li_matches = re.findall(li_pattern, html_str, re.DOTALL)

            for li_content in li_matches:
                try:
                    # 提取日期
                    date_match = re.search(r'<span class="span2">(\d{4}-\d{2}-\d{2})</span>', li_content)
                    if not date_match:
                        continue
                    publish_date = date_match.group(1)

                    # 提取onclick参数: showview('7FD8314358F90E4CFA7CA703E5B2AB8E',1,'招标公告')
                    onclick_match = re.search(r"showview\(['\"]([^'\"]+)['\"],\s*(\d+),\s*['\"]([^'\"]+)['\"]\)",
                                              li_content)
                    if not onclick_match:
                        continue

                    info_id = onclick_match.group(1)
                    # type_code = onclick_match.group(2)  # 这个type参数在showNotice.do中不需要
                    xuanxiang = onclick_match.group(3)

                    # 提取标题（从title属性，这是最完整的标题）
                    title_match = re.search(r'title=[\'"]([^\'"]+)[\'"]', li_content)
                    if title_match:
                        title = html.unescape(title_match.group(1))
                    else:
                        continue

                    # 清理标题中的HTML标签和特殊标记
                    title = re.sub(r'<[^>]+>', '', title)
                    title = title.replace('【电子全流程】', '').strip()

                    # 构建详情链接 - 修正后的格式
                    # 正确: https://jnggzy.jinan.gov.cn/jnggzyztb/front/showNotice.do?iid=7FD8314358F90E4CFA7CA703E5B2AB8E&xuanxiang=%E6%8B%9B%E6%A0%87%E5%85%AC%E5%91%8A&isnew=1
                    if detail_type == 'notice':
                        encoded_xuanxiang = quote(xuanxiang, safe='')
                        detail_url = f"{self.NOTICE_DETAIL_URL}?iid={info_id}&xuanxiang={encoded_xuanxiang}&isnew=1"
                    else:
                        # 备用格式
                        detail_url = f"{self.NOTICE_DETAIL_URL}?iid={info_id}&xuanxiang={quote(xuanxiang, safe='')}&isnew=1"

                    items.append({
                        'title': title,
                        'publish_date': publish_date,
                        'detail_url': detail_url,
                        'info_id': info_id,
                        'xuanxiang': xuanxiang
                    })

                except Exception as e:
                    self.logger.warning(f"解析列表项失败: {e}")
                    continue

        elif api_type == 'tendering':
            # 解析tendering/list.do返回的HTML (招标计划)
            # 格式: <li><span class="span1" style="..."><a href="/jnggzyztb/front/tendering/info.do?code=7918" title="...">标题</a></span><span class="span3" style="...">日期</span></li>

            pattern = r'<li[^>]*>.*?<a[^>]*href="/jnggzyztb/front/tendering/info\.do\?code=(\d+)"[^>]*title=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>.*?<span[^>]*class="span3"[^>]*>(\d{4}-\d{2}-\d{2})</span>.*?</li>'

            matches = re.findall(pattern, html_str, re.DOTALL)

            for match in matches:
                code, full_title, short_title, date = match

                # 构建详情链接
                detail_url = f"{self.TENDERING_DETAIL_URL}?code={code}"

                # 清理标题
                clean_title = html.unescape(full_title)
                clean_title = re.sub(r'<[^>]+>', '', clean_title).strip()

                items.append({
                    'title': clean_title,
                    'publish_date': date,
                    'detail_url': detail_url,
                    'code': code
                })

        elif api_type == 'soa':
            # 解析assets/querySoaList.do返回的HTML (国有企业采购)
            # 格式: <li><a style="..." href="/jnggzyztb/front/assets/soaInfo.do?pid=xxx&type=2&isnew=1&xuanxiang=1" target="_blank" title="...">标题</a><span>日期</span></li>

            pattern = r'<li[^>]*>.*?<a[^>]*href="/jnggzyztb/front/assets/soaInfo\.do\?([^"]+)"[^>]*target="_blank"[^>]*title=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>.*?<span>(\d{4}-\d{2}-\d{2})</span>.*?</li>'

            matches = re.findall(pattern, html_str, re.DOTALL)

            for match in matches:
                query_string, full_title, short_title, date = match

                # 构建完整详情链接
                detail_url = f"{self.SOA_DETAIL_URL}?{query_string}"

                # 清理标题
                clean_title = html.unescape(full_title)
                clean_title = re.sub(r'<[^>]+>', '', clean_title).strip()

                items.append({
                    'title': clean_title,
                    'publish_date': date,
                    'detail_url': detail_url
                })

        return items

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