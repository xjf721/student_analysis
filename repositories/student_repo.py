# -*- coding: utf-8 -*-
"""
学生数据访问层
"""
from typing import List, Optional, Dict
from sqlalchemy import func
from models import db, Student, ClassInfo


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
        latest_warning = student.warnings[0] if student.warnings else None
        if latest_warning:
            result['warning'] = latest_warning.to_dict()
        
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
