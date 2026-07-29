# -*- coding: utf-8 -*-
"""
学生数据访问层
"""
from typing import List, Optional, Dict
from sqlalchemy import func
from models import (
    db,
    Student,
    StudentBehavior,
    StudentPractice,
    StudentKnowledgeMastery,
    WarningRecord,
    StudentAssignmentDetail,
    StudentAssignmentChallenge,
)
from services.knowledge_order import extract_knowledge_sequence, knowledge_name_sort_key


def _read_educoder_assignment_details(student_id: int) -> List[Dict]:
    """从数据库读取某个学生的头歌作业明细。"""
    details = StudentAssignmentDetail.query.filter_by(
        student_id=student_id
    ).order_by(
        StudentAssignmentDetail.sheet_order.asc()
    ).all()

    if not details:
        return []

    detail_ids = [item.id for item in details]
    challenge_rows = StudentAssignmentChallenge.query.filter(
        StudentAssignmentChallenge.assignment_detail_id.in_(detail_ids)
    ).order_by(
        StudentAssignmentChallenge.sheet_order.asc(),
        StudentAssignmentChallenge.challenge_order.asc()
    ).all()

    challenges_by_detail = {}
    for challenge in challenge_rows:
        challenges_by_detail.setdefault(challenge.assignment_detail_id, []).append(challenge.to_dict())

    assignments = []
    for item in details:
        assignment = item.to_dict()
        assignment['challenges'] = challenges_by_detail.get(item.id, [])
        assignments.append(assignment)

    return assignments


def _summarize_assignments(assignments: List[Dict]) -> Dict:
    scored = [item for item in assignments if item.get('score') is not None]
    total_challenges = sum(item.get('total_challenge_count') or 0 for item in assignments)
    completed_challenges = sum(item.get('completed_challenge_count') or 0 for item in assignments)
    completed_assignments = len([
        item for item in assignments
        if (item.get('total_challenge_count') or 0) > 0
        and (item.get('completed_challenge_count') or 0) >= (item.get('total_challenge_count') or 0)
    ])

    return {
        'assignment_total': len(assignments),
        'assignment_scored_count': len(scored),
        'assignment_completed_count': completed_assignments,
        'assignment_completion_rate': round(completed_assignments / len(assignments) * 100, 2) if assignments else None,
        'avg_score': round(sum(item['score'] for item in scored) / len(scored), 2) if scored else None,
        'high_retry_assignment_count': len([item for item in assignments if (item.get('retry_count') or 0) > 5]),
        'total_challenge_count': total_challenges,
        'completed_challenge_count': completed_challenges,
        'challenge_completion_rate': round(completed_challenges / total_challenges * 100, 2) if total_challenges else None,
    }


class StudentRepository:
    """
    学生数据访问层
    
    提供学生相关的数据库操作
    """
    
    @staticmethod
    def get_by_id(student_id: int, class_id: int) -> Optional[Student]:
        """根据ID获取学生"""
        return Student.query.filter_by(id=student_id, class_id=class_id).first()
    
    @staticmethod
    def get_by_student_no(student_no: str) -> Optional[Student]:
        """根据学号获取学生"""
        return Student.get_by_student_no(student_no)
    
    @staticmethod
    def get_all(class_id: int) -> List[Student]:
        """获取所有学生"""
        return Student.query.filter_by(class_id=class_id).all()
    
    @staticmethod
    def get_with_details(student_id: int, class_id: int) -> Optional[Dict]:
        """
        获取学生详细信息（包含关联数据）
        
        Args:
            student_id: 学生ID
            
        Returns:
            学生详情字典
        """
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        
        if not student:
            return None
        
        result = student.to_dict()
        
        # 添加行为数据
        if student.behavior:
            result['behavior'] = student.behavior.to_dict()
        
        # 添加实践数据
        if student.practice:
            result['practice'] = student.practice.to_dict()
        
        # 添加预警信息
        latest_warning = next(iter(student.warnings), None)
        if latest_warning:
            result['warning'] = latest_warning.to_dict()

        result['theory_practice'] = StudentRepository.get_theory_practice(student_id, class_id)
        result['profile_metrics'] = StudentRepository.get_profile_metrics(student_id, class_id)
        
        return result

    @staticmethod
    def get_theory_practice(student_id: int, class_id: int) -> Optional[Dict]:
        """获取归一化后的理论/实践对比。"""
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if not student:
            return None

        theory_score = 0.0
        if student.behavior:
            theory_score = student.behavior.calculate_behavior_score()

        practice_score = 0.0
        if student.practice:
            practice_score = student.practice.calculate_practice_score()

        theory_score = max(0.0, min(float(theory_score or 0), 100.0))
        practice_score = max(0.0, min(float(practice_score or 0), 100.0))
        diff = theory_score - practice_score

        if theory_score >= 70 and practice_score >= 70:
            type_name = '双强'
        elif theory_score < 60 and practice_score < 60:
            type_name = '双弱'
        elif diff >= 10:
            type_name = '理论强实践弱'
        elif diff <= -10:
            type_name = '理论弱实践强'
        else:
            type_name = '均衡'

        return {
            'theory_score': round(theory_score, 2),
            'practice_score': round(practice_score, 2),
            'diff': round(diff, 2),
            'type': type_name,
            'theory_source': '雨课堂行为综合评分',
            'practice_source': '头歌个人总成绩按实践训练数量折算为百分制'
        }

    @staticmethod
    def get_profile_metrics(student_id: int, class_id: int) -> Optional[Dict]:
        """获取学生画像补充指标。"""
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if not student:
            return None

        masteries = StudentKnowledgeMastery.query.filter(
            StudentKnowledgeMastery.student_id == student_id,
            StudentKnowledgeMastery.knowledge_name != '__汇总__'
        ).all()
        weak_count = len([m for m in masteries if (m.mastery_rate or 0) < 60])
        avg_mastery = None
        if masteries:
            avg_mastery = sum((m.mastery_rate or 0) for m in masteries) / len(masteries)

        assignment_count = 0
        avg_assignment_score = None
        high_retry_count = 0
        if student.practice:
            assignment_count = student.practice.assignment_count or 0
            avg_assignment_score = student.practice.avg_experiment_score
            high_retry_count = student.practice.high_retry_count or 0

        return {
            'knowledge_count': len(masteries),
            'weak_knowledge_count': weak_count,
            'avg_mastery_rate': round(avg_mastery, 2) if avg_mastery is not None else None,
            'assignment_count': assignment_count,
            'avg_assignment_score': avg_assignment_score,
            'high_retry_count': high_retry_count
        }
    
    @staticmethod
    def get_full_overview(student_id: int, class_id: int) -> Optional[Dict]:
        """
        获取学生全览数据，聚合所有平台数据
        
        Args:
            student_id: 学生ID
            
        Returns:
            全览数据字典
        """
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if not student:
            return None
        
        result = {
            'basic': {
                'id': student.id,
                'student_no': student.student_no,
                'name': student.name,
                'class_name': student.class_info.class_name if student.class_info else None,
                'major': student.major,
                'created_at': student.created_at.strftime('%Y-%m-%d %H:%M:%S') if student.created_at else None,
                'updated_at': student.updated_at.strftime('%Y-%m-%d %H:%M:%S') if student.updated_at else None
            }
        }
        
        # 行为数据
        if student.behavior:
            result['behavior'] = student.behavior.to_dict()
        else:
            result['behavior'] = None
        
        # 实践数据
        if student.practice:
            result['practice'] = student.practice.to_dict()
        else:
            result['practice'] = None
        
        # 知识点掌握数据（按掌握率排序）
        masteries = StudentKnowledgeMastery.query.filter_by(
            student_id=student_id
        ).order_by(StudentKnowledgeMastery.mastery_rate.asc()).all()
        
        knowledge_overview = {
            'all_points': [],
            'weak_points': [],
            'summary': None,
            'stats': {
                'total_points': 0,
                'weak_point_count': 0,
                'avg_mastery_rate': None,
                'avg_completion_rate': None,
                'avg_correct_rate': None
            },
            'overall_mastery_rate': None,
            'overall_completion_rate': None,
            'overall_correct_rate': None
        }
        
        if masteries:
            weak_threshold = 60
            for m in masteries:
                point = m.to_dict()
                if m.knowledge_name == '__汇总__':
                    knowledge_overview['summary'] = point
                    knowledge_overview['overall_mastery_rate'] = m.mastery_rate
                    knowledge_overview['overall_completion_rate'] = m.completion_rate
                    knowledge_overview['overall_correct_rate'] = m.correct_rate
                    continue

                sequence = extract_knowledge_sequence(m.knowledge_name)
                point['chapter_no'] = '.'.join(str(part) for part in sequence) if sequence else ''
                knowledge_overview['all_points'].append(point)
                if m.mastery_rate < weak_threshold:
                    knowledge_overview['weak_points'].append(point)
            
            knowledge_overview['all_points'].sort(
                key=lambda point: knowledge_name_sort_key(point.get('knowledge_name', ''))
            )
            knowledge_overview['weak_points'].sort(
                key=lambda point: knowledge_name_sort_key(point.get('knowledge_name', ''))
            )

            points = knowledge_overview['all_points']
            completion_points = [p for p in points if p.get('completion_rate') is not None]
            correct_points = [p for p in points if p.get('correct_rate') is not None]
            knowledge_overview['stats'] = {
                'total_points': len(points),
                'weak_point_count': len(knowledge_overview['weak_points']),
                'avg_mastery_rate': round(sum((p.get('mastery_rate') or 0) for p in points) / len(points), 2) if points else None,
                'avg_completion_rate': round(sum((p.get('completion_rate') or 0) for p in completion_points) / len(completion_points), 2) if completion_points else None,
                'avg_correct_rate': round(sum((p.get('correct_rate') or 0) for p in correct_points) / len(correct_points), 2) if correct_points else None
            }
        
        result['knowledge'] = knowledge_overview
        
        # 预警信息
        warnings = WarningRecord.get_by_student_id(student_id)
        result['warnings'] = [w.to_dict() for w in warnings]

        latest_warning = warnings[0] if warnings else None
        if latest_warning:
            result['warning'] = {
                'warning_score': latest_warning.warning_score,
                'warning_level': latest_warning.warning_level,
                'warning_level_name': latest_warning.get_level_name(latest_warning.warning_level),
                'warning_reason': latest_warning.warning_reason,
                'warning_type': latest_warning.warning_type
            }
        else:
            result['warning'] = None
        
        # 作业明细（导入时已落库，请求时直接从数据库读取）
        result['assignments'] = _read_educoder_assignment_details(student.id)
        result['assignment_summary'] = _summarize_assignments(result['assignments'])
        
        result['theory_practice'] = StudentRepository.get_theory_practice(student_id, class_id)
        result['profile_metrics'] = StudentRepository.get_profile_metrics(student_id, class_id)
        
        return result
    
    @staticmethod
    def get_count(class_id: int) -> int:
        """获取学生数量"""
        return db.session.query(func.count(Student.id)).filter(
            Student.class_id == class_id
        ).scalar() or 0
    
    @staticmethod
    def search(keyword: str, class_id: int, limit: int = 20) -> List[Student]:
        """
        搜索学生（按学号或姓名）
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量
            
        Returns:
            学生列表
        """
        return Student.query.filter(
            Student.class_id == class_id,
            db.or_(
                Student.student_no.like(f'%{keyword}%'),
                Student.name.like(f'%{keyword}%')
            )
        ).limit(limit).all()
    
    @staticmethod
    def create(student_no: str, name: str, 
               class_id: Optional[int] = None,
               major: Optional[str] = None) -> Student:
        """
        创建学生
        
        Args:
            student_no: 学号
            name: 姓名
            class_id: 班级ID
            major: 专业
            
        Returns:
            学生对象
        """
        student = Student(
            student_no=student_no,
            name=name,
            class_id=class_id,
            major=major
        )
        student.save()
        return student
    
    @staticmethod
    def update(student_id: int, **kwargs) -> Optional[Student]:
        """
        更新学生信息
        
        Args:
            student_id: 学生ID
            **kwargs: 更新字段
            
        Returns:
            更新后的学生对象
        """
        student = Student.query.get(student_id)
        
        if not student:
            return None
        
        for key, value in kwargs.items():
            if hasattr(student, key):
                setattr(student, key, value)
        
        db.session.commit()
        return student
    
    @staticmethod
    def delete(student_id: int, class_id: int) -> Optional[Dict]:
        """原子删除当前班级的学生及全部学生级关联数据。"""
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if not student:
            return None

        deleted_student = {
            'id': student.id,
            'student_no': student.student_no,
            'name': student.name,
        }

        try:
            StudentAssignmentChallenge.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentAssignmentDetail.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentBehavior.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentPractice.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentKnowledgeMastery.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            WarningRecord.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            db.session.delete(student)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return deleted_student
