#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理旧数据和日志文件
- 清理数据库中指定天数前的数据
- 清理指定天数前的日志文件

用法:
    python clear_old_data.py    # 交互模式，菜单选择
"""
import os
import datetime
import pymysql
from pathlib import Path


# 预设选项
CLEANUP_OPTIONS = {
    '1': {'type': 'log', 'days': 7, 'label': '清理 7 天前的日志'},
    '2': {'type': 'log', 'days': 15, 'label': '清理 15 天前的日志'},
    '3': {'type': 'data', 'days': 30, 'label': '清理 30 天前的数据'},
    '4': {'type': 'data', 'days': 90, 'label': '清理 90 天前的数据'},
    '5': {'type': 'data', 'days': 180, 'label': '清理 180 天前的数据'},
    '6': {'type': 'data', 'days': 365, 'label': '清理 1 年前的数据'},
}


def show_menu():
    """显示清理菜单"""
    print("\n" + "=" * 50)
    print("       数据清理工具")
    print("=" * 50)
    print("请选择要清理的数据范围：")
    print("-" * 50)

    for key, option in CLEANUP_OPTIONS.items():
        cutoff = (datetime.date.today() - datetime.timedelta(days=option['days'])).strftime('%Y-%m-%d')
        print(f"  {key}. {option['label']} ({cutoff} 之前)")

    print("-" * 50)
    print("  0. 退出")
    print("=" * 50)


def cleanup_database(days_to_keep):
    """清理数据库中指定天数前的数据"""
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'bidding_user'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'bidding_db'),
        'charset': 'utf8mb4',
    }

    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days_to_keep)).strftime('%Y-%m-%d')

    # 验证密码是否已设置
    if not db_config['password']:
        print("❌ 错误：DB_PASSWORD 环境变量未设置")
        return 0

    print(f"\n开始清理数据库数据 ({cutoff_date} 之前)...")

    try:
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # 1. 统计将要删除的数据量
        cursor.execute("SELECT COUNT(*) FROM bidding_info WHERE publish_date < %s", (cutoff_date,))
        count_before_delete = cursor.fetchone()[0]

        if count_before_delete == 0:
            print(f"ℹ️  没有需要清理的旧数据")
        else:
            # 2. 删除指定日期前的数据
            delete_sql = "DELETE FROM bidding_info WHERE publish_date < %s"
            cursor.execute(delete_sql, (cutoff_date,))
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"✅ 数据库清理完成：删除了 {deleted_count} 条记录")

        # 3. 清理过期的运行日志
        cursor.execute("""
            DELETE FROM spider_run_logs
            WHERE run_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """, (days_to_keep,))
        run_logs_deleted = cursor.rowcount

        # 4. 清理过期的超时日志
        cursor.execute("""
            DELETE FROM spider_timeout_logs
            WHERE occurred_at < DATE_SUB(NOW(), INTERVAL %s DAY)
        """, (days_to_keep,))
        timeout_logs_deleted = cursor.rowcount

        conn.commit()
        conn.close()

        if run_logs_deleted > 0 or timeout_logs_deleted > 0:
            print(f"✅ 日志表清理完成：删除 {run_logs_deleted} 条运行日志，{timeout_logs_deleted} 条超时日志")

        return count_before_delete + run_logs_deleted + timeout_logs_deleted

    except Exception as e:
        print(f"❌ 数据库清理失败：{e}")
        return 0


def cleanup_log_files(days_to_keep):
    """清理指定天数前的日志文件"""
    print(f"\n开始清理日志文件...")

    # Scrapy 日志目录
    log_dirs = [
        Path(__file__).parent / 'scrapy_spider' / 'bidding_spider' / 'logs',
        Path(__file__).parent / 'logs',
    ]

    total_files_deleted = 0
    total_size_freed = 0

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue

        for log_file in log_dir.glob('*.log'):
            try:
                mtime = datetime.datetime.fromtimestamp(log_file.stat().st_mtime)
                age_days = (datetime.datetime.now() - mtime).days

                if age_days > days_to_keep:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    total_files_deleted += 1
                    total_size_freed += file_size
                    print(f"  删除：{log_file.name} ({age_days}天前，{file_size/1024:.1f}KB)")
            except Exception as e:
                print(f"  ⚠️  跳过文件 {log_file.name}: {e}")

        # 清理旧的统计 JSON 文件
        for json_file in log_dir.glob('*.json'):
            try:
                mtime = datetime.datetime.fromtimestamp(json_file.stat().st_mtime)
                age_days = (datetime.datetime.now() - mtime).days

                if age_days > days_to_keep:
                    file_size = json_file.stat().st_size
                    json_file.unlink()
                    total_files_deleted += 1
                    total_size_freed += file_size
            except Exception as e:
                print(f"  ⚠️  跳过文件 {json_file.name}: {e}")

    if total_files_deleted > 0:
        print(f"\n✅ 日志文件清理完成：删除 {total_files_deleted} 个文件，释放 {total_size_freed/1024/1024:.2f}MB 空间")
    else:
        print(f"\nℹ️  没有需要清理的日志文件")

    return total_files_deleted, total_size_freed


def cleanup_old_data(days_to_keep, cleanup_type='all'):
    """统一清理入口

    Args:
        days_to_keep: 保留最近多少天的数据
        cleanup_type: 清理类型 ('data'=数据库数据，'log'=日志文件，'all'=全部)
    """
    db_count = 0
    file_count = 0
    size_freed = 0

    if cleanup_type in ('data', 'all'):
        db_count = cleanup_database(days_to_keep)

    if cleanup_type in ('log', 'all'):
        file_count, size_freed = cleanup_log_files(days_to_keep)

    # 汇总
    print(f"\n{'='*50}")
    print(f"清理完成！")
    if cleanup_type in ('data', 'all'):
        print(f"  - 删除数据库记录：{db_count} 条")
    if cleanup_type in ('log', 'all'):
        print(f"  - 删除日志文件：{file_count} 个")
        print(f"  - 释放空间：{size_freed/1024/1024:.2f}MB")
    print(f"  - 保留天数：{days_to_keep} 天")
    print(f"{'='*50}")


def main():
    """主函数 - 交互模式"""
    # 尝试加载 .env 文件
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        print(f"正在加载环境变量：{env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

    while True:
        show_menu()
        try:
            choice = input("\n请输入选项 (0-6): ").strip()
        except EOFError:
            print("\n检测到非交互模式，退出清理工具")
            break

        if choice == '0':
            print("退出清理工具，再见！")
            break

        if choice in CLEANUP_OPTIONS:
            option = CLEANUP_OPTIONS[choice]
            days = option['days']
            label = option['label']
            cleanup_type = option['type']

            print(f"\n准备 {label}...")
            print("-" * 50)

            # 二次确认
            try:
                confirm = input("确认执行清理？(y/n): ").strip().lower()
            except EOFError:
                print("非交互模式，自动取消")
                break

            if confirm == 'y':
                cleanup_old_data(days_to_keep=days, cleanup_type=cleanup_type)
            else:
                print("已取消清理操作")
        else:
            print("❌ 无效选项，请重新输入")


if __name__ == "__main__":
    main()
