# -*- coding: utf-8 -*-
"""
行为数据访问层
"""
from typing import List, Optional, Dict
from sqlalchemy import func, desc
from models import db, Student, StudentBehavior


class BehaviorRepository:
    """
    行为数据访问层
    
    提供行为数据相关的数据库操作
    """
    
    @staticmethod
    def get_by_student_id(student_id: int) -> Optional[StudentBehavior]:
        """根据学生ID获取行为数据"""
        return StudentBehavior.get_by_student_id(student_id)
    
    @staticmethod
    def get_all(class_id: int) -> List[StudentBehavior]:
        """获取所有行为数据"""
        return StudentBehavior.query.join(Student).filter(
            Student.class_id == class_id
        ).all()
    
    @staticmethod
    def get_statistics(class_id: int) -> Dict:
        """
        获取行为统计数据
        
        Args:
            class_id: 班级ID
            
        Returns:
            统计数据字典
        """
        query = db.session.query(
            func.avg(StudentBehavior.attendance_rate).label('avg_attendance'),
            func.avg(StudentBehavior.video_finish_rate).label('avg_video'),
            func.avg(StudentBehavior.exercise_submit_rate).label('avg_submit'),
            func.avg(StudentBehavior.exercise_score_rate).label('avg_score'),
            func.avg(StudentBehavior.behavior_score).label('avg_behavior'),
            func.count(StudentBehavior.id).label('count')
        )
        
        query = query.join(Student).filter(Student.class_id == class_id)
        
        result = query.first()
        
        if not result or result.count == 0:
            return {
                'avg_attendance_rate': 0,
                'avg_video_finish_rate': 0,
                'avg_exercise_submit_rate': 0,
                'avg_exercise_score_rate': 0,
                'avg_behavior_score': 0,
                'count': 0
            }
        
        return {
            'avg_attendance_rate': round(result.avg_attendance or 0, 2),
            'avg_video_finish_rate': round(result.avg_video or 0, 2),
            'avg_exercise_submit_rate': round(result.avg_submit or 0, 2),
            'avg_exercise_score_rate': round(result.avg_score or 0, 2),
            'avg_behavior_score': round(result.avg_behavior or 0, 2),
            'count': result.count
        }
    
    @staticmethod
    def get_low_attendance(class_id: int, threshold: float = 60.0, limit: int = 20) -> List[Dict]:
        """
        获取低到课率学生
        
        Args:
            threshold: 阈值
            limit: 返回数量
            
        Returns:
            学生列表
        """
        results = db.session.query(Student, StudentBehavior)\
            .join(StudentBehavior)\
            .filter(Student.class_id == class_id)\
            .filter(StudentBehavior.attendance_rate < threshold)\
            .order_by(StudentBehavior.attendance_rate)\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': s.id,
            'student_no': s.student_no,
            'name': s.name,
            'attendance_rate': b.attendance_rate
        } for s, b in results]
    
    @staticmethod
    def get_top_performers(class_id: int, limit: int = 10) -> List[Dict]:
        """
        获取行为表现最好的学生
        
        Args:
            limit: 返回数量
            class_id: 班级ID
            
        Returns:
            学生列表
        """
        query = db.session.query(Student, StudentBehavior)\
            .join(StudentBehavior)\
            .filter(Student.class_id == class_id)\
            .order_by(desc(StudentBehavior.behavior_score))
        
        results = query.limit(limit).all()
        
        return [{
            'student_id': s.id,
            'student_no': s.student_no,
            'name': s.name,
            'behavior_score': b.behavior_score,
            'attendance_rate': b.attendance_rate,
            'video_finish_rate': b.video_finish_rate
        } for s, b in results]
    
    @staticmethod
    def update_or_create(student_id: int, **kwargs) -> StudentBehavior:
        """
        更新或创建行为数据
        
        Args:
            student_id: 学生ID
            **kwargs: 行为数据字段
            
        Returns:
            行为数据对象
        """
        behavior = StudentBehavior.get_by_student_id(student_id)
        
        if not behavior:
            behavior = StudentBehavior(student_id=student_id)
        
        for key, value in kwargs.items():
            if hasattr(behavior, key):
                setattr(behavior, key, value)
        
        db.session.add(behavior)
        db.session.commit()
        
        return behavior
