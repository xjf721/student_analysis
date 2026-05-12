# -*- coding: utf-8 -*-
"""
学生行为模型
"""
from typing import Optional
from sqlalchemy import Column, Float, Integer, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class StudentBehavior(BaseModel):
    """
    学生行为数据模型
    
    来源：雨课堂
    存储学生的学习行为数据，包括到课率、视频完成率、作答率等。
    这是系统的核心数据表之一。
    """
    __tablename__ = 'student_behavior'
    
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, unique=True, comment='学生ID')
    
    # 行为指标
    attendance_rate = Column(Float, default=0.0, comment='到课率(%)')
    ppt_view_rate = Column(Float, default=0.0, comment='PPT查看率(%)')
    video_finish_rate = Column(Float, default=0.0, comment='视频完成率(%)')
    exercise_submit_rate = Column(Float, default=0.0, comment='作业提交率(%)')
    exercise_score_rate = Column(Float, default=0.0, comment='作业得分率(%)')
    discussion_count = Column(Integer, default=0, comment='讨论次数')
    reply_count = Column(Integer, default=0, comment='回复次数')
    
    # 综合评分（分析引擎计算后存储）
    behavior_score = Column(Float, default=0.0, comment='行为综合评分')
    attendance_level = Column(Integer, default=0, comment='到课等级：0正常/1关注/2预警/3高危')
    
    # 关联关系
    student = relationship('Student', back_populates='behavior')
    
    def __repr__(self) -> str:
        return f'<StudentBehavior student_id={self.student_id}>'
    
    @classmethod
    def get_by_student_id(cls, student_id: int) -> Optional['StudentBehavior']:
        """
        根据学生ID获取行为数据
        
        Args:
            student_id: 学生ID
            
        Returns:
            StudentBehavior对象或None
        """
        return cls.query.filter_by(student_id=student_id).first()
    
    def calculate_behavior_score(self) -> float:
        """
        计算行为综合评分
        
        评分权重：
        - 到课率：30%
        - 视频完成率：25%
        - 作业提交率：20%
        - 作业得分率：15%
        - 讨论参与：10%
        
        Returns:
            综合评分(0-100)
        """
        # 讨论参与度归一化（假设10次以上为满分）
        discussion_score = min(100, (self.discussion_count + self.reply_count) * 5)
        
        score = (
            self.attendance_rate * 0.30 +
            self.video_finish_rate * 0.25 +
            self.exercise_submit_rate * 0.20 +
            self.exercise_score_rate * 0.15 +
            discussion_score * 0.10
        )
        
        return round(score, 2)
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            包含行为数据的字典
        """
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else None,
            'attendance_rate': self.attendance_rate,
            'ppt_view_rate': self.ppt_view_rate,
            'video_finish_rate': self.video_finish_rate,
            'exercise_submit_rate': self.exercise_submit_rate,
            'exercise_score_rate': self.exercise_score_rate,
            'discussion_count': self.discussion_count,
            'reply_count': self.reply_count,
            'behavior_score': self.behavior_score,
            'attendance_level': self.attendance_level,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
