from flask import current_app
from app.extensions import get_db_connection
from datetime import datetime


class FocusService:
    """重点关注业务逻辑"""

    @staticmethod
    def get_list(status='all', keyword='', page=1, page_size=20):
        """获取关注列表"""
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = ["1=1"]
        params = []

        if status != 'all':
            conditions.append("status = %s")
            params.append(status)

        if keyword:
            conditions.append("project_name LIKE %s")
            params.append(f'%{keyword}%')

        where_clause = " AND ".join(conditions)
        offset = (page - 1) * page_size

        cursor.execute(f"""
            SELECT * FROM focus_projects 
            WHERE {where_clause}
            ORDER BY focus_time DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()

        cursor.execute(f"SELECT COUNT(*) as total FROM focus_projects WHERE {where_clause}", params)
        total = cursor.fetchone()['total']

        cursor.execute("SELECT status, COUNT(*) as count FROM focus_projects GROUP BY status")
        stats = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.close()
        return rows, total, stats  # 只返回3个值

    @staticmethod
    def add(data):
        """添加关注"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查重复
        cursor.execute("""
            SELECT id FROM focus_projects 
            WHERE project_name = %s AND publish_date = %s AND project_source = %s
        """, (data['project_name'], data['publish_date'], data['project_source']))

        if cursor.fetchone():
            return False, '该项目已在关注列表中'

        cursor.execute("""
            INSERT INTO focus_projects 
            (project_name, publish_date, project_source, project_category, detail_url, focus_time, status, remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['project_name'], data['publish_date'], data['project_source'],
            data.get('project_category', '未分类'), data.get('detail_url', ''),
            datetime.now(), 'active', data.get('remark', '')
        ))
        conn.commit()
        focus_id = cursor.lastrowid
        cursor.close()
        return True, focus_id

    @staticmethod
    def update_status(focus_id, status, remark=None):
        """更新状态"""
        conn = get_db_connection()
        cursor = conn.cursor()

        fields = ["status = %s"]
        params = [status]

        if remark is not None:
            fields.append("remark = %s")
            params.append(remark)

        params.append(focus_id)
        cursor.execute(f"UPDATE focus_projects SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected > 0

    @staticmethod
    def delete(focus_id):
        """取消关注"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM focus_projects WHERE id = %s", (focus_id,))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected > 0

    @staticmethod
    def get_tracks(focus_id):
        """获取跟踪记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tracking_records 
            WHERE focus_id = %s ORDER BY record_time DESC
        """, (focus_id,))
        rows = cursor.fetchall()
        cursor.close()
        return rows

    @staticmethod
    def add_track(focus_id, content, record_type='其他', operator='系统'):
        """添加跟踪记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracking_records 
            (focus_id, record_content, record_time, record_type, operator)
            VALUES (%s, %s, %s, %s, %s)
        """, (focus_id, content, datetime.now(), record_type, operator))
        conn.commit()
        track_id = cursor.lastrowid
        cursor.close()
        return track_id

    @staticmethod
    def check_exists(project_keys):
        """批量检查项目是否已关注"""
        if not project_keys:
            return []

        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []
        for key in project_keys:
            parts = key.split('||')
            if len(parts) == 3:
                conditions.append("(project_name = %s AND publish_date = %s AND project_source = %s)")
                params.extend(parts)

        if not conditions:
            return []

        cursor.execute(f"""
            SELECT CONCAT(project_name, '||', publish_date, '||', project_source) as pk
            FROM focus_projects WHERE {' OR '.join(conditions)}
        """, params)
        rows = cursor.fetchall()
        cursor.close()
        return [row['pk'] for row in rows]