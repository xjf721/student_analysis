# -*- coding: utf-8 -*-
"""
预警数据访问层
"""
from typing import List, Optional, Dict
from sqlalchemy import func, desc
from models import db, Student, WarningRecord
from config import WARNING_LEVELS


class WarningRepository:
    """
    预警数据访问层
    
    提供预警记录相关的数据库操作
    """
    
    @staticmethod
    def get_by_id(warning_id: int) -> Optional[WarningRecord]:
        """根据ID获取预警记录"""
        return WarningRecord.query.get(warning_id)
    
    @staticmethod
    def get_by_student_id(student_id: int) -> List[WarningRecord]:
        """获取学生的所有预警记录"""
        return WarningRecord.get_by_student_id(student_id)
    
    @staticmethod
    def get_latest_by_student_id(student_id: int) -> Optional[WarningRecord]:
        """获取学生最新的预警记录"""
        return WarningRecord.get_latest_by_student_id(student_id)
    
    @staticmethod
    def get_high_risk_students(min_score: float = 60.0, limit: int = 50) -> List[Dict]:
        """
        获取高风险学生列表
        
        Args:
            min_score: 最低风险指数
            limit: 返回数量
            
        Returns:
            高风险学生列表
        """
        results = db.session.query(Student, WarningRecord)\
            .join(WarningRecord)\
            .filter(WarningRecord.warning_score >= min_score)\
            .order_by(desc(WarningRecord.warning_score))\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': s.id,
            'student_no': s.student_no,
            'name': s.name,
            'warning_type': w.warning_type,
            'warning_level': w.warning_level,
            'warning_level_name': WARNING_LEVELS.get(w.warning_level, '未知'),
            'warning_score': w.warning_score,
            'warning_reason': w.warning_reason,
            'created_at': w.created_at.strftime('%Y-%m-%d %H:%M') if w.created_at else None
        } for s, w in results]
    
    @staticmethod
    def get_statistics(class_id: Optional[int] = None) -> Dict:
        """
        获取预警统计数据
        
        Args:
            class_id: 班级ID
            
        Returns:
            统计数据
        """
        query = db.session.query(
            WarningRecord.warning_level,
            func.count(WarningRecord.id).label('count')
        ).group_by(WarningRecord.warning_level)
        
        if class_id:
            query = query.join(Student).filter(Student.class_id == class_id)
        
        results = query.all()
        
        stats = {
            'total_warnings': 0,
            'by_level': {level: 0 for level in WARNING_LEVELS.values()},
            'level_names': list(WARNING_LEVELS.values())
        }
        
        for level, count in results:
            level_name = WARNING_LEVELS.get(level, '未知')
            stats['by_level'][level_name] = count
            stats['total_warnings'] += count
        
        return stats
    
    @staticmethod
    def get_type_distribution() -> Dict:
        """
        获取预警类型分布
        
        Returns:
            类型分布
        """
        results = db.session.query(
            WarningRecord.warning_type,
            func.count(WarningRecord.id).label('count')
        ).group_by(WarningRecord.warning_type).all()
        
        return {
            'types': [r[0] for r in results],
            'counts': [r[1] for r in results]
        }
    
    @staticmethod
    def get_by_level(level: int, limit: int = 50) -> List[Dict]:
        """
        获取指定等级的预警学生
        
        Args:
            level: 预警等级
            limit: 返回数量
            
        Returns:
            学生列表
        """
        results = db.session.query(Student, WarningRecord)\
            .join(WarningRecord)\
            .filter(WarningRecord.warning_level == level)\
            .order_by(desc(WarningRecord.warning_score))\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': s.id,
            'student_no': s.student_no,
            'name': s.name,
            'warning_score': w.warning_score,
            'warning_reason': w.warning_reason
        } for s, w in results]
    
    @staticmethod
    def create(student_id: int, warning_type: str, 
               warning_level: int, warning_score: float,
               warning_reason: str) -> WarningRecord:
        """
        创建预警记录
        
        Args:
            student_id: 学生ID
            warning_type: 预警类型
            warning_level: 预警等级
            warning_score: 风险指数
            warning_reason: 预警原因
            
        Returns:
            预警记录对象
        """
        warning = WarningRecord(
            student_id=student_id,
            warning_type=warning_type,
            warning_level=warning_level,
            warning_score=warning_score,
            warning_reason=warning_reason
        )
        warning.save()
        return warning
    
    @staticmethod
    def delete_by_student(student_id: int) -> int:
        """
        删除学生的所有预警记录
        
        Args:
            student_id: 学生ID
            
        Returns:
            删除数量
        """
        count = WarningRecord.query.filter_by(student_id=student_id).delete()
        db.session.commit()
        return count
    
    @staticmethod
    def clear_all() -> int:
        """
        清除所有预警记录
        
        Returns:
            删除数量
        """
        count = WarningRecord.query.delete()
        db.session.commit()
        return count
