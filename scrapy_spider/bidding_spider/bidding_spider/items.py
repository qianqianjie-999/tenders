import scrapy
from itemloaders.processors import MapCompose, TakeFirst
import re

def remove_tags(value):
    """去除HTML标签"""
    if value:
        return re.sub(r'<[^>]+>', '', value)
    return value

class BiddingItem(scrapy.Item):
    # 列表页字段
    project_name = scrapy.Field(
        input_processor=MapCompose(remove_tags, str.strip),
        output_processor=TakeFirst()
    )
    publish_date = scrapy.Field(output_processor=TakeFirst())
    detail_url = scrapy.Field(output_processor=TakeFirst())
    project_source = scrapy.Field(output_processor=TakeFirst())
    project_category = scrapy.Field(output_processor=TakeFirst())



    # 爬虫元数据
    data_source = scrapy.Field()
    page_num = scrapy.Field()
    item_index = scrapy.Field()
    crawl_time = scrapy.Field()