from datetime import datetime, date
import re
from functools import wraps
from flask import jsonify
import traceback


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


def api_response(success=True, data=None, message='', status_code=200):
    """
    统一的API响应格式
    
    Args:
        success: 是否成功
        data: 返回的数据
        message: 消息
        status_code: HTTP状态码
        
    Returns:
        tuple: (jsonify响应, 状态码)
    """
    response = {'success': success}
    
    if data is not None:
        response['data'] = data
    
    if message:
        response['message'] = message
    
    return jsonify(response), status_code


def paginate(total, page, page_size):
    """
    计算分页信息
    
    Args:
        total: 总记录数
        page: 当前页码
        page_size: 每页大小
        
    Returns:
        dict: 分页信息
    """
    return {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': (total + page_size - 1) // page_size
    }


def handle_api_errors(f):
    """
    API错误处理装饰器
    自动捕获异常并返回统一格式的错误响应
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"API ERROR: {str(e)}")
            print(traceback.format_exc())
            return api_response(success=False, message=str(e), status_code=500)
    return decorated_function