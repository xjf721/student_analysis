# -*- coding: utf-8 -*-
"""
学生模型
"""
from typing import Optional, List
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship

from .base import db, BaseModel


class Student(BaseModel):
    """
    学生基础信息模型
    
    存储学生的基本个人信息，与班级关联。
    """
    __tablename__ = 'student'
    
    student_no = Column(String(50), unique=True, nullable=False, comment='学号')
    name = Column(String(100), nullable=False, comment='姓名')
    class_id = Column(Integer, ForeignKey('class_info.id'), nullable=True, comment='班级ID')
    major = Column(String(100), nullable=True, comment='专业')
    
    # 关联关系
    class_info = relationship('ClassInfo', back_populates='students')
    behavior = relationship('StudentBehavior', back_populates='student', uselist=False, lazy=True)
    practice = relationship('StudentPractice', back_populates='student', uselist=False, lazy=True)
    knowledge_masteries = relationship('StudentKnowledgeMastery', back_populates='student', lazy=True)
    warnings = relationship('WarningRecord', back_populates='student', lazy=True)
    
    def __repr__(self) -> str:
        return f'<Student {self.student_no} - {self.name}>'
    
    @classmethod
    def get_by_student_no(cls, student_no: str) -> Optional['Student']:
        """
        根据学号获取学生
        
        Args:
            student_no: 学号
            
        Returns:
            Student对象或None
        """
        return cls.query.filter_by(student_no=student_no).first()
    
    @classmethod
    def get_by_class_id(cls, class_id: int) -> List['Student']:
        """
        获取指定班级的所有学生
        
        Args:
            class_id: 班级ID
            
        Returns:
            学生列表
        """
        return cls.query.filter_by(class_id=class_id).all()
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含学生信息的字典
        """
        return {
            'id': self.id,
            'student_no': self.student_no,
            'name': self.name,
            'class_id': self.class_id,
            'class_name': self.class_info.class_name if self.class_info else None,
            'major': self.major,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
