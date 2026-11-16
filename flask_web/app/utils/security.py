"""通用安全校验函数。"""


def validate_password_policy(password):
    """返回密码策略错误列表；空列表表示通过。"""
    errors = []
    value = password or ""
    if len(value) < 12:
        errors.append("密码长度至少 12 位")
    if len(value) > 256:
        errors.append("密码长度不能超过 256 位")
    return errors
