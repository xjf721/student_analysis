# -*- coding: utf-8 -*-
"""
学生实践能力模型
"""
from typing import Optional
from datetime import datetime
from sqlalchemy import Column, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class StudentPractice(BaseModel):
    """
    学生实践能力数据模型
    
    来源：头歌
    存储学生的实践能力数据，包括实验成绩、活跃度、作业行为等。
    """
    __tablename__ = 'student_practice'
    
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, unique=True, comment='学生ID')
    
    # 实践指标
    total_score = Column(Float, default=0.0, comment='实验总成绩')
    activity_score = Column(Float, default=0.0, comment='活跃度分数')
    assignment_count = Column(Integer, default=0, comment='完成作业数')
    avg_experiment_score = Column(Float, default=0.0, comment='平均实验分数')
    high_retry_count = Column(Integer, default=0, comment='高频重试次数(提交超过5次的作业)')
    last_submit_time = Column(DateTime, nullable=True, comment='最后提交时间')
    
    # 综合评分（分析引擎计算后存储）
    practice_score = Column(Float, default=0.0, comment='实践能力综合评分')
    practice_level = Column(Integer, default=0, comment='实践能力等级：0正常/1关注/2预警/3高危')
    
    # 关联关系
    student = relationship('Student', back_populates='practice')
    
    def __repr__(self) -> str:
        return f'<StudentPractice student_id={self.student_id}>'
    
    @classmethod
    def get_by_student_id(cls, student_id: int) -> Optional['StudentPractice']:
        """
        根据学生ID获取实践数据
        
        Args:
            student_id: 学生ID
            
        Returns:
            StudentPractice对象或None
        """
        return cls.query.filter_by(student_id=student_id).first()
    
    def calculate_practice_score(self) -> float:
        """
        计算实践能力综合评分
        
        评分权重：
        - 实验总成绩：40%
        - 活跃度分数：30%
        - 平均实验分数：30%
        
        Returns:
            综合评分(0-100)
        """
        score = (
            self.total_score * 0.40 +
            self.activity_score * 0.30 +
            self.avg_experiment_score * 0.30
        )
        
        return round(score, 2)
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含实践数据的字典
        """
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else None,
            'total_score': self.total_score,
            'activity_score': self.activity_score,
            'assignment_count': self.assignment_count,
            'avg_experiment_score': self.avg_experiment_score,
            'high_retry_count': self.high_retry_count,
            'last_submit_time': self.last_submit_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_submit_time else None,
            'practice_score': self.practice_score,
            'practice_level': self.practice_level,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
