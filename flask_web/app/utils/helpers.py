from datetime import datetime, date
import re


def format_date_for_display(date_str):
    """格式化日期显示（你原来的函数）"""
    try:
        if isinstance(date_str, date):
            return date_str.strftime('%Y-%m-%d')
        elif isinstance(date_str, str):
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        return date_str
    except:
        return date_str


def highlight_keywords(text, keywords):
    """高亮显示关键词（你原来的函数）"""
    if not text:
        return text

    sorted_keywords = sorted(keywords, key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in text:
            text = text.replace(keyword,
                                f'<span class="highlight-keyword" title="相关关键词: {keyword}">{keyword}</span>')
    return text


def categorize_project(project_name, category_rules):
    """自动分类项目"""
    if not project_name:
        return '其他'

    project_name_lower = project_name.lower()

    for category, keywords in category_rules.items():
        for keyword in keywords:
            if keyword in project_name_lower:
                return category
    return '其他'


def get_time_diff(crawl_time):
    """计算时间差"""
    if not crawl_time:
        return '未知'
    now = datetime.now()
    diff = now - crawl_time
    minutes = diff.seconds // 60
    hours = diff.seconds // 3600

    if diff.days > 0:
        return f'{diff.days}天前'
    elif hours > 0:
        return f'{hours}小时前'
    elif minutes > 0:
        return f'{minutes}分钟前'
    else:
        return '刚刚'