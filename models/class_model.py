# -*- coding: utf-8 -*-
"""
班级模型
"""
from typing import Optional, List
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import relationship

from .base import BaseModel


class ClassInfo(BaseModel):
    """
    班级信息模型
    
    存储班级的基本信息，包括班级名称、任课教师、学期等。
    """
    __tablename__ = 'class_info'
    
    class_name = Column(String(200), nullable=False, comment='班级名称')
    teacher_name = Column(String(100), nullable=True, comment='任课教师')
    term = Column(String(50), nullable=True, comment='学期')
    status = Column(String(20), nullable=False, default='active', index=True, comment='active/archived')
    notes = Column(String(500), nullable=True, comment='班级备注')
    
    # 关联关系
    students = relationship('Student', back_populates='class_info', lazy=True)
    
    def __repr__(self) -> str:
        return f'<ClassInfo {self.class_name}>'
    
    @classmethod
    def get_by_name(cls, class_name: str) -> Optional['ClassInfo']:
        """
        根据班级名称获取班级
        
        Args:
            class_name: 班级名称
            
        Returns:
            ClassInfo对象或None
        """
        return cls.query.filter_by(class_name=class_name).first()
    
    @classmethod
    def get_all_classes(cls) -> List['ClassInfo']:
        """
        获取所有班级
        
        Returns:
            班级列表
        """
        return cls.query.all()
    
    def get_student_count(self) -> int:
        """
        获取班级学生数量
        
        Returns:
            学生数量
        """
        return len(self.students)
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含班级信息的字典
        """
        return {
            'id': self.id,
            'class_name': self.class_name,
            'teacher_name': self.teacher_name,
            'term': self.term,
            'status': self.status,
            'notes': self.notes,
            'student_count': self.get_student_count(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
