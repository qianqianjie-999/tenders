"""
用户数据访问层（pymysql 裸 SQL，与 focus_service 同款写法）

用户体系 2026-10-21 由 .env USERS_CONFIG 迁移至 bidding_db.users 表，
参考采购系统模式：角色（admin/user）、启用/禁用、管理员管理、自助改密。
"""
from werkzeug.security import generate_password_hash

from app.extensions import get_db_connection


class UserService:
    """users 表 CRUD"""

    @staticmethod
    def get_by_username(username):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            return cursor.fetchone()
        finally:
            cursor.close()

    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
        finally:
            cursor.close()

    @staticmethod
    def list_all():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC, id DESC")
            return cursor.fetchall()
        finally:
            cursor.close()

    @staticmethod
    def username_exists(username, exclude_id=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if exclude_id:
                cursor.execute(
                    "SELECT id FROM users WHERE username = %s AND id != %s",
                    (username, exclude_id))
            else:
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    @staticmethod
    def email_exists(email, exclude_id=None):
        if not email:
            return False
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if exclude_id:
                cursor.execute(
                    "SELECT id FROM users WHERE email = %s AND id != %s",
                    (email, exclude_id))
            else:
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    @staticmethod
    def create(username, password, role='user', full_name=None, email=None, department=None):
        """创建用户，返回新用户 id。密码明文传入，此处负责哈希。"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, email, department, role)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, generate_password_hash(password),
                  full_name or None, email or None, department or None, role))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()

    @staticmethod
    def update(user_id, fields):
        """按字段名更新（仅允许白名单字段），返回受影响行数。"""
        allowed = {'full_name', 'email', 'department', 'role', 'is_active'}
        sets = []
        params = []
        for key in allowed:
            if key in fields:
                sets.append(f"{key} = %s")
                params.append(fields[key])
        if not sets:
            return 0
        params.append(user_id)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", params)
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()

    @staticmethod
    def set_password(user_id, new_password):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                           (generate_password_hash(new_password), user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()

    @staticmethod
    def delete(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
