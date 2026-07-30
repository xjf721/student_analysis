# -*- coding: utf-8 -*-
"""
学生知识点掌握模型
"""
from typing import Optional, List
from sqlalchemy import Column, String, Float, Integer, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class StudentKnowledgeMastery(BaseModel):
    """
    学生知识点掌握情况模型
    
    系统核心数据表，存储学生对各知识点的掌握情况。
    支持热力图、AI分析、风险分析、知识点排行等功能。
    """
    __tablename__ = 'student_knowledge_mastery'
    
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, comment='学生ID')
    knowledge_name = Column(String(200), nullable=False, comment='知识点名称')
    mastery_rate = Column(Float, default=0.0, comment='掌握率(%)')
    completion_rate = Column(Float, nullable=True, comment='完成率(%)')
    correct_rate = Column(Float, nullable=True, comment='自测习题正确率/正确率(%)')
    mastery_level = Column(Integer, default=0, comment='掌握等级：0未掌握/1入门/2熟练/3精通')
    source = Column(String(50), nullable=True, comment='数据来源：雨课堂/头歌')
    
    # 关联关系
    student = relationship('Student', back_populates='knowledge_masteries')
    
    def __repr__(self) -> str:
        return f'<StudentKnowledgeMastery student_id={self.student_id} knowledge={self.knowledge_name}>'
    
    @classmethod
    def get_by_student_id(cls, student_id: int) -> List['StudentKnowledgeMastery']:
        """
        获取学生的所有知识点掌握情况
        
        Args:
            student_id: 学生ID
            
        Returns:
            知识点掌握列表
        """
        return cls.query.filter_by(student_id=student_id).all()
    
    @classmethod
    def get_by_knowledge_name(cls, knowledge_name: str) -> List['StudentKnowledgeMastery']:
        """
        获取某知识点的所有学生掌握情况
        
        Args:
            knowledge_name: 知识点名称
            
        Returns:
            知识点掌握列表
        """
        return cls.query.filter_by(knowledge_name=knowledge_name).all()
    
    @classmethod
    def get_student_knowledge(cls, student_id: int, knowledge_name: str) -> Optional['StudentKnowledgeMastery']:
        """
        获取学生特定知识点的掌握情况
        
        Args:
            student_id: 学生ID
            knowledge_name: 知识点名称
            
        Returns:
            StudentKnowledgeMastery对象或None
        """
        return cls.query.filter_by(student_id=student_id, knowledge_name=knowledge_name).first()
    
    @staticmethod
    def calculate_mastery_level(mastery_rate: float) -> int:
        """
        根据掌握率计算掌握等级
        
        Args:
            mastery_rate: 掌握率(0-100)
            
        Returns:
            掌握等级(0-3)
        """
        if mastery_rate >= 80:
            return 3  # 精通
        elif mastery_rate >= 60:
            return 2  # 熟练
        elif mastery_rate >= 40:
            return 1  # 入门
        else:
            return 0  # 未掌握
    
    @staticmethod
    def get_level_name(level: int) -> str:
        """
        获取等级名称
        
        Args:
            level: 等级(0-3)
            
        Returns:
            等级名称
        """
        level_names = {0: '未掌握', 1: '入门', 2: '熟练', 3: '精通'}
        return level_names.get(level, '未知')
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含知识点掌握数据的字典
        """
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else None,
            'knowledge_name': self.knowledge_name,
            'mastery_rate': self.mastery_rate,
            'completion_rate': self.completion_rate,
            'correct_rate': self.correct_rate,
            'mastery_level': self.mastery_level,
            'mastery_level_name': self.get_level_name(self.mastery_level),
            'source': self.source,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
