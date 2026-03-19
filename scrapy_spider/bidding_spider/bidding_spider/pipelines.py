import datetime
import pymysql
from itemadapter import ItemAdapter
import logging
import hashlib
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 尝试导入监控模块
try:
    from bidding_spider.monitor_db import get_monitor
except ImportError:
    get_monitor = None


class MariaDBPipeline:
    def __init__(self, db_config: Dict[str, Any]):
        """
        初始化数据库管道

        Args:
            db_config: 数据库配置字典
        """
        self.db_config = db_config
        self.seen_keys = set()  # 内存中缓存的已处理组合键
        self.conn = None
        self.cursor = None
        self.monitor = None  # 监控实例
        self.monitor_run_id = None  # 当前运行记录ID

        # 不同爬虫的加载策略配置 - 更新版本
        self.spider_loading_strategies = {
            'sd_post': {
                'condition': """
                AND DATE(publish_date) = CURDATE()
                AND detail_url LIKE 'http://www.ccgp-shandong.gov.cn%'
                """,
                'description': "加载今日数据且域名符合'http://www.ccgp-shandong.gov.cn'"
            },
            'jining_get': {
                'condition': """
                AND detail_url LIKE 'https://www.jnsggzy.cn/JiNing/Posts/Detail?id=%'
                AND publish_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
                """,
                'description': "加载特定域名最近3天数据"
            },
            'taian_post': {
                'condition': """
                AND DATE(publish_date) = CURDATE()
                AND detail_url LIKE 'http://www.taggzyjy.com.cn%'
                """,
                'description': "加载今日数据且域名符合'http://www.taggzyjy.com.cn'"
            },
            'jinan_post': {
                'condition': """
                AND DATE(publish_date) = CURDATE()
                AND detail_url LIKE 'https://jnggzy.jinan.gov.cn%'
                """,
                'description': "加载今日数据且域名符合'https://jnggzy.jinan.gov.cn'"
            },
            'zibo_post': {
                'condition': """
                AND DATE(publish_date) = CURDATE()
                AND (detail_url LIKE 'http://ggzyjy.zibo.gov.cn%' OR detail_url LIKE 'https://ggzyjy.zibo.gov.cn%')
                """,
                'description': "加载今日数据且域名符合'ggzyjy.zibo.gov.cn'"
            },
            'jiangsu_post': {
                'condition': """
                AND DATE(publish_date) = CURDATE()
                AND detail_url LIKE 'http://jsggzy.jszwfw.gov.cn%'
                """,
                'description': "加载今日数据且域名符合'http://jsggzy.jszwfw.gov.cn'"
            }
        }

        # 爬虫与数据表的映射关系
        self.spider_table_mapping = {
            'jiangsu_post': 'jiangsu_bidding_info',
            'sd_post': 'bidding_info',
            'jining_get': 'bidding_info',
            'taian_post': 'bidding_info',
            'jinan_post': 'bidding_info',
            'zibo_post': 'bidding_info'
        }

    @classmethod
    def from_crawler(cls, crawler):
        """
        从crawler获取数据库配置

        Args:
            crawler: Scrapy爬虫实例

        Returns:
            MariaDBPipeline实例
        """
        db_config = {
            'host': crawler.settings.get('DB_HOST', 'localhost'),
            'user': crawler.settings.get('DB_USER', 'bidding_user'),
            'password': crawler.settings.get('DB_PASSWORD', ''),
            'database': crawler.settings.get('DB_NAME', 'bidding_db'),
            'charset': 'utf8mb4',
            'port': crawler.settings.get('DB_PORT', 3306),
            'autocommit': crawler.settings.get('DB_AUTOCOMMIT', False),
        }

        # 验证密码是否已设置
        if not db_config['password']:
            raise ValueError("DB_PASSWORD must be set in settings or environment variables")
        return cls(db_config)

    def generate_item_key(self, project_name: str, publish_date, project_source: str) -> str:
        """
        生成项目的唯一组合键

        Args:
            project_name: 项目名称
            publish_date: 发布日期（字符串或datetime.date对象）
            project_source: 项目来源

        Returns:
            组合键字符串
        """
        # 对关键信息进行清洗和标准化
        clean_name = project_name.strip() if project_name else ""

        # 处理publish_date，可能是字符串或datetime.date对象
        if isinstance(publish_date, datetime.date):
            clean_date = publish_date.strftime('%Y-%m-%d')
        elif isinstance(publish_date, str):
            clean_date = publish_date.strip()
        else:
            clean_date = str(publish_date).strip() if publish_date else ""

        clean_source = project_source.strip() if project_source else ""

        # 使用MD5哈希生成固定长度的键（可选，可以减少内存占用）
        # 如果项目数量不多，可以直接使用字符串组合
        key_string = f"{clean_name}||{clean_date}||{clean_source}"

        # 方法1：直接返回字符串组合键（更易调试）
        # return key_string

        # 方法2：返回MD5哈希值（节省内存）
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()

    def open_spider(self, spider):
        """
        爬虫开始时执行的初始化操作

        Args:
            spider: Scrapy爬虫实例
        """
        try:
            # 建立数据库连接
            self.conn = pymysql.connect(**self.db_config)
            self.cursor = self.conn.cursor()

            # 检查数据库表是否存在，如果不存在则创建
            self.create_table_if_not_exists()

            # 加载已存在的项目组合键到内存，传入spider参数
            self.load_existing_keys(spider)

            # 获取监控实例
            if get_monitor and hasattr(spider, 'monitor') and spider.monitor:
                self.monitor = spider.monitor
                # 注意：此时 spider.monitor_run_id 可能还是 None（因为 start_requests 还未执行）
                # 将在 process_item 中动态获取 run_id
                self.monitor_run_id = None
                logger.info(f"[Pipeline] 监控模块已连接，将在 process_item 中获取运行 ID")

            logger.info(f"数据库连接已建立: {self.db_config['database']}")
            logger.info(f"内存中加载了 {len(self.seen_keys)} 个已存在的项目键")

        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def create_table_if_not_exists(self):
        """
        创建数据库表（如果不存在）
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS bidding_info (
            id INT AUTO_INCREMENT PRIMARY KEY,
            project_name VARCHAR(500) NOT NULL,
            publish_date DATE NOT NULL,
            detail_url VARCHAR(1000),
            project_source VARCHAR(100) NOT NULL,
            project_category VARCHAR(50),
            crawl_time DATETIME NOT NULL,
            created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY idx_unique_project (project_name(200), publish_date, project_source(50)),
            INDEX idx_publish_date (publish_date),
            INDEX idx_project_source (project_source),
            INDEX idx_project_category (project_category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """

        try:
            self.cursor.execute(create_table_sql)
            self.conn.commit()
            logger.info("数据库表已确认存在")
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            self.conn.rollback()
            raise

    def load_existing_keys(self, spider=None):
        """
        从数据库加载已存在的项目组合键到内存
        根据爬虫类型进行不同的加载策略

        Args:
            spider: Scrapy爬虫实例，用于判断爬虫类型
        """
        try:
            # 构建基础查询SQL
            query_sql = """
            SELECT 
                project_name, 
                publish_date, 
                project_source,
                detail_url
            FROM bidding_info 
            WHERE project_name IS NOT NULL 
            AND publish_date IS NOT NULL 
            AND project_source IS NOT NULL
            """

            # 根据爬虫名称添加不同的过滤条件
            if spider and hasattr(spider, 'name'):
                spider_name = spider.name

                if spider_name in self.spider_loading_strategies:
                    strategy = self.spider_loading_strategies[spider_name]
                    query_sql += f" {strategy['condition']}"
                    logger.info(f"加载策略: {spider_name}爬虫 - {strategy['description']}")
                else:
                    # 默认加载策略（例如最近7天数据，避免加载过多）
                    query_sql += " AND publish_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
                    logger.info(f"加载策略: {spider_name}爬虫 - 使用默认策略（最近7天数据）")

            # 添加排序，确保查询结果一致
            query_sql += " ORDER BY publish_date DESC, project_name"

            self.cursor.execute(query_sql)
            existing_items = self.cursor.fetchall()

            # 生成组合键并添加到集合
            loaded_count = 0
            for project_name, publish_date, project_source, detail_url in existing_items:
                # 根据爬虫类型进行额外验证
                if spider and spider.name in self.spider_loading_strategies:
                    strategy = self.spider_loading_strategies[spider.name]
                    # 对特定爬虫进行域名双重验证
                    if 'sd_post' == spider.name:
                        if detail_url and 'http://www.ccgp-shandong.gov.cn' not in detail_url:
                            continue  # 跳过非指定域名的记录
                    elif 'taian_post' == spider.name:
                        if detail_url and 'http://www.taggzyjy.com.cn' not in detail_url:
                            continue  # 跳过非指定域名的记录
                    elif 'jining_get' == spider.name:
                        if detail_url and 'https://www.jnsggzy.cn' not in detail_url:
                            continue  # 跳过非指定域名的记录
                    elif 'jinan_post' == spider.name:
                        if detail_url and 'jnggzy.jinan.gov.cn' not in detail_url:
                            continue  # 跳过非指定域名的记录
                    elif 'zibo_post' == spider.name:
                        if detail_url and 'ggzyjy.zibo.gov.cn' not in detail_url:
                            continue  # 跳过非指定域名的记录

                item_key = self.generate_item_key(project_name, publish_date, project_source)
                self.seen_keys.add(item_key)
                loaded_count += 1

            logger.info(f"成功加载 {loaded_count} 个已存在的项目键到内存")

            # 记录详细统计信息
            if loaded_count > 0 and spider:
                logger.debug(f"{spider.name}爬虫内存键集合大小: {len(self.seen_keys)}")

        except Exception as e:
            logger.warning(f"加载现有项目键失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            self.seen_keys = set()

    def close_spider(self, spider):
        """
        爬虫结束时执行的清理操作

        Args:
            spider: Scrapy爬虫实例
        """
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

        # 清空内存集合
        self.seen_keys.clear()

        logger.info("数据库连接已关闭，内存已清理")

    def process_item(self, item, spider):
        """
        处理每个抓取到的项目

        Args:
            item: Scrapy Item对象
            spider: Scrapy爬虫实例

        Returns:
            处理后的Item对象
        """
        try:
            adapter = ItemAdapter(item)

            # 提取关键字段
            project_name = adapter.get('project_name', '')
            publish_date = adapter.get('publish_date', '')
            project_source = adapter.get('project_source', '')
            detail_url = adapter.get('detail_url', '')

            # 验证必要字段
            if not self.validate_required_fields(project_name, publish_date, project_source):
                logger.warning(f"必要字段缺失，跳过: {project_name[:50] if project_name else '无名项目'}...")
                return item

            # 根据爬虫类型进行域名验证
            if spider and hasattr(spider, 'name'):
                spider_name = spider.name
                if spider_name == 'sd_post':
                    if detail_url and 'http://www.ccgp-shandong.gov.cn' not in detail_url:
                        logger.info(f"sd_post爬虫跳过非指定域名: {detail_url}")
                        return item
                elif spider_name == 'taian_post':
                    if detail_url and 'http://www.taggzyjy.com.cn' not in detail_url:
                        logger.info(f"taian_post爬虫跳过非指定域名: {detail_url}")
                        return item
                elif spider_name == 'jining_get':
                    if detail_url and 'https://www.jnsggzy.cn' not in detail_url:
                        logger.info(f"jining_get爬虫跳过非指定域名: {detail_url}")
                        return item
                elif spider_name == 'jiangsu_post':
                    if detail_url and 'http://jsggzy.jszwfw.gov.cn' not in detail_url:
                        logger.info(f"jiangsu_post 爬虫跳过非指定域名：{detail_url}")
                        return item

            # 生成组合键
            item_key = self.generate_item_key(project_name, publish_date, project_source)

            # 步骤1：内存去重检查
            if item_key in self.seen_keys:
                logger.debug(f"项目已存在（内存去重）: {project_name[:50]}...")
                return item

            # 步骤2：数据库去重检查（双重验证）
            if self.check_database_duplicate(project_name, publish_date, project_source, spider):
                logger.info(f"项目已存在（数据库去重）: {project_name[:50]}...")
                self.seen_keys.add(item_key)
                return item

            # 步骤3：插入新数据
            self.insert_new_item(adapter, project_name, publish_date, project_source, detail_url, spider)
            
            # 更新监控入库数量
            # 动态获取 monitor_run_id（因为它可能在 open_spider 之后才被设置）
            if self.monitor:
                try:
                    # 优先使用 spider 的 monitor_run_id（如果已设置）
                    run_id = getattr(spider, 'monitor_run_id', None) or self.monitor.get_current_run_id()
                    if run_id:
                        self.monitor.increment_items_stored(run_id, 1)
                except Exception as e:
                    logger.debug(f"[Monitor] 更新入库数量失败：{e}")

            # 添加到内存集合
            self.seen_keys.add(item_key)

            logger.info(f"✅ 成功插入数据: {project_name[:50]}...")

        except pymysql.IntegrityError as e:
            # 数据库唯一约束冲突（虽然我们已经检查过，但并发情况下仍可能发生）
            logger.warning(
                f"数据库唯一约束冲突，项目已存在: {project_name[:50] if 'project_name' in locals() else '未知项目'}")
            self.conn.rollback()
            if 'item_key' in locals():
                self.seen_keys.add(item_key)

        except pymysql.Error as e:
            logger.error(f"数据库操作失败: {e}")
            self.conn.rollback()
            # 可以选择将错误项目记录到文件，以便后续重试
            self.log_failed_item(item, str(e))

        except Exception as e:
            logger.error(f"处理项目时发生未知错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.conn.rollback()

        return item

    def validate_required_fields(self, project_name: str, publish_date: str, project_source: str) -> bool:
        """
        验证必要字段是否完整

        Args:
            project_name: 项目名称
            publish_date: 发布日期
            project_source: 项目来源

        Returns:
            验证结果（True/False）
        """
        if not project_name or not project_name.strip():
            logger.warning("项目名称不能为空")
            return False

        if not publish_date or not str(publish_date).strip():
            logger.warning(f"发布日期不能为空: {project_name[:50]}...")
            return False

        if not project_source or not project_source.strip():
            logger.warning(f"项目来源不能为空: {project_name[:50]}...")
            return False

        # 验证日期格式
        try:
            # 如果是datetime.date对象，转换为字符串
            if isinstance(publish_date, datetime.date):
                publish_date_str = publish_date.strftime('%Y-%m-%d')
            else:
                publish_date_str = str(publish_date).strip()

            datetime.datetime.strptime(publish_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"发布日期格式不正确: {publish_date}")
            return False

        return True

    def check_database_duplicate(self, project_name: str, publish_date, project_source: str, spider=None) -> bool:
        """
        检查数据库中是否已存在相同项目

        Args:
            project_name: 项目名称
            publish_date: 发布日期（字符串或 datetime.date 对象）
            project_source: 项目来源
            spider: Scrapy 爬虫实例，用于选择目标表

        Returns:
            是否存在重复（True/False）
        """
        try:
            # 根据爬虫类型选择目标表
            table_name = 'bidding_info'
            if spider and hasattr(spider, 'name'):
                table_name = self.spider_table_mapping.get(spider.name, 'bidding_info')
            
            check_sql = f"""
            SELECT COUNT(*) FROM {table_name} 
            WHERE project_name = %s 
            AND publish_date = %s 
            AND project_source = %s
            """

            # 处理 publish_date，如果是 datetime.date 对象则转换为字符串
            if isinstance(publish_date, datetime.date):
                publish_date_str = publish_date.strftime('%Y-%m-%d')
            else:
                publish_date_str = str(publish_date).strip()

            self.cursor.execute(check_sql, (
                project_name.strip(),
                publish_date_str,
                project_source.strip()
            ))

            result = self.cursor.fetchone()
            return result and result[0] > 0

        except Exception as e:
            logger.error(f"数据库去重检查失败：{e}")
            # 发生错误时，保守起见返回 True（视为重复），避免插入重复数据
            return True

    def insert_new_item(self, adapter, project_name: str, publish_date: str, project_source: str, detail_url: str, spider=None):
        """
        插入新项目到数据库

        Args:
            adapter: ItemAdapter 对象
            project_name: 项目名称
            publish_date: 发布日期
            project_source: 项目来源
            detail_url: 详情链接
            spider: Scrapy 爬虫实例，用于选择目标表
        """
        # 根据爬虫类型选择目标表
        table_name = 'bidding_info'
        if spider and hasattr(spider, 'name'):
            table_name = self.spider_table_mapping.get(spider.name, 'bidding_info')
        
        sql = f"""
        INSERT INTO {table_name} (
            project_name, 
            publish_date, 
            detail_url, 
            project_source, 
            project_category, 
            crawl_time
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """

        values = (
            project_name[:500],  # 限制长度
            publish_date,
            detail_url[:1000] if detail_url else None,  # 限制长度
            project_source[:100],  # 限制长度
            adapter.get('project_category', '')[:50] if adapter.get('project_category') else None,
            datetime.datetime.now()
        )

        self.cursor.execute(sql, values)
        self.conn.commit()

    def log_failed_item(self, item, error_msg: str):
        """
        记录处理失败的项目到日志文件

        Args:
            item: 失败的Item对象
            error_msg: 错误信息
        """
        try:
            adapter = ItemAdapter(item)
            failed_item_info = {
                'project_name': adapter.get('project_name', ''),
                'publish_date': adapter.get('publish_date', ''),
                'project_source': adapter.get('project_source', ''),
                'detail_url': adapter.get('detail_url', ''),
                'error': error_msg,
                'timestamp': datetime.datetime.now().isoformat()
            }

            # 记录到错误日志
            logger.error(f"失败项目详情: {failed_item_info}")

        except Exception as e:
            logger.error(f"记录失败项目时出错: {e}")