# flask_web/app/services/keyword_service.py
from app.extensions import get_db_connection
from flask import current_app


class KeywordService:
    """关键词管理服务 - 支持动态增删改查"""

    _cache = None  # 简单的内存缓存，避免频繁查询数据库
    _cache_valid = False

    @classmethod
    def get_all_keywords(cls, use_cache=True):
        """
        获取所有关键词列表
        :param use_cache: 是否使用缓存
        :return: 关键词字符串列表
        """
        if use_cache and cls._cache_valid and cls._cache is not None:
            return cls._cache.copy()

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT keyword FROM highlight_keywords 
                ORDER BY category, created_time DESC
            """)
            rows = cursor.fetchall()
            keywords = [row['keyword'] for row in rows]
            cursor.close()

            # 更新缓存
            cls._cache = keywords
            cls._cache_valid = True

            return keywords
        except Exception as e:
            print(f"[KeywordService] 获取关键词失败: {e}")
            # 数据库查询失败时，返回配置中的静态列表作为fallback
            fallback = current_app.config.get('HIGHLIGHT_KEYWORDS', [])
            print(f"[KeywordService] 使用fallback列表，共{len(fallback)}个关键词")
            return fallback

    @classmethod
    def get_keywords_with_stats(cls):
        """
        获取关键词及其统计信息（关联项目数量）
        :return: 包含关键词和统计的字典列表
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 获取所有关键词
            cursor.execute("""
                SELECT keyword, category, created_time 
                FROM highlight_keywords 
                ORDER BY category, created_time DESC
            """)
            keywords = cursor.fetchall()

            # 统计每个关键词关联的项目数（近30天）
            result = []
            for kw in keywords:
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM bidding_info 
                    WHERE project_name LIKE %s 
                    AND publish_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                """, (f'%{kw["keyword"]}%',))
                stat = cursor.fetchone()

                result.append({
                    'keyword': kw['keyword'],
                    'category': kw['category'],
                    'project_count': stat['count'] if stat else 0,
                    'created_time': kw['created_time'].strftime('%Y-%m-%d') if kw['created_time'] else ''
                })

            cursor.close()
            return result

        except Exception as e:
            print(f"[KeywordService] 获取关键词统计失败: {e}")
            return []

    @classmethod
    def add_keyword(cls, keyword, category='general'):
        """
        添加新关键词
        :param keyword: 关键词字符串
        :param category: 分类（可选，默认general）
        :return: (success: bool, message: str)
        """
        keyword = keyword.strip()
        if not keyword:
            return False, "关键词不能为空"

        if len(keyword) > 100:
            return False, "关键词长度不能超过100个字符"

        # 验证分类（可选）
        valid_categories = ['general', '交通', '智能化', '公安', '其他']
        if category not in valid_categories:
            category = 'general'

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM highlight_keywords WHERE keyword = %s",
                (keyword,)
            )
            if cursor.fetchone():
                cursor.close()
                return False, f"关键词 '{keyword}' 已存在"

            # 插入新关键词（包含分类）
            cursor.execute("""
                INSERT INTO highlight_keywords (keyword, category) 
                VALUES (%s, %s)
            """, (keyword, category))

            conn.commit()
            cursor.close()

            # 使缓存失效
            cls._cache_valid = False

            print(f"[KeywordService] 成功添加关键词: {keyword} (分类: {category})")
            return True, "添加成功"

        except Exception as e:
            print(f"[KeywordService] 添加关键词失败: {e}")
            return False, f"添加失败: {str(e)}"

    @classmethod
    def delete_keyword(cls, keyword):
        """
        删除关键词
        :param keyword: 要删除的关键词
        :return: (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM highlight_keywords WHERE keyword = %s",
                (keyword,)
            )

            if cursor.rowcount == 0:
                cursor.close()
                return False, f"关键词 '{keyword}' 不存在"

            conn.commit()
            cursor.close()

            # 使缓存失效
            cls._cache_valid = False

            # 同步更新内存配置
            if 'HIGHLIGHT_KEYWORDS' in current_app.config:
                if keyword in current_app.config['HIGHLIGHT_KEYWORDS']:
                    current_app.config['HIGHLIGHT_KEYWORDS'].remove(keyword)

            print(f"[KeywordService] 成功删除关键词: {keyword}")
            return True, "删除成功"

        except Exception as e:
            print(f"[KeywordService] 删除关键词失败: {e}")
            return False, f"删除失败: {str(e)}"

    @classmethod
    def update_keyword(cls, old_keyword, new_keyword, new_category=None):
        """
        修改关键词
        :param old_keyword: 原关键词
        :param new_keyword: 新关键词
        :param new_category: 新分类（可选，不传则保持不变）
        :return: (success: bool, message: str)
        """
        new_keyword = new_keyword.strip()
        if not new_keyword:
            return False, "新关键词不能为空"

        if len(new_keyword) > 100:
            return False, "关键词长度不能超过100个字符"

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查原关键词是否存在
            cursor.execute(
                "SELECT id FROM highlight_keywords WHERE keyword = %s",
                (old_keyword,)
            )
            if not cursor.fetchone():
                cursor.close()
                return False, f"原关键词 '{old_keyword}' 不存在"

            # 如果新旧不同，检查新关键词是否已存在
            if old_keyword != new_keyword:
                cursor.execute(
                    "SELECT id FROM highlight_keywords WHERE keyword = %s",
                    (new_keyword,)
                )
                if cursor.fetchone():
                    cursor.close()
                    return False, f"新关键词 '{new_keyword}' 已存在"

            # 执行更新
            if new_category:
                cursor.execute("""
                    UPDATE highlight_keywords 
                    SET keyword = %s, category = %s 
                    WHERE keyword = %s
                """, (new_keyword, new_category, old_keyword))
            else:
                cursor.execute("""
                    UPDATE highlight_keywords 
                    SET keyword = %s 
                    WHERE keyword = %s
                """, (new_keyword, old_keyword))

            conn.commit()
            cursor.close()

            # 使缓存失效
            cls._cache_valid = False

            # 同步更新内存配置
            if 'HIGHLIGHT_KEYWORDS' in current_app.config:
                if old_keyword in current_app.config['HIGHLIGHT_KEYWORDS']:
                    idx = current_app.config['HIGHLIGHT_KEYWORDS'].index(old_keyword)
                    current_app.config['HIGHLIGHT_KEYWORDS'][idx] = new_keyword

            print(f"[KeywordService] 成功修改关键词: {old_keyword} -> {new_keyword}")
            return True, "修改成功"

        except Exception as e:
            print(f"[KeywordService] 修改关键词失败: {e}")
            return False, f"修改失败: {str(e)}"

    @classmethod
    def get_categories(cls):
        """获取所有关键词分类"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT category 
                FROM highlight_keywords 
                WHERE category IS NOT NULL AND category != ''
                ORDER BY category
            """)
            categories = [row['category'] for row in cursor.fetchall()]
            cursor.close()
            return categories
        except Exception as e:
            print(f"[KeywordService] 获取分类失败: {e}")
            return ['general']

    @classmethod
    def clear_cache(cls):
        """清除缓存，强制下次从数据库重新加载"""
        cls._cache_valid = False
        cls._cache = None

    @classmethod
    def get_keyword_category(cls, keyword):
        """
        根据关键词内容自动判断分类
        按照 CATEGORY_RULES 规则匹配
        """
        # 从配置获取分类规则
        category_rules = current_app.config.get('CATEGORY_RULES', {})

        # 按优先级顺序匹配（更具体的规则先匹配）
        # 遍历规则，检查关键词是否属于该分类
        for category, keywords in category_rules.items():
            if category == '其他':
                continue  # 其他放最后

            # 检查关键词是否匹配该分类的关键词列表
            for rule_keyword in keywords:
                if rule_keyword in keyword or keyword in rule_keyword:
                    return category

        # 检查是否包含"交通"但不属于智能交通（更宽泛的匹配）
        if '交通' in keyword:
            return '大交通'

        # 默认返回其他
        return '其他'

    @classmethod
    def add_keyword(cls, keyword, category=None):
        """
        添加新关键词
        :param keyword: 关键词字符串
        :param category: 分类（可选，不传则自动判断）
        :return: (success: bool, message: str)
        """
        keyword = keyword.strip()
        if not keyword:
            return False, "关键词不能为空"

        if len(keyword) > 100:
            return False, "关键词长度不能超过100个字符"

        # 如果没有提供分类，自动判断
        if not category or category == 'general':
            category = cls.get_keyword_category(keyword)
            print(f"[KeywordService] 自动分类 '{keyword}' -> '{category}'")

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM highlight_keywords WHERE keyword = %s",
                (keyword,)
            )
            if cursor.fetchone():
                cursor.close()
                return False, f"关键词 '{keyword}' 已存在"

            # 插入新关键词
            cursor.execute("""
                    INSERT INTO highlight_keywords (keyword, category) 
                    VALUES (%s, %s)
                """, (keyword, category))

            conn.commit()
            cursor.close()

            # 使缓存失效
            cls._cache_valid = False

            # 同时更新内存中的配置（兼容性）
            if 'HIGHLIGHT_KEYWORDS' in current_app.config:
                if keyword not in current_app.config['HIGHLIGHT_KEYWORDS']:
                    current_app.config['HIGHLIGHT_KEYWORDS'].append(keyword)

            print(f"[KeywordService] 成功添加关键词: {keyword} (分类: {category})")
            return True, f"添加成功，分类：{category}"

        except Exception as e:
            print(f"[KeywordService] 添加关键词失败: {e}")
            return False, f"添加失败: {str(e)}"