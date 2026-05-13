# -*- coding: utf-8 -*-
"""
学生数据访问层
"""
from typing import List, Optional, Dict
import pandas as pd
from sqlalchemy import func
from models import db, Student, ClassInfo, StudentKnowledgeMastery
from config import BASE_DIR, EDUCODER_ASSIGNMENT_FILE


def _read_educoder_assignment_details(student_no: str) -> List[Dict]:
    """
    从头歌作业成绩表Excel文件中读取某个学生的所有作业明细
    
    Args:
        student_no: 学号
        
    Returns:
        作业明细列表
    """
    file_path = BASE_DIR / EDUCODER_ASSIGNMENT_FILE
    if not file_path.exists():
        return []
    
    try:
        xls = pd.ExcelFile(file_path)
        assignments = []
        
        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if '学号' not in df.columns:
                    continue
                
                # 灵活匹配学号
                df['学号_str'] = df['学号'].astype(str).str.strip()
                row = df[df['学号_str'] == str(student_no).strip()]
                
                if row.empty:
                    # 尝试去前导零
                    stripped = str(student_no).lstrip('0') or '0'
                    row = df[df['学号_str'] == stripped]
                
                if row.empty:
                    continue
                
                r = row.iloc[0]
                assignment = {
                    'name': sheet_name,
                    'status': str(r.get('提交状态', '--')),
                    'score': float(r['最终成绩']) if pd.notna(r.get('最终成绩')) else None,
                    'time_cost': str(r.get('本实训总耗时', '--')),
                    'retry_count': int(r['总评测次数']) if pd.notna(r.get('总评测次数')) else 0,
                }
                assignments.append(assignment)
            except Exception:
                continue
        
        return assignments
    except Exception:
        return []


class StudentRepository:
    """
    学生数据访问层
    
    提供学生相关的数据库操作
    """
    
    @staticmethod
    def get_by_id(student_id: int) -> Optional[Student]:
        """根据ID获取学生"""
        return Student.query.get(student_id)
    
    @staticmethod
    def get_by_student_no(student_no: str) -> Optional[Student]:
        """根据学号获取学生"""
        return Student.get_by_student_no(student_no)
    
    @staticmethod
    def get_all(class_id: Optional[int] = None) -> List[Student]:
        """获取所有学生"""
        query = Student.query
        if class_id:
            query = query.filter_by(class_id=class_id)
        return query.all()
    
    @staticmethod
    def get_with_details(student_id: int) -> Optional[Dict]:
        """
        获取学生详细信息（包含关联数据）
        
        Args:
            student_id: 学生ID
            
        Returns:
            学生详情字典
        """
        student = Student.query.get(student_id)
        
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
        
        return result
    
    @staticmethod
    def get_full_overview(student_id: int) -> Optional[Dict]:
        """
        获取学生全览数据，聚合所有平台数据
        
        Args:
            student_id: 学生ID
            
        Returns:
            全览数据字典
        """
        student = Student.query.get(student_id)
        if not student:
            return None
        
        result = {
            'basic': {
                'id': student.id,
                'student_no': student.student_no,
                'name': student.name,
                'class_name': student.class_info.class_name if student.class_info else None,
                'major': student.major
            }
        }
        
        # 行为数据
        if student.behavior:
            b = student.behavior
            result['behavior'] = {
                'attendance_rate': b.attendance_rate,
                'ppt_view_rate': b.ppt_view_rate,
                'video_finish_rate': b.video_finish_rate,
                'exercise_submit_rate': b.exercise_submit_rate,
                'exercise_score_rate': b.exercise_score_rate,
                'discussion_count': b.discussion_count,
                'reply_count': b.reply_count,
                'behavior_score': b.behavior_score
            }
        else:
            result['behavior'] = None
        
        # 实践数据
        if student.practice:
            p = student.practice
            result['practice'] = {
                'total_score': p.total_score,
                'activity_score': p.activity_score,
                'avg_experiment_score': p.avg_experiment_score,
                'assignment_count': p.assignment_count,
                'high_retry_count': p.high_retry_count,
                'practice_score': p.practice_score
            }
        else:
            result['practice'] = None
        
        # 知识点掌握数据（按掌握率排序）
        masteries = StudentKnowledgeMastery.query.filter_by(
            student_id=student_id
        ).order_by(StudentKnowledgeMastery.mastery_rate.asc()).all()
        
        knowledge_overview = {
            'all_points': [],
            'weak_points': [],
            'overall_mastery_rate': None,
            'overall_completion_rate': None
        }
        
        if masteries:
            weak_threshold = 60
            for m in masteries:
                point = {
                    'knowledge_name': m.knowledge_name,
                    'mastery_rate': m.mastery_rate,
                    'mastery_level': m.mastery_level,
                    'mastery_level_name': StudentKnowledgeMastery.get_level_name(m.mastery_level),
                    'source': m.source
                }
                knowledge_overview['all_points'].append(point)
                if m.mastery_rate < weak_threshold:
                    knowledge_overview['weak_points'].append(point)
            
            # 排序：薄弱点按掌握率升序，全部按掌握率降序
            knowledge_overview['all_points'].sort(key=lambda x: x['mastery_rate'], reverse=True)
            
            # 查找汇总记录
            summary = StudentKnowledgeMastery.get_student_knowledge(student_id, '__汇总__')
            if summary:
                knowledge_overview['overall_mastery_rate'] = summary.mastery_rate
        
        result['knowledge'] = knowledge_overview
        
        # 预警信息
        latest_warning = next(iter(student.warnings), None)
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
        
        # 作业明细（从Excel文件直接读取）
        result['assignments'] = _read_educoder_assignment_details(student.student_no)
        
        # 理论vs实践对比
        theory_score = student.behavior.behavior_score if student.behavior is not None else 0
        practice_score = student.practice.practice_score if student.practice is not None else 0
        diff = theory_score - practice_score
        
        if theory_score >= 60 and practice_score >= 60:
            type_name = '双强'
        elif theory_score < 60 and practice_score < 60:
            type_name = '双弱'
        elif theory_score >= practice_score:
            type_name = '理论强实践弱'
        else:
            type_name = '理论弱实践强'
        
        result['theory_practice'] = {
            'theory_score': round(theory_score, 2),
            'practice_score': round(practice_score, 2),
            'diff': round(diff, 2),
            'type': type_name
        }
        
        return result
    
    @staticmethod
    def get_count(class_id: Optional[int] = None) -> int:
        """获取学生数量"""
        query = db.session.query(func.count(Student.id))
        if class_id:
            query = query.filter_by(class_id=class_id)
        return query.scalar() or 0
    
    @staticmethod
    def search(keyword: str, limit: int = 20) -> List[Student]:
        """
        搜索学生（按学号或姓名）
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量
            
        Returns:
            学生列表
        """
        return Student.query.filter(
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
    def delete(student_id: int) -> bool:
        """
        删除学生
        
        Args:
            student_id: 学生ID
            
        Returns:
            是否删除成功
        """
        student = Student.query.get(student_id)
        
        if not student:
            return False
        
        student.delete()
        return True
