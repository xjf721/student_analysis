# -*- coding: utf-8 -*-
"""
实践能力分析器

负责分析学生的实践能力数据，包括：
- 实验能力分析
- 提交行为分析
- 高频失败分析
- 实践能力评分
"""
from typing import Dict, List, Optional
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from models import db, Student, ClassInfo, StudentPractice


class PracticeAnalyzer:
    """
    实践能力分析器
    
    分析学生的实验和实践能力
    """
    
    def __init__(self, class_id: Optional[int] = None):
        """
        初始化实践能力分析器
        
        Args:
            class_id: 班级ID
        """
        self.class_id = class_id
    
    def analyze_all(self) -> Dict:
        """
        分析所有学生的实践数据
        
        Returns:
            分析结果
        """
        practices = self._get_practices()
        
        for practice in practices:
            practice.practice_score = practice.calculate_practice_score()
            practice.practice_level = self._calculate_level(practice.practice_score)
            db.session.add(practice)
        
        db.session.commit()
        
        return {
            'success': True,
            'analyzed_count': len(practices),
            'message': f'成功分析 {len(practices)} 名学生的实践数据'
        }
    
    def _get_practices(self) -> List[StudentPractice]:
        """
        获取实践数据
        """
        query = StudentPractice.query
        
        if self.class_id:
            query = query.join(Student).filter(Student.class_id == self.class_id)
        
        return query.all()
    
    def _calculate_level(self, score: float) -> int:
        """
        计算实践能力等级
        
        Args:
            score: 分数
            
        Returns:
            等级(0-3)
        """
        if score < 50:
            return 3  # 高危
        elif score < 60:
            return 2  # 预警
        elif score < 70:
            return 1  # 关注
        else:
            return 0  # 正常
    
    def get_class_statistics(self, class_id: Optional[int] = None) -> Dict:
        """
        获取班级实践统计数据
        
        Args:
            class_id: 班级ID
            
        Returns:
            统计数据
        """
        query = db.session.query(
            func.avg(StudentPractice.total_score).label('avg_total'),
            func.avg(StudentPractice.activity_score).label('avg_activity'),
            func.avg(StudentPractice.avg_experiment_score).label('avg_experiment'),
            func.avg(StudentPractice.practice_score).label('avg_practice'),
            func.sum(StudentPractice.assignment_count).label('total_assignments'),
            func.count(StudentPractice.id).label('student_count')
        )
        
        if class_id:
            query = query.join(Student).filter(Student.class_id == class_id)
        
        result = query.first()
        
        if not result or result.student_count == 0:
            return self._empty_stats()
        
        return {
            'avg_total_score': round(result.avg_total or 0, 2),
            'avg_activity_score': round(result.avg_activity or 0, 2),
            'avg_experiment_score': round(result.avg_experiment or 0, 2),
            'avg_practice_score': round(result.avg_practice or 0, 2),
            'total_assignments': result.total_assignments or 0,
            'student_count': result.student_count
        }
    
    def _empty_stats(self) -> Dict:
        """返回空统计"""
        return {
            'avg_total_score': 0,
            'avg_activity_score': 0,
            'avg_experiment_score': 0,
            'avg_practice_score': 0,
            'total_assignments': 0,
            'student_count': 0
        }
    
    def get_low_score_students(self, threshold: float = 50.0, limit: int = 20) -> List[Dict]:
        """
        获取实验成绩低于阈值的学生
        
        Args:
            threshold: 分数阈值
            limit: 返回数量
            
        Returns:
            学生列表
        """
        results = db.session.query(Student, StudentPractice)\
            .join(StudentPractice, Student.id == StudentPractice.student_id)\
            .filter(StudentPractice.avg_experiment_score < threshold)\
            .order_by(StudentPractice.avg_experiment_score)\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': student.id,
            'student_no': student.student_no,
            'name': student.name,
            'avg_experiment_score': practice.avg_experiment_score,
            'practice_score': practice.practice_score,
            'assignment_count': practice.assignment_count
        } for student, practice in results]
    
    def get_high_retry_students(self, threshold: int = 3, limit: int = 20) -> List[Dict]:
        """
        获取高频重试学生（可能存在困难）
        
        Args:
            threshold: 重试次数阈值
            limit: 返回数量
            
        Returns:
            学生列表
        """
        results = db.session.query(Student, StudentPractice)\
            .join(StudentPractice, Student.id == StudentPractice.student_id)\
            .filter(StudentPractice.high_retry_count >= threshold)\
            .order_by(desc(StudentPractice.high_retry_count))\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': student.id,
            'student_no': student.student_no,
            'name': student.name,
            'high_retry_count': practice.high_retry_count,
            'avg_experiment_score': practice.avg_experiment_score
        } for student, practice in results]
    
    def get_inactive_students(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """
        获取近期不活跃学生
        
        Args:
            days: 天数阈值
            limit: 返回数量
            
        Returns:
            学生列表
        """
        threshold_date = datetime.now() - timedelta(days=days)
        
        results = db.session.query(Student, StudentPractice)\
            .join(StudentPractice, Student.id == StudentPractice.student_id)\
            .filter(
                (StudentPractice.last_submit_time < threshold_date) |
                (StudentPractice.last_submit_time.is_(None))
            )\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': student.id,
            'student_no': student.student_no,
            'name': student.name,
            'last_submit_time': practice.last_submit_time.strftime('%Y-%m-%d %H:%M') if practice.last_submit_time else '从未提交',
            'activity_score': practice.activity_score
        } for student, practice in results]
    
    def get_theory_practice_comparison(self, class_id: Optional[int] = None) -> List[Dict]:
        """
        获取理论与实践对比数据
        
        Args:
            class_id: 班级ID
            
        Returns:
            对比数据列表
        """
        query = db.session.query(
            Student,
            StudentBehavior,
            StudentPractice
        ).join(
            StudentBehavior, Student.id == StudentBehavior.student_id
        ).join(
            StudentPractice, Student.id == StudentPractice.student_id
        )
        
        if class_id:
            query = query.filter(Student.class_id == class_id)
        
        results = query.all()
        
        data = []
        for student, behavior, practice in results:
            theory_score = behavior.behavior_score
            practice_score = practice.practice_score
            diff = theory_score - practice_score
            
            # 判断类型
            if theory_score >= 60 and practice_score >= 60:
                type_name = '双强'
            elif theory_score < 60 and practice_score < 60:
                type_name = '双弱'
            elif theory_score >= practice_score:
                type_name = '理论强实践弱'
            else:
                type_name = '理论弱实践强'
            
            data.append({
                'student_id': student.id,
                'student_no': student.student_no,
                'name': student.name,
                'theory_score': round(theory_score, 2),
                'practice_score': round(practice_score, 2),
                'diff': round(diff, 2),
                'type': type_name
            })
        
        return sorted(data, key=lambda x: abs(x['diff']), reverse=True)
