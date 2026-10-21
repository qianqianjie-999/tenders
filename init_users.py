#!/usr/bin/env python3
"""
初始化/迁移用户脚本（2026-10-21 新增，参考采购系统 init_users.py）

用途：
1. 在 bidding_db 中创建 users 表（IF NOT EXISTS）；
2. 读取 .env 中旧的 USERS_CONFIG（格式 用户名:密码哈希;...），将账号迁入
   users 表，角色全部为 admin（密码哈希原样搬入，用户密码不变）；
3. 若迁移后表仍为空，创建默认管理员 admin / admin123（请立即登录改密）。

用法：python3 init_users.py
"""
import os
import sys

import pymysql
from werkzeug.security import generate_password_hash

# 与 flask_web/app/config.py 相同的 .env 解析逻辑
ROOT = os.path.dirname(os.path.abspath(__file__))
for _candidate in (os.path.join(ROOT, '.env'), os.path.join(ROOT, 'flask_web', '.env')):
    if os.path.exists(_candidate):
        with open(_candidate, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)
        break

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(256) NOT NULL,
  full_name VARCHAR(100) NULL,
  email VARCHAR(120) NULL,
  department VARCHAR(100) NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'user',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def get_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'bidding_user'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'bidding_db'),
        port=int(os.environ.get('DB_PORT', 3306)),
        charset=os.environ.get('DB_CHARSET', 'utf8mb4'),
        cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    print('=' * 50)
    print('初始化/迁移用户（tenders）')
    print('=' * 50)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. 建表
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    print('[1/3] users 表已就绪')

    # 2. 迁移 USERS_CONFIG（哈希原样搬入，角色全部 admin）
    migrated = skipped = 0
    users_config = os.environ.get('USERS_CONFIG', '')
    if users_config:
        for entry in users_config.split(';'):
            if ':' not in entry:
                continue
            username, password_hash = entry.split(':', 1)
            username = username.strip()
            password_hash = password_hash.strip()
            if not username or not password_hash:
                continue
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print(f"  用户 '{username}' 已存在，跳过")
                skipped += 1
                continue
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
                (username, password_hash))
            migrated += 1
            print(f"  已迁移：{username}（admin）")
        conn.commit()
    else:
        print('[2/3] .env 中未找到 USERS_CONFIG，跳过迁移')
    if users_config:
        print(f'[2/3] 迁移完成：新增 {migrated}，跳过 {skipped}')

    # 3. 表为空则创建默认管理员
    cursor.execute("SELECT COUNT(*) AS c FROM users")
    if cursor.fetchone()['c'] == 0:
        cursor.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s, %s, %s, 'admin')",
            ('admin', generate_password_hash('admin123'), '系统管理员'))
        conn.commit()
        print("[3/3] 表为空，已创建默认管理员 admin / admin123  【警告：请立即登录修改密码！】")
    else:
        print('[3/3] 用户表非空，无需创建默认管理员')

    cursor.close()
    conn.close()

    print('=' * 50)
    print('完成。验证登录后，可从 .env 删除 USERS_CONFIG 行。')
    print('=' * 50)


if __name__ == '__main__':
    sys.exit(main())
