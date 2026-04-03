#!/usr/bin/env python3
"""
生成密码哈希工具

用于生成 Flask-Login 用户密码的哈希值，以便配置到 .env 文件中
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flask_web'))

from werkzeug.security import generate_password_hash


def main():
    print("=" * 60)
    print("密码哈希生成工具")
    print("=" * 60)
    print()

    # 获取用户输入
    if len(sys.argv) > 1:
        username = sys.argv[1]
        password = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        username = input("请输入用户名：")
        password = None

    if not password:
        password = input("请输入密码：")

    if not username or not password:
        print("错误：用户名和密码不能为空")
        sys.exit(1)

    # 生成密码哈希
    password_hash = generate_password_hash(password)

    print()
    print("=" * 60)
    print("生成结果")
    print("=" * 60)
    print()
    print(f"用户名：{username}")
    print(f"密码哈希：{password_hash}")
    print()
    print("配置示例（添加到 .env 文件）：")
    print("-" * 60)
    print(f"USERS_CONFIG={username}:{password_hash}")
    print("-" * 60)
    print()
    print("如有多个用户，用分号分隔：")
    print("USERS_CONFIG=user1:hash1;user2:hash2;user3:hash3")
    print()
    print("=" * 60)


if __name__ == '__main__':
    main()
