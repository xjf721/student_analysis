# -*- coding: utf-8 -*-
"""
知识点数据访问层
"""
from typing import List, Optional, Dict
from sqlalchemy import func, desc
from models import db, Student, StudentKnowledgeMastery


class KnowledgeRepository:
    """
    知识点数据访问层
    
    提供知识点掌握数据相关的数据库操作
    """
    
    @staticmethod
    def get_by_student_id(student_id: int) -> List[StudentKnowledgeMastery]:
        """获取学生的所有知识点掌握情况"""
        return StudentKnowledgeMastery.get_by_student_id(student_id)
    
    @staticmethod
    def get_student_knowledge(student_id: int, knowledge_name: str) -> Optional[StudentKnowledgeMastery]:
        """获取学生特定知识点的掌握情况"""
        return StudentKnowledgeMastery.get_student_knowledge(student_id, knowledge_name)
    
    @staticmethod
    def get_all_knowledge_names() -> List[str]:
        """获取所有知识点名称"""
        results = db.session.query(
            StudentKnowledgeMastery.knowledge_name
        ).distinct().all()
        
        return [r[0] for r in results]
    
    @staticmethod
    def get_knowledge_statistics() -> List[Dict]:
        """
        获取各知识点统计数据
        
        Returns:
            知识点统计列表
        """
        results = db.session.query(
            StudentKnowledgeMastery.knowledge_name,
            func.avg(StudentKnowledgeMastery.mastery_rate).label('avg_rate'),
            func.count(StudentKnowledgeMastery.id).label('count'),
            func.min(StudentKnowledgeMastery.mastery_rate).label('min_rate'),
            func.max(StudentKnowledgeMastery.mastery_rate).label('max_rate')
        ).filter(
            StudentKnowledgeMastery.knowledge_name != '__汇总__'
        ).group_by(
            StudentKnowledgeMastery.knowledge_name
        ).order_by(
            desc('avg_rate')
        ).all()
        
        return [{
            'knowledge_name': r[0],
            'avg_mastery_rate': round(r[1] or 0, 2),
            'student_count': r[2],
            'min_rate': round(r[3] or 0, 2),
            'max_rate': round(r[4] or 0, 2)
        } for r in results]
    
    @staticmethod
    def get_weak_knowledge_points(threshold: float = 40.0) -> List[str]:
        """
        获取整体薄弱的知识点
        
        Args:
            threshold: 掌握率阈值
            
        Returns:
            薄弱知识点名称列表
        """
        stats = KnowledgeRepository.get_knowledge_statistics()
        
        return [s['knowledge_name'] for s in stats if s['avg_mastery_rate'] < threshold]
    
    @staticmethod
    def get_students_by_knowledge(knowledge_name: str, 
                                   min_rate: Optional[float] = None,
                                   max_rate: Optional[float] = None,
                                   limit: int = 50) -> List[Dict]:
        """
        获取指定知识点掌握情况的学生列表
        
        Args:
            knowledge_name: 知识点名称
            min_rate: 最低掌握率
            max_rate: 最高掌握率
            limit: 返回数量
            
        Returns:
            学生列表
        """
        query = db.session.query(Student, StudentKnowledgeMastery)\
            .join(StudentKnowledgeMastery)\
            .filter(StudentKnowledgeMastery.knowledge_name == knowledge_name)
        
        if min_rate is not None:
            query = query.filter(StudentKnowledgeMastery.mastery_rate >= min_rate)
        
        if max_rate is not None:
            query = query.filter(StudentKnowledgeMastery.mastery_rate <= max_rate)
        
        query = query.order_by(desc(StudentKnowledgeMastery.mastery_rate))
        
        results = query.limit(limit).all()
        
        return [{
            'student_id': s.id,
            'student_no': s.student_no,
            'name': s.name,
            'mastery_rate': m.mastery_rate,
            'mastery_level': m.mastery_level
        } for s, m in results]
    
    @staticmethod
    def get_heatmap_data(class_id: Optional[int] = None,
                         knowledge_limit: int = 20,
                         student_limit: int = 50) -> Dict:
        """
        获取知识点热力图数据
        
        Args:
            class_id: 班级ID
            knowledge_limit: 知识点数量限制
            student_limit: 学生数量限制
            
        Returns:
            热力图数据
        """
        # 获取知识点列表
        knowledge_stats = KnowledgeRepository.get_knowledge_statistics()[:knowledge_limit]
        knowledge_names = [k['knowledge_name'] for k in knowledge_stats]
        
        if not knowledge_names:
            return {'students': [], 'knowledge': [], 'data': []}
        
        # 获取学生列表
        query = Student.query
        if class_id:
            query = query.filter_by(class_id=class_id)
        
        students = query.limit(student_limit).all()
        
        # 构建数据矩阵
        data = []
        for s_idx, student in enumerate(students):
            for k_idx, k_name in enumerate(knowledge_names):
                mastery = StudentKnowledgeMastery.get_student_knowledge(student.id, k_name)
                if mastery:
                    data.append([s_idx, k_idx, mastery.mastery_rate])
        
        return {
            'students': [s.name for s in students],
            'knowledge': knowledge_names,
            'data': data
        }
