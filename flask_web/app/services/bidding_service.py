from flask import current_app
from app.extensions import get_db_connection
from app.utils.helpers import categorize_project, format_date_for_display
from datetime import date
from app.services.keyword_service import KeywordService


# app/services/bidding_service.py

class BiddingService:
    @staticmethod
    def get_data(date_filter_type='single', date_params=None, category='全部',
                 source='全部', keyword='', highlight_only=False, page=1, page_size=20):
        """查询招标数据（支持单日期或日期范围）"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 构建日期条件
        if date_filter_type == 'range' and len(date_params) == 2:
            start_date, end_date = date_params
            date_condition = "publish_date BETWEEN %s AND %s"
            params = [start_date, end_date]
        else:
            # 单日期模式
            query_date = date_params[0] if date_params else date.today().strftime('%Y-%m-%d')
            date_condition = "publish_date = %s"
            params = [query_date]

        conditions = [date_condition]

        if category != '全部' and category:
            conditions.append("project_category = %s")
            params.append(category)

        if source != '全部' and source:
            conditions.append("project_source = %s")
            params.append(source)

        if keyword:
            conditions.append("project_name LIKE %s")
            params.append(f'%{keyword}%')

        if highlight_only:
            keywords = KeywordService.get_all_keywords() or current_app.config.get('HIGHLIGHT_KEYWORDS', [])
            if keywords:
                highlight_conditions = []
                for kw in keywords:
                    highlight_conditions.append("project_name LIKE %s")
                    params.append(f'%{kw}%')
                conditions.append("(" + " OR ".join(highlight_conditions) + ")")

        where_clause = " AND ".join(conditions)
        offset = (page - 1) * page_size

        # 查询数据
        sql = f"""
        SELECT * FROM bidding_info 
        WHERE {where_clause}
        ORDER BY publish_date DESC, id DESC
        LIMIT %s OFFSET %s
        """
        cursor.execute(sql, params + [page_size, offset])
        rows = cursor.fetchall()

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM bidding_info WHERE {where_clause}", params)
        total = cursor.fetchone()['total']

        # 处理数据...
        processed = []
        keywords = KeywordService.get_all_keywords()
        if not keywords:
            keywords = current_app.config.get('HIGHLIGHT_KEYWORDS', [])
        category_rules = current_app.config.get('CATEGORY_RULES', {})

        for row in rows:
            is_highlighted = any(kw in row['project_name'] for kw in keywords)
            cat = row['project_category'] or categorize_project(row['project_name'], category_rules)

            processed.append({
                'id': row['id'],
                'project_name': row['project_name'],
                'publish_date': format_date_for_display(row['publish_date']),
                'detail_url': row['detail_url'],
                'project_source': row['project_source'],
                'project_category': cat,
                'crawl_time': row['crawl_time'].strftime('%Y-%m-%d %H:%M:%S') if row['crawl_time'] else '',
                'is_highlighted': is_highlighted,
                'has_keyword': is_highlighted
            })

        cursor.close()
        return processed, total

    @staticmethod
    def get_statistics_range(start_date, end_date):
        """获取日期范围内的统计数据"""
        conn = get_db_connection()
        cursor = conn.cursor()

        keywords = KeywordService.get_all_keywords()
        if not keywords:
            keywords = current_app.config.get('HIGHLIGHT_KEYWORDS', [])

        # 总数
        cursor.execute("""
            SELECT COUNT(*) as total 
            FROM bidding_info 
            WHERE publish_date BETWEEN %s AND %s
        """, (start_date, end_date))
        total = cursor.fetchone()['total']

        # 高亮数
        if keywords:
            conditions = " OR ".join(["project_name LIKE %s"] * len(keywords))
            cursor.execute(f"""
                SELECT COUNT(*) as highlight 
                FROM bidding_info 
                WHERE publish_date BETWEEN %s AND %s
                AND ({conditions})
            """, [start_date, end_date] + [f'%{kw}%' for kw in keywords])
            highlight = cursor.fetchone()['highlight']
        else:
            highlight = 0

        cursor.close()
        return {'total_count': total, 'highlight_count': highlight}

    @staticmethod
    def get_statistics(query_date):
        """获取单日统计数据 - 使用动态关键词服务"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 使用 KeywordService 动态获取关键词（支持缓存）
        keywords = KeywordService.get_all_keywords()

        # 如果数据库获取失败，fallback到静态配置
        if not keywords:
            keywords = current_app.config.get('HIGHLIGHT_KEYWORDS', [])
            print(f"[BiddingService] 使用fallback关键词列表，共{len(keywords)}个")

        # 总数
        cursor.execute("SELECT COUNT(*) as total FROM bidding_info WHERE publish_date = %s", (query_date,))
        total = cursor.fetchone()['total']

        # 高亮数（包含任一关键词的项目）
        if keywords:
            conditions = " OR ".join(["project_name LIKE %s"] * len(keywords))
            cursor.execute(f"""
                SELECT COUNT(*) as highlight FROM bidding_info 
                WHERE publish_date = %s AND ({conditions})
            """, [query_date] + [f'%{kw}%' for kw in keywords])
            highlight = cursor.fetchone()['highlight']
        else:
            highlight = 0
            print(f"[BiddingService] 警告：没有配置关键词，高亮统计为0")

        cursor.close()
        return {'total_count': total, 'highlight_count': highlight}

    @staticmethod
    def get_categories():
        """获取所有分类"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT COALESCE(project_category, '未分类') as category 
            FROM bidding_info 
            WHERE project_category IS NOT NULL AND project_category != ''
            ORDER BY category
        """)
        rows = cursor.fetchall()
        cursor.close()
        return ['全部'] + [row['category'] for row in rows]

    @staticmethod
    def get_sources():
        """获取所有来源"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT COALESCE(project_source, '未知') as source 
            FROM bidding_info 
            WHERE project_source IS NOT NULL AND project_source != ''
            ORDER BY source
        """)
        rows = cursor.fetchall()
        cursor.close()
        return ['全部'] + [row['source'] for row in rows]