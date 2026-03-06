import scrapy
import json
import datetime
import time
from pathlib import Path
from bidding_spider.items import BiddingItem
from twisted.internet.error import TimeoutError, TCPTimedOutError

# 导入监控数据库模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class SdPostSpider(scrapy.Spider):
    name = 'sd_post'
    allowed_domains = ['ccgp-shandong.gov.cn']

    # API配置
    API_URL = 'http://www.ccgp-shandong.gov.cn:8087/api/website/site/getListByCode'
    DETAIL_API_URL = 'http://www.ccgp-shandong.gov.cn:8087/api/website/site/getDetail'

    def __init__(self, target_date=None, **kwargs):
        """
        初始化爬虫
        :param target_date: 指定日期，格式为 'YYYY-MM-DD'，若不指定则默认为当天
        """
        super().__init__(**kwargs)
        
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
        
        # 处理目标日期
        if target_date:
            try:
                # 验证日期格式
                datetime.datetime.strptime(target_date, '%Y-%m-%d')
                self.target_date = target_date
                self.logger.info(f"指定抓取日期: {self.target_date}")
            except ValueError:
                self.logger.error(f"日期格式错误: {target_date}，请使用 YYYY-MM-DD 格式")
                raise ValueError(f"Invalid date format: {target_date}. Expected format: YYYY-MM-DD")
        else:
            # 默认为当天
            self.target_date = datetime.datetime.now().strftime('%Y-%m-%d')
            self.logger.info(f"未指定日期，默认抓取当天: {self.target_date}")

        # 山东省地市代码映射
        self.city_codes = {
            '3701': '济南市',
            '3702': '青岛市',
            '3703': '淄博市',
            '3704': '枣庄市',
            '3705': '东营市',
            '3706': '烟台市',
            '3707': '潍坊市',
            '3708': '济宁市',
            '3709': '泰安市',
            '3710': '威海市',
            '3711': '日照市',
            '3712': '莱芜市',
            '3713': '临沂市',
            '3714': '德州市',
            '3715': '聊城市',
            '3716': '滨州市',
            '3717': '菏泽市'
        }

    def start_requests(self):
        """生成POST请求 - 抓取指定日期的数据（默认为当天）"""
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
        
        target_date = self.target_date
        
        # 开始时间和结束时间都是目标日期
        start_date = target_date
        end_date = target_date

        self.logger.info(f"开始抓取日期: {target_date} 的数据")

        # 1. 省本级需求公示
        yield self._create_request(
            col_code="2500",
            area="370000",
            config={
                'name': '山东省网需求公示-省本级',
                'category': '需求公示',
                'source': '省本级'
            },
            page=1
        )

        # 2. 省本级采购公告
        yield self._create_request(
            col_code="0301",
            area="370000",
            config={
                'name': '山东省网采购公告-省本级',
                'category': '采购公告',
                'source': '省本级'
            },
            page=1
        )

        # 3. 遍历17个地市的需求公示
        for city_code, city_name in self.city_codes.items():
            self.logger.info(f"请求地市需求公示: {city_name}({city_code})")
            yield self._create_request(
                col_code="2504",
                area=city_code,
                config={
                    'name': f'山东省网需求公示-{city_name}',
                    'category': '需求公示',
                    'source': city_name,
                    'city_code': city_code,
                    'city_name': city_name
                },
                page=1
            )

        # 4. 遍历17个地市的采购公告
        for city_code, city_name in self.city_codes.items():
            self.logger.info(f"请求地市采购公告: {city_name}({city_code})")
            yield self._create_request(
                col_code="0303",
                area=city_code,
                config={
                    'name': f'山东省网采购公告-{city_name}',
                    'category': '采购公告',
                    'source': city_name,
                    'city_code': city_code,
                    'city_name': city_name
                },
                page=1
            )

        self.logger.info(f"总共创建了 {2 + 2 * len(self.city_codes)} 个初始请求")

    def _create_request(self, col_code, area, config, page):
        """辅助方法：创建标准化的请求"""
        return scrapy.Request(
            url=self.API_URL,
            method='POST',
            body=json.dumps({
                "colCode": col_code,
                "area": area,
                "title": "",
                "projectCode": "",
                "currentPage": page,
                "pageSize": 50,
                "buyKind": "",
                "buyType": "",
                "startTime": f"{self.target_date} 00:00:00",
                "oldData": 0,
                "endTime": f"{self.target_date} 23:59:59",
                "homePage": 0,
                "mergeType": 0,
                "projectType": "",
                "unitName": "",
                "captchaUuid": "b4dab911da29139eb1937e3b867dc2ea"
            }),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            callback=self.parse_api_response,
            meta={
                'config': config,
                'page_num': page,
                'item_index': 0,
                'col_code': col_code,
                'area': area
            },
            errback=self.handle_error,
            dont_filter=True
        )

    def parse_api_response(self, response):
        """解析API响应 - 处理指定日期的数据"""
        config = response.meta['config']
        page_num = response.meta['page_num']
        item_index = response.meta['item_index']
        col_code = response.meta['col_code']
        area = response.meta['area']

        self.logger.info(f"解析API响应: {config['name']}, 第{page_num}页")

        try:
            data = json.loads(response.text)

            # 检查HTTP状态
            if response.status != 200:
                self.logger.error(f"HTTP错误: {response.status}")
                return

            # 检查业务状态码
            inner_data = data.get('data', {})
            inner_code = inner_data.get('code')

            if inner_code != 100:
                self.logger.error(f"API业务错误: {inner_data.get('message', '无错误信息')}, 错误码: {inner_code}")
                return

            # 获取数据
            records_data = inner_data.get('data', {})
            items = records_data.get('records', [])
            total_records = records_data.get('total', 0)
            current_page = records_data.get('current', 1)
            total_pages = records_data.get('pages', 0)

            self.logger.info(f"第{current_page}页: {len(items)}条数据，共{total_records}条，共{total_pages}页")

            if not items:
                self.logger.info("本页没有数据，停止翻页")
                return

            found_target_data = False
            target_count = 0

            for idx, item_data in enumerate(items):
                item_index += 1

                # 创建Item
                item = BiddingItem()

                # 提取基础信息
                item['project_name'] = item_data.get('title', '').strip()
                publish_time = item_data.get('date', '')
                item['publish_date'] = publish_time.split(' ')[0] if publish_time else ''
                item['detail_url'] = self.build_detail_url(item_data, config)
                item['project_source'] = config['source']
                item['project_category'] = config['category']

                # 设置爬虫元数据
                item['data_source'] = '山东省政府采购网'
                item['page_num'] = current_page
                item['item_index'] = item_index
                item['crawl_time'] = datetime.datetime.now()

                # 检查是否为目标日期的数据
                if item['publish_date']:
                    try:
                        pub_date = datetime.datetime.strptime(item['publish_date'], '%Y-%m-%d').date()
                        target = datetime.datetime.strptime(self.target_date, '%Y-%m-%d').date()

                        if pub_date == target:
                            found_target_data = True
                            target_count += 1
                            self.logger.info(
                                f"发现目标数据 [{item['publish_date']}]: {item['project_name'][:50]}..."
                            )
                            yield item
                            self.items_crawled += 1
                        else:
                            self.logger.debug(
                                f"跳过非目标日期数据 [{item['publish_date']}]: {item['project_name'][:30]}..."
                            )
                    except Exception as e:
                        self.logger.warning(f"日期处理失败: {item['publish_date']}, 错误: {e}")
                else:
                    self.logger.warning(f"无发布日期信息: {item['project_name'][:30]}...")

            self.logger.info(f"本页共有 {target_count} 条目标日期({self.target_date})数据")

            # 翻页逻辑
            if found_target_data and current_page < total_pages:
                self.logger.info(f"继续翻页到第{current_page + 1}页")
                yield self._create_request(
                    col_code=col_code,
                    area=area,
                    config=config,
                    page=current_page + 1
                ).replace(meta={
                    'config': config,
                    'page_num': current_page + 1,
                    'item_index': item_index,
                    'col_code': col_code,
                    'area': area
                })
            else:
                if not found_target_data:
                    self.logger.info("当前页无目标日期数据，停止翻页")
                elif current_page >= total_pages:
                    self.logger.info("已达到最后一页")

        except json.JSONDecodeError as e:
            self.logger.error(f'JSON解析失败: {e}')
            self.logger.error(f'响应内容: {response.text[:500]}')
        except Exception as e:
            self.logger.error(f'解析API响应时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())

    def build_detail_url(self, item_data, config):
        """构建详情页URL"""
        project_id = item_data.get('infoId', item_data.get('id', ''))
        
        # 根据配置确定colCode
        if "需求公示" in config['name']:
            col_code = "2504" if "省本级" not in config['name'] else "2500"
        else:
            col_code = "0303" if "省本级" not in config['name'] else "0301"

        if project_id:
            return f'http://www.ccgp-shandong.gov.cn/detail?id={project_id}&colCode={col_code}&oldData=0'
        return ''

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
                    timeout_seconds = 60  # 默认超时时间
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
        
        # 处理其他错误
        elif failure.check(scrapy.exceptions.DNSLookupError):
            self.dns_errors += 1
            self.logger.error("DNS解析失败")
        elif failure.check(scrapy.exceptions.ConnectionRefusedError):
            self.logger.error("连接被拒绝")
    
    def closed(self, reason):
        """爬虫关闭时的处理"""
        # 记录到监控数据库
        if self.monitor and self.monitor_run_id:
            try:
                # 根据关闭原因判断状态
                if reason == 'finished':
                    status = 'success'
                elif 'timeout' in reason.lower() or '错误' in reason or 'fail' in reason.lower():
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
                self.logger.info(f"[Monitor] 运行记录已更新，ID: {self.monitor_run_id}, 状态: {status}")
            except Exception as e:
                self.logger.warning(f"[Monitor] 记录运行结束失败: {e}")
