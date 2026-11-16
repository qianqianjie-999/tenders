"""通用安全校验函数。"""

import re


def validate_password_policy(password):
    """返回密码策略错误列表；空列表表示通过。"""
    errors = []
    value = password or ""
    if len(value) < 9:
        errors.append("密码长度至少 9 位")
    if len(value) > 256:
        errors.append("密码长度不能超过 256 位")
    if not re.search(r"[A-Za-z]", value):
        errors.append("密码必须包含字母")
    if not re.search(r"\d", value):
        errors.append("密码必须包含数字")
    return errors
