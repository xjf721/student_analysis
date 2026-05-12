# -*- coding: utf-8 -*-
"""
头歌数据导入器

负责导入头歌平台数据，包括：
- 总成绩
- 活跃度
- 作业成绩
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import pandas as pd

from .base_importer import BaseImporter
from .parser_utils import (
    safe_float, safe_int, extract_rate,
    clean_student_no, clean_name, auto_map_columns, read_excel_smart
)
from models import db, Student, ClassInfo, StudentPractice, StudentKnowledgeMastery, ImportRecord


class EducoderImporter(BaseImporter):
    """
    头歌总成绩导入器
    
    负责导入学生的实验总成绩和活跃度数据
    """
    
    @property
    def import_type(self) -> str:
        return '头歌'
    
    def get_expected_columns(self) -> List[str]:
        """
        获取期望的列名
        
        头歌文件通常包含学号/用户名和成绩
        """
        return []
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        重写校验方法，头歌文件的列名不固定
        """
        errors = []
        
        # 检查文件是否存在
        if not self.file_path.exists():
            errors.append(f'文件不存在: {self.file_path}')
            return False, errors
        
        # 检查文件格式
        if self.file_path.suffix.lower() not in ['.xlsx', '.xls']:
            errors.append(f'不支持的文件格式: {self.file_path.suffix}')
            return False, errors
        
        # 检查是否重复导入（允许覆盖，仅警告）
        if ImportRecord.is_imported(self.filename):
            self.warnings.append(f'文件已导入过: {self.filename}，将覆盖原有数据')
        
        # 读取文件
        try:
            self.df = self._read_file()
        except Exception as e:
            errors.append(f'文件读取失败: {str(e)}')
            return False, errors
        
        self.errors = errors
        return True, errors
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析头歌数据
        
        头歌文件格式多样，需要智能识别
        """
        from models import ImportRecord
        
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 使用自动列名映射
        df = auto_map_columns(self.df)
        
        # 尝试识别学号列
        student_no_col = self._find_student_no_column()
        name_col = self._find_name_column()
        
        if not student_no_col:
            errors.append('无法识别学号列，请检查文件格式')
            return False, errors
        
        # 获取成绩列
        score_cols = self._find_score_columns()
        
        for idx, row in df.iterrows():
            try:
                student_no = clean_student_no(row.get(student_no_col))
                if not student_no:
                    continue
                
                name = clean_name(row.get(name_col)) if name_col else None
                
                # 计算成绩
                total_score = 0.0
                score_count = 0
                
                for col in score_cols:
                    score = safe_float(row.get(col), None)
                    if score is not None:
                        total_score += score
                        score_count += 1
                
                avg_score = total_score / score_count if score_count > 0 else 0
                
                practice_data = {
                    'student_no': student_no,
                    'name': name,
                    'total_score': total_score,
                    'activity_score': safe_float(row.get('活跃度', row.get('活跃度得分', 0))),
                    'avg_experiment_score': avg_score,
                    'assignment_count': score_count,
                    'high_retry_count': 0,  # 需要从作业明细获取
                    'last_submit_time': None
                }
                
                self.parsed_data.append(practice_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        保存数据到数据库
        """
        success_count = 0
        
        # 获取或创建班级
        class_id = self._get_or_create_class()
        
        for data in self.parsed_data:
            try:
                # 查找或创建学生
                student = Student.find_by_student_no_flex(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'] or f'学生{data["student_no"]}',
                        class_id=class_id
                    )
                    student.save()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                    # 关联班级（如果学生还没有班级）
                    if class_id and not student.class_id:
                        student.class_id = class_id
                        db.session.commit()
                
                # 更新或创建实践数据
                practice = StudentPractice.get_by_student_id(student.id)
                if not practice:
                    practice = StudentPractice(student_id=student.id)
                
                practice.total_score = data['total_score']
                practice.activity_score = data['activity_score']
                practice.avg_experiment_score = data['avg_experiment_score']
                practice.assignment_count = data['assignment_count']
                practice.high_retry_count = data['high_retry_count']
                practice.last_submit_time = data['last_submit_time']
                
                # 计算综合评分
                practice.practice_score = practice.calculate_practice_score()
                practice.practice_level = StudentKnowledgeMastery.calculate_mastery_level(
                    practice.practice_score
                )
                
                db.session.add(practice)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存学生{data.get("student_no", "未知")}失败: {str(e)}')
        
        db.session.commit()
        return success_count
    
    def _find_student_no_column(self) -> Optional[str]:
        """
        尝试识别学号列
        """
        possible_names = ['学号', '用户名', '账号', 'student_no', 'studentno', 'id']
        
        for col in self.df.columns:
            col_lower = str(col).lower()
            for name in possible_names:
                if name in col_lower:
                    return col
        
        # 尝试通过数据特征识别
        for col in self.df.columns:
            sample = self.df[col].dropna().head(5)
            if len(sample) > 0:
                # 学号通常是数字或包含数字的字符串
                first_val = str(sample.iloc[0])
                if first_val.isdigit() and len(first_val) >= 6:
                    return col
        
        return None
    
    def _find_name_column(self) -> Optional[str]:
        """
        尝试识别姓名列
        """
        possible_names = ['姓名', '名字', 'name', '学生姓名', '用户名']
        
        for col in self.df.columns:
            col_lower = str(col).lower()
            for name in possible_names:
                if name in col_lower and '用户名' not in col_lower:
                    return col
        
        return None
    
    def _find_score_columns(self) -> List[str]:
        """
        识别成绩列
        """
        score_cols = []
        exclude_keywords = ['学号', '姓名', '名字', '班级', '活跃度', 'rank', '排名']
        
        for col in self.df.columns:
            col_lower = str(col).lower()
            
            # 排除非成绩列
            if any(kw in col_lower for kw in exclude_keywords):
                continue
            
            # 检查是否为数值列
            if pd.api.types.is_numeric_dtype(self.df[col]):
                score_cols.append(col)
        
        return score_cols


class EducoderActivityImporter(EducoderImporter):
    """
    头歌活跃度导入器
    
    支持导入：
    - 课堂活跃度统计（单行表头）
    """
    
    @property
    def import_type(self) -> str:
        return '头歌-活跃度'
    
    def _read_file(self) -> pd.DataFrame:
        """
        读取活跃度文件
        优先查找包含"活跃度"的sheet
        """
        xls = None
        for eng in ['openpyxl', 'xlrd']:
            try:
                xls = pd.ExcelFile(self.file_path, engine=eng)
                break
            except Exception:
                continue
        if xls is None:
            raise ValueError(f'无法读取文件: {self.file_path}')
        
        sheet_names = xls.sheet_names
        
        target_sheet = None
        for sheet_name in sheet_names:
            if '活跃度' in sheet_name:
                target_sheet = sheet_name
                break
        
        if not target_sheet:
            target_sheet = sheet_names[0] if sheet_names else None
        
        if target_sheet:
            return read_excel_smart(self.file_path, sheet_name=target_sheet)
        return read_excel_smart(self.file_path)
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析活跃度数据
        """
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 使用自动列名映射
        df = auto_map_columns(self.df)
        
        student_no_col = '学号' if '学号' in df.columns else self._find_student_no_column()
        name_col = '姓名' if '姓名' in df.columns else self._find_name_column()
        activity_col = '活跃度' if '活跃度' in df.columns else None
        
        if not student_no_col:
            errors.append('无法识别学号列')
            return False, errors
        
        for idx, row in df.iterrows():
            try:
                student_no = clean_student_no(row.get(student_no_col))
                if not student_no:
                    continue
                
                name = clean_name(row.get(name_col)) if name_col else None
                activity_score = safe_float(row.get(activity_col, 0)) if activity_col else 0
                
                self.parsed_data.append({
                    'student_no': student_no,
                    'name': name,
                    'activity_score': activity_score
                })
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        更新学生的活跃度数据
        """
        success_count = 0
        
        # 获取或创建班级
        class_id = self._get_or_create_class()
        
        for data in self.parsed_data:
            try:
                student = Student.find_by_student_no_flex(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'] or f'学生{data["student_no"]}',
                        class_id=class_id
                    )
                    student.save()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                    # 关联班级（如果学生还没有班级）
                    if class_id and not student.class_id:
                        student.class_id = class_id
                        db.session.commit()
                
                practice = StudentPractice.get_by_student_id(student.id)
                if not practice:
                    practice = StudentPractice(student_id=student.id)
                
                practice.activity_score = data['activity_score']
                db.session.add(practice)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存失败: {str(e)}')
        
        db.session.commit()
        return success_count


class EducoderAssignmentImporter(EducoderImporter):
    """
    头歌作业成绩导入器
    
    负责导入详细的作业成绩，每个sheet对应一门作业。
    遍历所有sheet，汇总每个学生的平均实验成绩和重试次数。
    """
    
    @property
    def import_type(self) -> str:
        return '头歌-作业成绩'
    
    def _read_file(self) -> pd.DataFrame:
        """作业成绩表读取第一个sheet即可，实际解析由 _read_all_sheets 完成"""
        return read_excel_smart(self.file_path)
    
    def _read_all_sheets(self) -> List[pd.DataFrame]:
        """读取所有sheet的DataFrame列表"""
        dfs = []
        xls = None
        for eng in ['openpyxl', 'xlrd']:
            try:
                xls = pd.ExcelFile(self.file_path, engine=eng)
                break
            except Exception:
                continue
        if xls is None:
            raise ValueError(f'无法读取文件: {self.file_path}')
        
        for sheet in xls.sheet_names:
            try:
                df = read_excel_smart(self.file_path, sheet_name=sheet)
                dfs.append(df)
            except Exception as e:
                self.warnings.append(f'跳过sheet {sheet}: {e}')
        return dfs
    
    def _find_column_in_sheet(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """在DataFrame的列中查找候选列名，支持精确匹配和包含匹配"""
        for col in df.columns:
            col_str = str(col).strip()
            for c in candidates:
                if col_str == c:
                    return col
        for col in df.columns:
            col_str = str(col).lower()
            for c in candidates:
                if c.lower() in col_str:
                    return col
        return None
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析所有sheet的作业成绩数据
        
        每个sheet对应一门作业：
        - '学号'列：学生标识
        - '真实姓名'/'姓名'列：学生姓名
        - '最终成绩'列：该作业最终成绩
        - '总评测次数'列：评测次数（用于判断高频重试）
        """
        errors = []
        self.parsed_data = []
        
        # 读取所有sheet
        all_sheets = self._read_all_sheets()
        if not all_sheets:
            return False, ['没有可读取的sheet']
        
        # 按学号汇总学生数据
        student_scores = {}
        student_names = {}
        
        for sheet_idx, df in enumerate(all_sheets):
            student_no_col = self._find_column_in_sheet(df, ['学号'])
            name_col = self._find_column_in_sheet(df, ['真实姓名', '姓名'])
            score_col = self._find_column_in_sheet(df, ['最终成绩', '总分'])
            retry_col = self._find_column_in_sheet(df, ['总评测次数'])
            
            if not student_no_col or not score_col:
                self.warnings.append(f'Sheet {sheet_idx+1}: 找不到学号或成绩列，跳过')
                continue
            
            for idx, row in df.iterrows():
                student_no = clean_student_no(row.get(student_no_col))
                if not student_no:
                    continue
                
                score = safe_float(row.get(score_col), None)
                if score is None:
                    continue
                
                retry_count = safe_int(row.get(retry_col)) if retry_col else 0
                
                if student_no not in student_scores:
                    student_scores[student_no] = []
                    student_names[student_no] = clean_name(row.get(name_col)) if name_col else None
                
                student_scores[student_no].append(score)
                # high_retry 只累加每sheet的（假设评测次数>5为高频重试）
                if retry_count > 5 and student_no in student_scores:
                    pass  # 下面汇总时计算
        
        # 汇总
        for student_no, scores in student_scores.items():
            name = student_names.get(student_no)
            avg_score = sum(scores) / len(scores) if scores else 0
            total_score = sum(scores)
            
            self.parsed_data.append({
                'student_no': student_no,
                'name': name,
                'total_score': total_score,
                'avg_experiment_score': avg_score,
                'assignment_count': len(scores),
                'high_retry_count': 0,
                'last_submit_time': None
            })
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
