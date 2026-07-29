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
        计算实践成绩。

        头歌总成绩导入器已经按“个人总成绩 / 实训数量”折算为百分制，
        因此实践成绩直接使用该折算结果；活跃度和平均实验分作为独立分析指标。
        
        Returns:
            实践成绩(0-100)
        """
        return self.normalize_score(self.total_score)

    @staticmethod
    def normalize_score(value: Optional[float]) -> float:
        """将常规成绩归一化到 0-100。"""
        if value is None:
            return 0.0
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(score, 100.0)), 2)

    @staticmethod
    def normalize_activity_score(value: Optional[float]) -> float:
        """
        将头歌活跃度归一化到 0-100。

        当前导出中活跃度是加权原始分（如作业完成数 * 10），满分约 900+；
        转成百分制时先按 /10 压缩，再截断到 100。
        """
        if value is None:
            return 0.0
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        if score > 100:
            score = score / 10.0
        return round(max(0.0, min(score, 100.0)), 2)

    @staticmethod
    def calculate_practice_level(score: float) -> int:
        """实践风险等级：0正常/1关注/2预警/3高危。"""
        if score < 50:
            return 3
        if score < 60:
            return 2
        if score < 70:
            return 1
        return 0
    
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
            'activity_score_normalized': self.normalize_activity_score(self.activity_score),
            'assignment_count': self.assignment_count,
            'avg_experiment_score': self.avg_experiment_score,
            'high_retry_count': self.high_retry_count,
            'last_submit_time': self.last_submit_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_submit_time else None,
            'practice_score': self.practice_score,
            'practice_level': self.practice_level,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
