# -*- coding: utf-8 -*-
"""
风险预警引擎

负责分析学生学习风险并生成预警记录，包括：
- 风险规则配置
- 风险指数计算
- 预警记录生成
"""
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import func, desc
from models import db, Student, ClassInfo, StudentBehavior, StudentPractice, WarningRecord
from config import WARNING_RULES, WARNING_LEVELS


class WarningEngine:
    """
    风险预警引擎
    
    基于配置化规则分析学生学习风险
    """
    
    def __init__(self, class_id: Optional[int] = None):
        """
        初始化预警引擎
        
        Args:
            class_id: 班级ID
        """
        self.class_id = class_id
        self.rules = WARNING_RULES
    
    def analyze_all(self) -> Dict:
        """
        分析所有学生的风险情况
        
        Returns:
            分析结果
        """
        students = self._get_students()
        analyzed_count = 0
        
        for student in students:
            self._analyze_student(student)
            analyzed_count += 1
        
        db.session.commit()
        
        return {
            'success': True,
            'analyzed_count': analyzed_count,
            'message': f'成功分析 {analyzed_count} 名学生的风险情况'
        }
    
    def _get_students(self) -> List[Student]:
        """
        获取学生列表
        """
        query = Student.query
        
        if self.class_id:
            query = query.filter_by(class_id=self.class_id)
        
        return query.all()
    
    def _analyze_student(self, student: Student) -> None:
        """
        分析单个学生的风险情况
        
        Args:
            student: 学生对象
        """
        # 获取学生的行为和实践数据
        behavior = StudentBehavior.get_by_student_id(student.id)
        practice = StudentPractice.get_by_student_id(student.id)
        
        if not behavior:
            return
        
        # 计算各维度风险
        risk_factors = []
        total_risk_score = 0
        
        # 1. 到课率风险
        if behavior.attendance_rate < self.rules['attendance_rate']['threshold']:
            risk_score = self._calculate_risk_score(
                behavior.attendance_rate,
                self.rules['attendance_rate']['threshold']
            )
            risk_factors.append({
                'type': '到课',
                'score': risk_score,
                'reason': f"到课率({behavior.attendance_rate:.1f}%)低于阈值({self.rules['attendance_rate']['threshold']}%)"
            })
            total_risk_score += risk_score
        
        # 2. 视频完成率风险
        if behavior.video_finish_rate < self.rules['video_finish_rate']['threshold']:
            risk_score = self._calculate_risk_score(
                behavior.video_finish_rate,
                self.rules['video_finish_rate']['threshold']
            )
            risk_factors.append({
                'type': '视频',
                'score': risk_score,
                'reason': f"视频完成率({behavior.video_finish_rate:.1f}%)过低"
            })
            total_risk_score += risk_score
        
        # 3. 实验成绩风险
        if practice and practice.avg_experiment_score < self.rules['avg_experiment_score']['threshold']:
            risk_score = self._calculate_risk_score(
                practice.avg_experiment_score,
                self.rules['avg_experiment_score']['threshold']
            )
            risk_factors.append({
                'type': '实验',
                'score': risk_score,
                'reason': f"实验平均分({practice.avg_experiment_score:.1f})过低"
            })
            total_risk_score += risk_score
        
        # 4. 理论实践偏差风险
        if practice:
            theory_practice_diff = abs(behavior.behavior_score - practice.practice_score)
            if theory_practice_diff > self.rules['theory_practice_diff']['threshold']:
                risk_score = theory_practice_diff * 0.8
                risk_factors.append({
                    'type': '综合',
                    'score': risk_score,
                    'reason': f"理论与实践偏差过大({theory_practice_diff:.1f})"
                })
                total_risk_score += risk_score
        
        # 归一化风险分数
        total_risk_score = min(100, total_risk_score)
        
        # 确定最高风险等级
        warning_level = WarningRecord.calculate_warning_level(total_risk_score)
        
        # 生成预警记录
        if risk_factors:
            # 取风险最高的类型
            max_risk = max(risk_factors, key=lambda x: x['score'])
            
            # 删除旧预警记录
            WarningRecord.query.filter_by(student_id=student.id).delete()
            
            # 创建新预警记录
            warning = WarningRecord(
                student_id=student.id,
                warning_type=max_risk['type'],
                warning_level=warning_level,
                warning_score=total_risk_score,
                warning_reason='; '.join([f['reason'] for f in risk_factors])
            )
            db.session.add(warning)
    
    def _calculate_risk_score(self, value: float, threshold: float) -> float:
        """
        计算风险分数
        
        值越低于阈值，风险越高
        
        Args:
            value: 实际值
            threshold: 阈值
            
        Returns:
            风险分数(0-100)
        """
        if value >= threshold:
            return 0
        
        # 计算差距比例
        gap_ratio = (threshold - value) / threshold
        
        # 转换为风险分数
        risk_score = gap_ratio * 100
        
        return min(100, max(0, risk_score))
    
    def get_warning_students(self, min_level: int = 1, limit: int = 50) -> List[Dict]:
        """
        获取有预警的学生列表
        
        Args:
            min_level: 最低预警等级
            limit: 返回数量
            
        Returns:
            预警学生列表
        """
        results = db.session.query(Student, WarningRecord)\
            .join(WarningRecord, Student.id == WarningRecord.student_id)\
            .filter(WarningRecord.warning_level >= min_level)\
            .order_by(desc(WarningRecord.warning_score))\
            .limit(limit)\
            .all()
        
        return [{
            'student_id': student.id,
            'student_no': student.student_no,
            'name': student.name,
            'warning_type': warning.warning_type,
            'warning_level': warning.warning_level,
            'warning_level_name': WarningRecord.get_level_name(warning.warning_level),
            'warning_score': warning.warning_score,
            'warning_reason': warning.warning_reason
        } for student, warning in results]
    
    def get_warning_statistics(self, class_id: Optional[int] = None) -> Dict:
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
            'by_level': {
                '正常': 0,
                '关注': 0,
                '预警': 0,
                '高危': 0
            }
        }
        
        for level, count in results:
            level_name = WARNING_LEVELS.get(level, '未知')
            stats['by_level'][level_name] = count
            stats['total_warnings'] += count
        
        return stats
    
    def get_warning_type_distribution(self) -> Dict:
        """
        获取预警类型分布
        
        Returns:
            类型分布数据
        """
        results = db.session.query(
            WarningRecord.warning_type,
            func.count(WarningRecord.id).label('count')
        ).group_by(WarningRecord.warning_type).all()
        
        return {
            'types': [r[0] for r in results],
            'counts': [r[1] for r in results]
        }
    
    def refresh_warnings(self) -> Dict:
        """
        刷新所有预警数据（重新分析）
        
        Returns:
            刷新结果
        """
        # 清除所有预警记录
        WarningRecord.query.delete()
        
        # 重新分析
        return self.analyze_all()
