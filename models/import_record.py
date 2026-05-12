# -*- coding: utf-8 -*-
"""
导入日志模型
"""
from typing import Optional, List
from sqlalchemy import Column, String, Integer

from .base import BaseModel


class ImportRecord(BaseModel):
    """
    数据导入日志模型
    
    记录每次数据导入的详细信息，支持防止重复导入、错误追踪、回滚等功能。
    """
    __tablename__ = 'import_record'
    
    filename = Column(String(255), nullable=False, comment='导入文件名')
    import_type = Column(String(50), nullable=False, comment='导入类型：雨课堂/头歌')
    import_status = Column(String(20), default='进行中', comment='导入状态：进行中/成功/失败')
    success_count = Column(Integer, default=0, comment='成功导入数量')
    failed_count = Column(Integer, default=0, comment='失败数量')
    error_message = Column(String(1000), nullable=True, comment='错误信息')
    
    def __repr__(self) -> str:
        return f'<ImportRecord {self.filename}>'
    
    @classmethod
    def get_by_filename(cls, filename: str) -> Optional['ImportRecord']:
        """
        根据文件名获取导入记录
        
        Args:
            filename: 文件名
            
        Returns:
            ImportRecord对象或None
        """
        return cls.query.filter_by(filename=filename).first()
    
    @classmethod
    def is_imported(cls, filename: str) -> bool:
        """
        检查文件是否已成功导入
        
        Args:
            filename: 文件名
            
        Returns:
            是否已导入
        """
        record = cls.query.filter_by(filename=filename, import_status='成功').first()
        return record is not None
    
    @classmethod
    def get_recent_records(cls, limit: int = 20) -> List['ImportRecord']:
        """
        获取最近的导入记录
        
        Args:
            limit: 返回记录数量
            
        Returns:
            导入记录列表
        """
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()
    
    def mark_success(self, success_count: int) -> None:
        """
        标记导入成功
        
        Args:
            success_count: 成功导入数量
        """
        self.import_status = '成功'
        self.success_count = success_count
        self.save()
    
    def mark_failed(self, error_message: str, success_count: int = 0, failed_count: int = 0) -> None:
        """
        标记导入失败
        
        Args:
            error_message: 错误信息
            success_count: 成功数量
            failed_count: 失败数量
        """
        self.import_status = '失败'
        self.error_message = error_message
        self.success_count = success_count
        self.failed_count = failed_count
        self.save()
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含导入记录数据的字典
        """
        return {
            'id': self.id,
            'filename': self.filename,
            'import_type': self.import_type,
            'import_status': self.import_status,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'error_message': self.error_message,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
