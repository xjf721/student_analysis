# -*- coding: utf-8 -*-
"""
行为分析器

负责分析学生的学习行为数据，包括：
- 到课分析
- 视频学习分析
- 活跃度分析
- 课堂参与分析
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, desc
from models import db, Student, ClassInfo, StudentBehavior


class BehaviorAnalyzer:
    """
    行为分析器
    
    分析学生的学习行为数据并生成综合评分
    """
    
    def __init__(self, class_id: Optional[int] = None):
        """
        初始化行为分析器
        
        Args:
            class_id: 班级ID，如果指定则只分析该班级
        """
        self.class_id = class_id
    
    def analyze_all(self) -> Dict:
        """
        分析所有学生的行为数据
        
        Returns:
            分析结果字典
        """
        students = self._get_students()
        
        for student in students:
            self._analyze_student(student)
        
        db.session.commit()
        
        return {
            'success': True,
            'analyzed_count': len(students),
            'message': f'成功分析 {len(students)} 名学生的行为数据'
        }
    
    def _get_students(self) -> List[Student]:
        """
        获取待分析的学生列表
        
        Returns:
            学生列表
        """
        query = Student.query
        
        if self.class_id:
            query = query.filter_by(class_id=self.class_id)
        
        return query.all()
    
    def _analyze_student(self, student: Student) -> None:
        """
        分析单个学生的行为数据
        
        Args:
            student: 学生对象
        """
        behavior = StudentBehavior.get_by_student_id(student.id)
        
        if not behavior:
            return
        
        # 计算综合评分
        behavior.behavior_score = self._calculate_score(behavior)
        
        # 计算各维度等级
        behavior.attendance_level = self._get_level(behavior.attendance_rate, [60, 70, 80])
        
        db.session.add(behavior)
    
    def _calculate_score(self, behavior: StudentBehavior) -> float:
        """
        计算行为综合评分
        
        评分权重：
        - 到课率：30%
        - 视频完成率：25%
        - 作业提交率：20%
        - 作业得分率：15%
        - 讨论参与：10%
        
        Args:
            behavior: 行为数据对象
            
        Returns:
            综合评分(0-100)
        """
        # 讨论参与度归一化
        discussion_score = min(100, (behavior.discussion_count + behavior.reply_count) * 5)
        
        score = (
            behavior.attendance_rate * 0.30 +
            behavior.video_finish_rate * 0.25 +
            behavior.exercise_submit_rate * 0.20 +
            behavior.exercise_score_rate * 0.15 +
            discussion_score * 0.10
        )
        
        return round(score, 2)
    
    def _get_level(self, value: float, thresholds: List[float]) -> int:
        """
        根据阈值计算等级
        
        Args:
            value: 数值
            thresholds: 阈值列表 [一级阈值, 二级阈值, 三级阈值]
            
        Returns:
            等级(0-3)
        """
        if value < thresholds[0]:
            return 3  # 高危
        elif value < thresholds[1]:
            return 2  # 预警
        elif value < thresholds[2]:
            return 1  # 关注
        else:
            return 0  # 正常
    
    def get_class_statistics(self, class_id: Optional[int] = None) -> Dict:
        """
        获取班级行为统计数据
        
        Args:
            class_id: 班级ID，如果为None则获取全年级统计
            
        Returns:
            统计数据字典
        """
        query = db.session.query(
            func.avg(StudentBehavior.attendance_rate).label('avg_attendance'),
            func.avg(StudentBehavior.ppt_view_rate).label('avg_ppt_view'),
            func.avg(StudentBehavior.video_finish_rate).label('avg_video_finish'),
            func.avg(StudentBehavior.exercise_submit_rate).label('avg_exercise_submit'),
            func.avg(StudentBehavior.exercise_score_rate).label('avg_exercise_score'),
            func.avg(StudentBehavior.behavior_score).label('avg_behavior_score'),
            func.count(StudentBehavior.id).label('total_count')
        )
        
        if class_id:
            query = query.join(Student).filter(Student.class_id == class_id)
        
        result = query.first()
        
        if not result or result.total_count == 0:
            return {
                'avg_attendance_rate': 0,
                'avg_ppt_view_rate': 0,
                'avg_video_finish_rate': 0,
                'avg_exercise_submit_rate': 0,
                'avg_exercise_score_rate': 0,
                'avg_behavior_score': 0,
                'total_count': 0
            }
        
        return {
            'avg_attendance_rate': round(result.avg_attendance or 0, 2),
            'avg_ppt_view_rate': round(result.avg_ppt_view or 0, 2),
            'avg_video_finish_rate': round(result.avg_video_finish or 0, 2),
            'avg_exercise_submit_rate': round(result.avg_exercise_submit or 0, 2),
            'avg_exercise_score_rate': round(result.avg_exercise_score or 0, 2),
            'avg_behavior_score': round(result.avg_behavior_score or 0, 2),
            'total_count': result.total_count
        }
    
    def get_low_attendance_students(self, threshold: float = 60.0, limit: int = 20) -> List[Dict]:
        """
        获取到课率低于阈值的学生
        
        Args:
            threshold: 到课率阈值
            limit: 返回数量限制
            
        Returns:
            学生列表
        """
        results = db.session.query(Student, StudentBehavior)\
            .join(StudentBehavior, Student.id == StudentBehavior.student_id)\
            .filter(StudentBehavior.attendance_rate < threshold)\
            .order_by(StudentBehavior.attendance_rate)\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': student.id,
            'student_no': student.student_no,
            'name': student.name,
            'attendance_rate': behavior.attendance_rate,
            'behavior_score': behavior.behavior_score
        } for student, behavior in results]
    
    def get_radar_data(self, class_id: Optional[int] = None) -> Dict:
        """
        获取班级画像雷达图数据
        
        Args:
            class_id: 班级ID
            
        Returns:
            雷达图数据
        """
        stats = self.get_class_statistics(class_id)
        
        return {
            'indicator': [
                {'name': '到课率', 'max': 100},
                {'name': '视频完成率', 'max': 100},
                {'name': '作业提交率', 'max': 100},
                {'name': '作业得分率', 'max': 100},
                {'name': 'PPT查看率', 'max': 100}
            ],
            'values': [
                stats['avg_attendance_rate'],
                stats['avg_video_finish_rate'],
                stats['avg_exercise_submit_rate'],
                stats['avg_exercise_score_rate'],
                stats['avg_ppt_view_rate']
            ]
        }
