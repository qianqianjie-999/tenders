from flask import current_app
from app.extensions import get_db_connection
from datetime import datetime


class FocusService:
    """重点关注业务逻辑"""

    # 公告/需求分类规则（2026-10-21 与用户确认）：
    # 类别含「需求」或「计划」=> 需求类；其余 => 公告类
    # 注意：关键词必须走 %s 参数化（连接未声明 utf8mb4 时中文裸写进 SQL 会编码报错）

    @staticmethod
    def get_list(status='all', keyword='', page=1, page_size=20, notice_type='all'):
        """获取关注列表。notice_type: all / notice(公告) / demand(需求)"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            demand_cond = "(project_category LIKE %s OR project_category LIKE %s)"
            demand_params = ['%需求%', '%计划%']

            conditions = ["1=1"]
            params = []

            if status != 'all':
                conditions.append("status = %s")
                params.append(status)

            if keyword:
                conditions.append("project_name LIKE %s")
                params.append(f'%{keyword}%')

            if notice_type == 'demand':
                conditions.append(demand_cond)
                params += demand_params
            elif notice_type == 'notice':
                conditions.append(f"NOT {demand_cond}")
                params += demand_params

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

            # 公告/需求分类统计（用于页签数量展示）
            cursor.execute(f"""
                SELECT
                    SUM(CASE WHEN {demand_cond} THEN 1 ELSE 0 END) AS demand,
                    SUM(CASE WHEN NOT {demand_cond} THEN 1 ELSE 0 END) AS notice
                FROM focus_projects
            """, demand_params * 2)
            type_stats = cursor.fetchone()

            cursor.close()
            return rows, total, stats, type_stats
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def add(data, focused_by=None):
        """添加关注。focused_by: 操作人用户名（2026-10-21 新增）"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id FROM focus_projects
                WHERE project_name = %s AND publish_date = %s AND project_source = %s
            """, (data['project_name'], data['publish_date'], data['project_source']))

            if cursor.fetchone():
                cursor.close()
                return False, '该项目已在关注列表中'

            cursor.execute("""
                INSERT INTO focus_projects
                (project_name, publish_date, project_source, project_category, detail_url, focus_time, status, remark, focused_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['project_name'], data['publish_date'], data['project_source'],
                data.get('project_category', '未分类'), data.get('detail_url', ''),
                datetime.now(), 'active', data.get('remark', ''), focused_by
            ))
            conn.commit()
            focus_id = cursor.lastrowid
            cursor.close()
            return True, focus_id
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def update_status(focus_id, status, remark=None):
        """更新状态"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
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
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def delete(focus_id):
        """取消关注"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM focus_projects WHERE id = %s", (focus_id,))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            return affected > 0
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def get_tracks(focus_id):
        """获取跟踪记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM tracking_records
                WHERE focus_id = %s ORDER BY record_time DESC
            """, (focus_id,))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def add_track(focus_id, content, record_type='其他', operator='系统'):
        """添加跟踪记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO tracking_records
                (focus_id, record_content, record_time, record_type, operator)
                VALUES (%s, %s, %s, %s, %s)
            """, (focus_id, content, datetime.now(), record_type, operator))
            conn.commit()
            track_id = cursor.lastrowid
            cursor.close()
            return track_id
        except Exception:
            cursor.close()
            raise

    @staticmethod
    def check_exists(project_keys):
        """批量检查项目是否已关注"""
        if not project_keys:
            return []

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            conditions = []
            params = []
            for key in project_keys:
                parts = key.split('||')
                if len(parts) == 3:
                    conditions.append("(project_name = %s AND publish_date = %s AND project_source = %s)")
                    params.extend(parts)

            if not conditions:
                cursor.close()
                return []

            cursor.execute(f"""
                SELECT CONCAT(project_name, '||', publish_date, '||', project_source) as pk
                FROM focus_projects WHERE {' OR '.join(conditions)}
            """, params)
            rows = cursor.fetchall()
            cursor.close()
            return [row['pk'] for row in rows]
        except Exception:
            cursor.close()
            raise