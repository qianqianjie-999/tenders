"""
认证服务模块
处理用户认证相关逻辑
"""
from flask import current_app
from werkzeug.security import generate_password_hash


class AuthService:
    """认证服务类"""

    @staticmethod
    def get_users_from_config(users_config_str=''):
        """
        从配置中加载用户字典

        用户配置格式：USERNAME1:PASSWORD_HASH1;USERNAME2:PASSWORD_HASH2
        支持多个用户，用分号分隔

        Args:
            users_config_str: 用户配置字符串，如果为空则从 current_app 获取

        Returns:
            dict: 用户名到密码哈希的映射
        """
        users = {}

        # 如果没有传入配置字符串，尝试从 current_app 获取
        if not users_config_str:
            try:
                users_config_str = current_app.config.get('USERS_CONFIG', '')
            except RuntimeError:
                # 不在应用上下文中，返回空字典
                return {}

        if not users_config_str:
            return users

        for user_entry in users_config_str.split(';'):
            if ':' in user_entry:
                username, password_hash = user_entry.split(':', 1)
                username = username.strip()
                password_hash = password_hash.strip()
                if username:
                    users[username] = password_hash

        return users

    @staticmethod
    def generate_password_hash(password):
        """
        生成密码哈希

        Args:
            password: 明文密码

        Returns:
            str: 密码哈希字符串
        """
        return generate_password_hash(password)

    @staticmethod
    def print_password_hash(password):
        """
        打印密码哈希和配置示例

        Args:
            password: 要生成哈希的密码
        """
        password_hash = generate_password_hash(password)
        print(f"\n{'='*60}")
        print(f"密码哈希生成结果")
        print(f"{'='*60}")
        print(f"明文密码：{password}")
        print(f"\n密码哈希：\n{password_hash}\n")
        print(f"配置示例（添加到 .env 文件）：")
        print(f"USERS_CONFIG=admin:{password_hash}")
        print(f"{'='*60}\n")
        return password_hash
