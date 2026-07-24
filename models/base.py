# -*- coding: utf-8 -*-
"""
数据库基础模型
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy import inspect, text
import pymysql


db = SQLAlchemy()


def ensure_database_exists(app) -> None:
    """
    确保数据库存在，不存在则自动创建
    
    Args:
        app: Flask应用实例
    """
    from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
    
    try:
        # 尝试连接到MySQL服务器（不指定数据库）
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
                cursor.execute(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{MYSQL_DATABASE}'")
                result = cursor.fetchone()
                
                if not result:
                    # 数据库不存在，创建它
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    connection.commit()
                    print(f"✓ 数据库 '{MYSQL_DATABASE}' 已自动创建")
                else:
                    print(f"✓ 数据库 '{MYSQL_DATABASE}' 已存在")
        finally:
            connection.close()
            
    except Exception as e:
        print(f"⚠ 检查/创建数据库时出错: {e}")
        print("  请确保MySQL服务正在运行，并且配置正确")


class BaseModel(db.Model):
    """基础模型类，提供通用字段和方法"""
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
    
    def save(self) -> None:
        """保存当前对象到数据库"""
        db.session.add(self)
        db.session.commit()
    
    def delete(self) -> None:
        """删除当前对象"""
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def get_by_id(cls, id: int):
        """根据ID获取对象"""
        return cls.query.get(id)
    
    @classmethod
    def get_all(cls):
        """获取所有对象"""
        return cls.query.all()


def init_db(app) -> None:
    """
    初始化数据库连接
    
    Args:
        app: Flask应用实例
    """
    # 先确保数据库存在
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('mysql'):
        ensure_database_exists(app)
    
    db.init_app(app)
    
    with app.app_context():
        # 创建所有表（如果不存在）
        db.create_all()
        ensure_schema_columns()
        print("✓ 数据库表初始化完成")


def ensure_schema_columns() -> None:
    """
    为已存在的旧表补充新增列。

    项目没有迁移框架，db.create_all() 不会给旧表自动加列；这里仅添加向后兼容的可空/默认列。
    """
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    dialect = db.engine.dialect.name

    def sql_type(mysql_type: str, sqlite_type: str = None) -> str:
        if dialect == 'mysql':
            return mysql_type
        return sqlite_type or mysql_type

    table_columns = {
        'student_knowledge_mastery': {
            'completion_rate': sql_type('FLOAT NULL'),
            'correct_rate': sql_type('FLOAT NULL'),
        },
        'student_assignment_detail': {
            'deadline_progress': sql_type('VARCHAR(50) NULL'),
            'latest_progress': sql_type('VARCHAR(50) NULL'),
            'challenge_score': sql_type('FLOAT NULL'),
            'total_challenge_count': sql_type('INTEGER DEFAULT 0'),
            'completed_challenge_count': sql_type('INTEGER DEFAULT 0'),
            'challenge_completion_rate': sql_type('FLOAT DEFAULT 0'),
            'pass_time': sql_type('DATETIME NULL'),
            'last_finish_time': sql_type('DATETIME NULL'),
        },
    }

    with db.engine.begin() as connection:
        for table_name, columns in table_columns.items():
            if table_name not in existing_tables:
                continue

            existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
