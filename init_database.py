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
    python init_database.py --tables-only
    python init_database.py --reset --confirm-reset DELETE-ALL-STUDENT-ANALYSIS-DATA
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

RESET_CONFIRMATION = 'DELETE-ALL-STUDENT-ANALYSIS-DATA'


def validate_reset_confirmation(value: Optional[str]) -> bool:
    """仅接受重建数据库所需的精确、非交互式确认短语。"""
    return value == RESET_CONFIRMATION


def load_app_dependencies():
    """仅在参数校验完成且确需建表时加载会初始化数据库的应用模块。"""
    from app import create_app
    from models import db

    return create_app, db


def load_database_dependencies():
    """参数校验完成后才加载 MySQL 驱动和连接配置。"""
    import pymysql
    from config import (
        MYSQL_DATABASE,
        MYSQL_HOST,
        MYSQL_PASSWORD,
        MYSQL_PORT,
        MYSQL_USER,
        validate_database_environment,
    )

    validate_database_environment()
    settings = {
        'host': MYSQL_HOST,
        'port': MYSQL_PORT,
        'user': MYSQL_USER,
        'password': MYSQL_PASSWORD,
        'database': MYSQL_DATABASE,
    }
    return pymysql, settings


def create_database() -> bool:
    """
    创建数据库（如果不存在）
    
    Returns:
        是否成功
    """
    try:
        pymysql, settings = load_database_dependencies()
        print(f"正在连接MySQL服务器: {settings['host']}:{settings['port']}...")
        connection = pymysql.connect(
            host=settings['host'],
            port=settings['port'],
            user=settings['user'],
            password=settings['password'],
            charset='utf8mb4'
        )
        
        try:
            with connection.cursor() as cursor:
                # 检查数据库是否存在
                cursor.execute(
                    f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{settings['database']}'"
                )
                result = cursor.fetchone()
                
                if result:
                    print(f"✓ 数据库 '{settings['database']}' 已存在")
                    return True
                else:
                    # 创建数据库
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{settings['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    connection.commit()
                    print(f"✓ 数据库 '{settings['database']}' 已创建")
                    return True
        finally:
            connection.close()
            
    except Exception as e:
        print(f"✗ MySQL 配置或连接失败: {e}")
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
    try:
        pymysql, settings = load_database_dependencies()
        print(f"⚠ 警告：即将删除数据库 '{settings['database']}' 及其所有数据！")
        connection = pymysql.connect(
            host=settings['host'],
            port=settings['port'],
            user=settings['user'],
            password=settings['password'],
            charset='utf8mb4'
        )
        
        try:
            with connection.cursor() as cursor:
                # 删除数据库
                cursor.execute(f"DROP DATABASE IF EXISTS `{settings['database']}`")
                connection.commit()
                print(f"✓ 数据库 '{settings['database']}' 已删除")
                
                # 重新创建
                cursor.execute(
                    f"CREATE DATABASE `{settings['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                connection.commit()
                print(f"✓ 数据库 '{settings['database']}' 已重新创建")
                return True
        finally:
            connection.close()
            
    except Exception as e:
        print(f"✗ MySQL 配置或重置失败: {e}")
        return False


def create_tables() -> bool:
    """
    创建所有表结构
    
    Returns:
        是否成功
    """
    print("正在创建表结构...")
    
    try:
        create_app, database = load_app_dependencies()
        config_name = 'prod' if os.environ.get('FLASK_ENV') == 'prod' else 'dev'
        app = create_app(config_name)
        
        with app.app_context():
            # 创建所有表
            database.create_all()
            
            # 验证表是否创建成功
            from sqlalchemy import inspect
            inspector = inspect(database.engine)
            tables = inspector.get_table_names()
            
            print(f"✓ 已创建 {len(tables)} 个表:")
            for table in tables:
                print(f"  - {table}")
            
            return True
            
    except Exception as e:
        print(f"✗ 创建表失败: {e}")
        return False


def main(argv=None):
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库初始化工具')
    parser.add_argument('--reset', action='store_true', help='删除并重建数据库')
    parser.add_argument(
        '--confirm-reset',
        help=f'重建时必须精确输入 {RESET_CONFIRMATION}',
    )
    parser.add_argument('--tables-only', action='store_true', help='只创建表结构（不创建数据库）')
    
    args = parser.parse_args(argv)

    if args.reset and not validate_reset_confirmation(args.confirm_reset):
        parser.error(f'--reset 必须同时提供 --confirm-reset {RESET_CONFIRMATION}')
    
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
