# -*- coding: utf-8 -*-
"""
知识点分析器

负责分析学生的知识点掌握情况，包括：
- 知识点掌握率计算
- 薄弱点识别
- 班级平均对比
- 热力图数据生成
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, desc
from models import db, Student, ClassInfo, StudentKnowledgeMastery


class KnowledgeAnalyzer:
    """
    知识点分析器
    
    分析学生的知识点掌握情况，生成热力图数据
    """
    
    def __init__(self, class_id: int):
        """
        初始化知识点分析器
        
        Args:
            class_id: 班级ID
        """
        if not class_id:
            raise ValueError('class_id is required')
        self.class_id = class_id
    
    def analyze_all(self) -> Dict:
        """
        分析所有知识点掌握数据
        
        Returns:
            分析结果
        """
        masteries = self._get_masteries()
        
        for mastery in masteries:
            mastery.mastery_level = StudentKnowledgeMastery.calculate_mastery_level(
                mastery.mastery_rate
            )
            db.session.add(mastery)
        
        db.session.commit()
        
        return {
            'success': True,
            'analyzed_count': len(masteries),
            'message': f'成功分析 {len(masteries)} 条知识点掌握数据'
        }
    
    def _get_masteries(self) -> List[StudentKnowledgeMastery]:
        """
        获取知识点掌握数据
        """
        return StudentKnowledgeMastery.query.join(Student).filter(
            Student.class_id == self.class_id
        ).all()
    
    def get_knowledge_list(self) -> List[str]:
        """
        获取所有知识点列表
        
        Returns:
            知识点名称列表
        """
        results = db.session.query(
            StudentKnowledgeMastery.knowledge_name
        ).join(Student).filter(
            Student.class_id == self.class_id,
            StudentKnowledgeMastery.knowledge_name != '__汇总__'
        ).distinct().all()
        
        return [r[0] for r in results]
    
    def get_knowledge_statistics(self) -> List[Dict]:
        """
        获取各知识点的统计数据
        
        Returns:
            知识点统计列表
        """
        query = db.session.query(
            StudentKnowledgeMastery.knowledge_name,
            func.avg(StudentKnowledgeMastery.mastery_rate).label('avg_rate'),
            func.count(StudentKnowledgeMastery.id).label('student_count'),
            func.sum(func.IF(StudentKnowledgeMastery.mastery_rate < 40, 1, 0)).label('weak_count')
        ).join(Student).filter(
            Student.class_id == self.class_id,
            StudentKnowledgeMastery.knowledge_name != '__汇总__'
        ).group_by(
            StudentKnowledgeMastery.knowledge_name
        ).order_by(
            desc('avg_rate')
        )
        
        results = query.all()
        
        return [{
            'knowledge_name': r[0],
            'avg_mastery_rate': round(r[1] or 0, 2),
            'student_count': r[2],
            'weak_count': r[3],
            'weak_ratio': round((r[3] / r[2] * 100) if r[2] > 0 else 0, 2)
        } for r in results]
    
    def get_weak_knowledge_points(self, threshold: float = 40.0, limit: int = 10) -> List[Dict]:
        """
        获取整体薄弱的知识点
        
        Args:
            threshold: 掌握率阈值
            limit: 返回数量
            
        Returns:
            薄弱知识点列表
        """
        stats = self.get_knowledge_statistics()
        
        return [s for s in stats if s['avg_mastery_rate'] < threshold][:limit]
    
    def get_student_weak_points(self, student_id: int, threshold: float = 60.0) -> List[Dict]:
        """
        获取学生的薄弱知识点
        
        Args:
            student_id: 学生ID
            threshold: 掌握率阈值
            
        Returns:
            薄弱知识点列表
        """
        student = Student.query.filter_by(id=student_id, class_id=self.class_id).first()
        if not student:
            return []

        results = StudentKnowledgeMastery.query.filter(
            StudentKnowledgeMastery.student_id == student_id,
            StudentKnowledgeMastery.mastery_rate < threshold
        ).order_by(
            StudentKnowledgeMastery.mastery_rate
        ).all()
        
        return [r.to_dict() for r in results]
    
    def get_heatmap_data(self,
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
        # 获取知识点列表（按平均掌握率排序）
        knowledge_stats = self.get_knowledge_statistics()[:knowledge_limit]
        knowledge_names = [k['knowledge_name'] for k in knowledge_stats]
        
        if not knowledge_names:
            return {'students': [], 'knowledge': [], 'data': []}
        
        # 获取学生列表
        students = Student.query.filter_by(class_id=self.class_id).limit(student_limit).all()
        
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
    
    def get_student_knowledge_ranking(self, knowledge_name: str, limit: int = 20) -> List[Dict]:
        """
        获取指定知识点的学生排名
        
        Args:
            knowledge_name: 知识点名称
            limit: 返回数量
            
        Returns:
            排名列表
        """
        results = db.session.query(Student, StudentKnowledgeMastery)\
            .join(StudentKnowledgeMastery, Student.id == StudentKnowledgeMastery.student_id)\
            .filter(Student.class_id == self.class_id)\
            .filter(StudentKnowledgeMastery.knowledge_name == knowledge_name)\
            .order_by(desc(StudentKnowledgeMastery.mastery_rate))\
            .limit(limit)\
            .all()
        
        return [{
            'rank': idx + 1,
            'student_no': student.student_no,
            'name': student.name,
            'mastery_rate': mastery.mastery_rate,
            'mastery_level': mastery.mastery_level
        } for idx, (student, mastery) in enumerate(results)]
    
    def compare_with_class_avg(self, student_id: int) -> List[Dict]:
        """
        比较学生与班级平均掌握率
        
        Args:
            student_id: 学生ID
            
        Returns:
            对比数据
        """
        student = Student.query.filter_by(id=student_id, class_id=self.class_id).first()
        if not student:
            return []
        
        # 获取学生掌握数据
        student_masteries = StudentKnowledgeMastery.get_by_student_id(student_id)
        student_dict = {m.knowledge_name: m.mastery_rate for m in student_masteries}
        
        # 获取班级平均
        class_stats = db.session.query(
            StudentKnowledgeMastery.knowledge_name,
            func.avg(StudentKnowledgeMastery.mastery_rate).label('avg_rate')
        ).join(Student).filter(
            Student.class_id == self.class_id
        ).group_by(
            StudentKnowledgeMastery.knowledge_name
        ).all()
        
        result = []
        for stat in class_stats:
            k_name = stat[0]
            avg_rate = stat[1] or 0
            student_rate = student_dict.get(k_name, 0)
            
            result.append({
                'knowledge_name': k_name,
                'student_rate': round(student_rate, 2),
                'class_avg_rate': round(avg_rate, 2),
                'diff': round(student_rate - avg_rate, 2)
            })
        
        return sorted(result, key=lambda x: x['diff'])
