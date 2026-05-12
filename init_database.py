# -*- coding: utf-8 -*-
"""
数据库初始化脚本

用于创建数据库和所有表结构。
使用场景：
- 首次部署系统
- 数据库被删除后重新初始化
- 需要重置数据库结构

使用方法：
    python init_database.py          # 使用默认配置
    python init_database.py --reset  # 重置数据库（删除所有数据）
"""
import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
import pymysql
from app import create_app
from models import db


def create_database() -> bool:
    """
    创建数据库（如果不存在）
    
    Returns:
        是否成功
    """
    print(f"正在连接MySQL服务器: {MYSQL_HOST}:{MYSQL_PORT}...")
    
    try:
        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset='utf8mb4'
        )
        
        try:
            with connection.cursor() as cursor:
                # 检查数据库是否存在
                cursor.execute(
                    f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{MYSQL_DATABASE}'"
                )
                result = cursor.fetchone()
                
                if result:
                    print(f"✓ 数据库 '{MYSQL_DATABASE}' 已存在")
                    return True
                else:
                    # 创建数据库
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    connection.commit()
                    print(f"✓ 数据库 '{MYSQL_DATABASE}' 已创建")
                    return True
        finally:
            connection.close()
            
    except pymysql.Error as e:
        print(f"✗ 连接MySQL失败: {e}")
        print("  请检查：")
        print("  1. MySQL服务是否正在运行")
        print("  2. 数据库配置是否正确（config.py）")
        return False


def reset_database() -> bool:
    """
    重置数据库（删除并重新创建）
    
    Returns:
        是否成功
    """
    print(f"⚠ 警告：即将删除数据库 '{MYSQL_DATABASE}' 及其所有数据！")
    confirm = input("确认删除？(yes/no): ")
    
    if confirm.lower() != 'yes':
        print("已取消操作")
        return False
    
    try:
        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset='utf8mb4'
        )
        
        try:
            with connection.cursor() as cursor:
                # 删除数据库
                cursor.execute(f"DROP DATABASE IF EXISTS `{MYSQL_DATABASE}`")
                connection.commit()
                print(f"✓ 数据库 '{MYSQL_DATABASE}' 已删除")
                
                # 重新创建
                cursor.execute(
                    f"CREATE DATABASE `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                connection.commit()
                print(f"✓ 数据库 '{MYSQL_DATABASE}' 已重新创建")
                return True
        finally:
            connection.close()
            
    except pymysql.Error as e:
        print(f"✗ 重置数据库失败: {e}")
        return False


def create_tables() -> bool:
    """
    创建所有表结构
    
    Returns:
        是否成功
    """
    print("正在创建表结构...")
    
    try:
        app = create_app('dev')
        
        with app.app_context():
            # 创建所有表
            db.create_all()
            
            # 验证表是否创建成功
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            print(f"✓ 已创建 {len(tables)} 个表:")
            for table in tables:
                print(f"  - {table}")
            
            return True
            
    except Exception as e:
        print(f"✗ 创建表失败: {e}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库初始化工具')
    parser.add_argument('--reset', action='store_true', help='重置数据库（删除所有数据）')
    parser.add_argument('--tables-only', action='store_true', help='只创建表结构（不创建数据库）')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("教学过程智能分析与预警平台 - 数据库初始化")
    print("=" * 60)
    print()
    
    if args.reset:
        # 重置数据库
        if not reset_database():
            sys.exit(1)
    elif not args.tables_only:
        # 创建数据库
        if not create_database():
            sys.exit(1)
    
    # 创建表结构
    if create_tables():
        print()
        print("=" * 60)
        print("✓ 数据库初始化完成！")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("✗ 数据库初始化失败")
        print("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()
