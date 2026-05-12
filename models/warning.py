# -*- coding: utf-8 -*-
"""
风险预警模型
"""
from typing import Optional, List
from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class WarningRecord(BaseModel):
    """
    风险预警记录模型
    
    存储学生的学习风险预警信息。
    """
    __tablename__ = 'warning_record'
    
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, comment='学生ID')
    warning_type = Column(String(50), nullable=False, comment='预警类型：到课/视频/实验/综合')
    warning_level = Column(Integer, default=0, comment='预警等级：0正常/1关注/2预警/3高危')
    warning_score = Column(Float, default=0.0, comment='风险指数(0-100)')
    warning_reason = Column(String(500), nullable=True, comment='预警原因')
    
    # 关联关系
    student = relationship('Student', back_populates='warnings')
    
    def __repr__(self) -> str:
        return f'<WarningRecord student_id={self.student_id} type={self.warning_type}>'
    
    @classmethod
    def get_by_student_id(cls, student_id: int) -> List['WarningRecord']:
        """
        获取学生的所有预警记录
        
        Args:
            student_id: 学生ID
            
        Returns:
            预警记录列表
        """
        return cls.query.filter_by(student_id=student_id).order_by(cls.warning_score.desc()).all()
    
    @classmethod
    def get_latest_by_student_id(cls, student_id: int) -> Optional['WarningRecord']:
        """
        获取学生最新的预警记录
        
        Args:
            student_id: 学生ID
            
        Returns:
            最新的WarningRecord对象或None
        """
        return cls.query.filter_by(student_id=student_id).order_by(cls.created_at.desc()).first()
    
    @classmethod
    def get_high_risk_students(cls, min_score: float = 60.0) -> List['WarningRecord']:
        """
        获取高风险学生列表
        
        Args:
            min_score: 最低风险指数阈值
            
        Returns:
            预警记录列表
        """
        return cls.query.filter(cls.warning_score >= min_score).order_by(cls.warning_score.desc()).all()
    
    @staticmethod
    def get_level_name(level: int) -> str:
        """
        获取等级名称
        
        Args:
            level: 等级(0-3)
            
        Returns:
            等级名称
        """
        level_names = {0: '正常', 1: '关注', 2: '预警', 3: '高危'}
        return level_names.get(level, '未知')
    
    @staticmethod
    def calculate_warning_level(score: float) -> int:
        """
        根据风险指数计算预警等级
        
        Args:
            score: 风险指数(0-100)
            
        Returns:
            预警等级(0-3)
        """
        if score >= 80:
            return 3  # 高危
        elif score >= 60:
            return 2  # 预警
        elif score >= 30:
            return 1  # 关注
        else:
            return 0  # 正常
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含预警数据的字典
        """
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else None,
            'student_no': self.student.student_no if self.student else None,
            'warning_type': self.warning_type,
            'warning_level': self.warning_level,
            'warning_level_name': self.get_level_name(self.warning_level),
            'warning_score': self.warning_score,
            'warning_reason': self.warning_reason,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
