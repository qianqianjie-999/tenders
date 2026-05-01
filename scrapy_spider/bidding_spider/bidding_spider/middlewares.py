import logging
import time
from scrapy import signals


class RequestStatsMiddleware:
    """
    请求统计中间件
    """

    def __init__(self):
        self.logger = logging.getLogger('stats_middleware')

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def process_request(self, request, spider):
        """记录请求开始时间"""
        request.meta['start_time'] = time.time()
        return None

    def process_response(self, request, response, spider):
        """记录响应时间"""
        start_time = request.meta.get('start_time')
        if start_time:
            response_time = (time.time() - start_time) * 1000
            request.meta['response_time'] = response_time

            # 慢请求记录
            slow_threshold = getattr(spider, 'SLOW_REQUEST_THRESHOLD', 5000)
            if response_time > slow_threshold:
                spider.slow_requests = getattr(spider, 'slow_requests', 0) + 1
                spider.crawler.stats.inc_value('slow_requests')

        return response

    def spider_closed(self, spider, reason):
        """爬虫关闭时输出中间件统计"""
        self.logger.info(f"中间件统计 - 爬虫 {spider.name} 关闭原因: {reason}")