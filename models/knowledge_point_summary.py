# -*- coding: utf-8 -*-
"""
知识点汇总模型
"""
from sqlalchemy import Column, String, Float, Integer, ForeignKey, Text

from .base import BaseModel


class KnowledgePointSummary(BaseModel):
    """
    雨课堂按知识点汇总数据。

    该表保留知识点粒度，避免把全班知识点汇总误写入学生-知识点明细表。
    """
    __tablename__ = 'knowledge_point_summary'

    class_id = Column(Integer, ForeignKey('class_info.id'), nullable=False, comment='班级ID')
    knowledge_name = Column(String(200), nullable=False, comment='知识点名称')
    mastery_rate = Column(Float, default=0.0, comment='掌握率(%)')

    published_contents = Column(Text, nullable=True, comment='发布学习内容')
    content_status = Column(String(100), nullable=True, comment='完成情况（未开始/进行中/已完成）')
    content_not_started_count = Column(Integer, default=0, comment='未开始内容数')
    content_in_progress_count = Column(Integer, default=0, comment='进行中内容数')
    content_completed_count = Column(Integer, default=0, comment='已完成内容数')
    content_completion_rate = Column(Float, default=0.0, comment='学习内容完成率(%)')

    quiz_count = Column(Integer, default=0, comment='自测习题数')
    quiz_status = Column(String(100), nullable=True, comment='作答情况（未作答/已作答）')
    quiz_unanswered_count = Column(Integer, default=0, comment='未作答数')
    quiz_answered_count = Column(Integer, default=0, comment='已作答数')
    quiz_completion_rate = Column(Float, default=0.0, comment='自测完成率(%)')
    quiz_correct_rate = Column(Float, default=0.0, comment='自测正确率(%)')

    source = Column(String(50), default='雨课堂-知识点汇总', comment='数据来源')
    source_file = Column(String(255), nullable=True, comment='来源文件')

    def to_dict(self) -> dict:
        completion_mastery_gap = (self.content_completion_rate or 0) - (self.mastery_rate or 0)

        return {
            'id': self.id,
            'class_id': self.class_id,
            'knowledge_name': self.knowledge_name,
            'mastery_rate': self.mastery_rate,
            'published_contents': self.published_contents,
            'content_status': self.content_status,
            'content_not_started_count': self.content_not_started_count,
            'content_in_progress_count': self.content_in_progress_count,
            'content_completed_count': self.content_completed_count,
            'content_completion_rate': self.content_completion_rate,
            'completion_mastery_gap': round(completion_mastery_gap, 2),
            'quiz_count': self.quiz_count,
            'quiz_status': self.quiz_status,
            'quiz_unanswered_count': self.quiz_unanswered_count,
            'quiz_answered_count': self.quiz_answered_count,
            'quiz_completion_rate': self.quiz_completion_rate,
            'quiz_correct_rate': self.quiz_correct_rate,
            'source': self.source,
            'source_file': self.source_file,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
