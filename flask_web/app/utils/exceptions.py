"""
自定义异常类
提供统一的异常处理机制
"""


class BaseAPIException(Exception):
    """API异常基类"""
    
    def __init__(self, message, status_code=400, payload=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload
    
    def to_dict(self):
        rv = dict(self.payload or ())
        rv['success'] = False
        rv['message'] = self.message
        return rv


class ValidationError(BaseAPIException):
    """验证错误"""
    
    def __init__(self, message='数据验证失败', payload=None):
        super().__init__(message, status_code=400, payload=payload)


class NotFoundError(BaseAPIException):
    """资源未找到"""
    
    def __init__(self, message='资源不存在', payload=None):
        super().__init__(message, status_code=404, payload=payload)


class DatabaseError(BaseAPIException):
    """数据库错误"""
    
    def __init__(self, message='数据库操作失败', payload=None):
        super().__init__(message, status_code=500, payload=payload)


class AuthenticationError(BaseAPIException):
    """认证错误"""
    
    def __init__(self, message='认证失败', payload=None):
        super().__init__(message, status_code=401, payload=payload)


class PermissionError(BaseAPIException):
    """权限错误"""
    
    def __init__(self, message='权限不足', payload=None):
        super().__init__(message, status_code=403, payload=payload)
