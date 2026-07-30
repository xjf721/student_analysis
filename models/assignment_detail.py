# -*- coding: utf-8 -*-
"""
头歌作业明细模型
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class StudentAssignmentDetail(BaseModel):
    """
    头歌作业成绩明细。

    粒度为学生-作业 sheet 行，用于学生全览和画像，不再在请求时读取 Excel。
    """
    __tablename__ = 'student_assignment_detail'

    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, comment='学生ID')
    assignment_name = Column(String(255), nullable=False, comment='作业/实验名称')
    sheet_order = Column(Integer, default=0, comment='作业顺序')
    submit_status = Column(String(50), nullable=True, comment='提交状态')
    deadline_progress = Column(String(50), nullable=True, comment='截止前完成关卡')
    latest_progress = Column(String(50), nullable=True, comment='最新完成关卡')
    score = Column(Float, nullable=True, comment='最终成绩')
    challenge_score = Column(Float, nullable=True, comment='关卡得分')
    time_cost = Column(String(100), nullable=True, comment='本实训总耗时')
    retry_count = Column(Integer, default=0, comment='总评测次数')
    total_challenge_count = Column(Integer, default=0, comment='关卡总数')
    completed_challenge_count = Column(Integer, default=0, comment='已完成关卡数')
    challenge_completion_rate = Column(Float, default=0.0, comment='关卡完成率(%)')
    pass_time = Column(DateTime, nullable=True, comment='通关时间')
    last_finish_time = Column(DateTime, nullable=True, comment='最后完成时间')
    source_file = Column(String(255), nullable=True, comment='来源文件')

    student = relationship('Student')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'student_id': self.student_id,
            'name': self.assignment_name,
            'status': self.submit_status,
            'deadline_progress': self.deadline_progress,
            'latest_progress': self.latest_progress,
            'score': self.score,
            'challenge_score': self.challenge_score,
            'time_cost': self.time_cost,
            'retry_count': self.retry_count,
            'total_challenge_count': self.total_challenge_count,
            'completed_challenge_count': self.completed_challenge_count,
            'challenge_completion_rate': self.challenge_completion_rate,
            'pass_time': self.pass_time.strftime('%Y-%m-%d %H:%M:%S') if self.pass_time else None,
            'last_finish_time': self.last_finish_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_finish_time else None,
            'sheet_order': self.sheet_order,
            'source_file': self.source_file,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
