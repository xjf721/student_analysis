# -*- coding: utf-8 -*-
"""
头歌作业关卡明细模型
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel


class StudentAssignmentChallenge(BaseModel):
    """
    头歌作业关卡明细。

    粒度为学生-作业-关卡，用于展示每个实验内部不同关卡的完成状态、时间和评测次数。
    """
    __tablename__ = 'student_assignment_challenge'

    assignment_detail_id = Column(
        Integer,
        ForeignKey('student_assignment_detail.id'),
        nullable=False,
        comment='作业明细ID'
    )
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False, comment='学生ID')
    assignment_name = Column(String(255), nullable=False, comment='作业/实验名称')
    sheet_order = Column(Integer, default=0, comment='作业顺序')
    challenge_order = Column(Integer, default=0, comment='关卡顺序')
    challenge_name = Column(String(255), nullable=True, comment='关卡名称')
    status = Column(String(50), nullable=True, comment='关卡状态')
    start_time = Column(DateTime, nullable=True, comment='开始时间')
    finish_time = Column(DateTime, nullable=True, comment='完成时间')
    retry_count = Column(Integer, default=0, comment='评测次数')
    comment = Column(String(255), nullable=True, comment='评语')
    source_file = Column(String(255), nullable=True, comment='来源文件')

    assignment_detail = relationship('StudentAssignmentDetail')
    student = relationship('Student')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'assignment_detail_id': self.assignment_detail_id,
            'student_id': self.student_id,
            'assignment_name': self.assignment_name,
            'sheet_order': self.sheet_order,
            'challenge_order': self.challenge_order,
            'challenge_name': self.challenge_name,
            'status': self.status,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'finish_time': self.finish_time.strftime('%Y-%m-%d %H:%M:%S') if self.finish_time else None,
            'retry_count': self.retry_count,
            'comment': self.comment,
            'source_file': self.source_file,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
