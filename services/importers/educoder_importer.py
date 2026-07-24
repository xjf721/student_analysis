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
import re
import pandas as pd

from .base_importer import BaseImporter
from .parser_utils import (
    safe_float, safe_int, extract_rate,
    clean_student_no, clean_name, auto_map_columns, read_excel_smart
)
from models import (
    db,
    Student,
    StudentPractice,
    StudentAssignmentDetail,
    StudentAssignmentChallenge,
    ImportRecord,
)


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
        
        try:
            self._get_target_class_id()
        except ValueError as exc:
            errors.append(str(exc))
            return False, errors

        # 检查是否重复导入（允许覆盖，仅警告）
        if ImportRecord.is_imported(self.class_id, self.file_hash):
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
        
        df = auto_map_columns(self.df)
        
        # 尝试识别学号列
        student_no_col = self._find_student_no_column()
        name_col = self._find_name_column()
        
        if not student_no_col:
            errors.append('无法识别学号列，请检查文件格式')
            return False, errors
        
        for idx, row in df.iterrows():
            try:
                student_no = clean_student_no(row.get(student_no_col))
                if not student_no:
                    continue
                
                name = clean_name(row.get(name_col)) if name_col else None

                total_score = self._extract_final_score(row)
                personal_total_score = safe_float(row.get('个人总成绩'), None)
                
                practice_data = {
                    'student_no': student_no,
                    'name': name,
                    'total_score': total_score,
                    'personal_total_score': personal_total_score,
                }
                
                self.parsed_data.append(practice_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors

    def _extract_final_score(self, row) -> float:
        """从头歌总成绩表提取平台百分制最终成绩。"""
        for col in ['最终占比得分', '最终成绩', '总成绩', '成绩']:
            score = safe_float(row.get(col), None)
            if score is not None:
                return score
        return 0.0
    
    def _save_to_db(self) -> int:
        """
        保存数据到数据库
        """
        success_count = 0
        
        # 获取或创建班级
        class_id = self._get_target_class_id()
        
        for data in self.parsed_data:
            try:
                # 查找或创建学生
                student = self._find_target_student(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'] or f'学生{data["student_no"]}',
                        class_id=class_id
                    )
                    db.session.add(student)
                    db.session.flush()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                
                # 更新或创建实践数据
                practice = StudentPractice.get_by_student_id(student.id)
                if not practice:
                    practice = StudentPractice(student_id=student.id)
                
                practice.total_score = data['total_score']
                practice.activity_score = practice.activity_score or 0.0
                practice.avg_experiment_score = practice.avg_experiment_score or 0.0
                practice.assignment_count = practice.assignment_count or 0
                practice.high_retry_count = practice.high_retry_count or 0
                
                # 计算综合评分
                practice.practice_score = practice.calculate_practice_score()
                practice.practice_level = StudentPractice.calculate_practice_level(practice.practice_score)
                
                db.session.add(practice)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存学生{data.get("student_no", "未知")}失败: {str(e)}')
        
        db.session.flush()
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
        class_id = self._get_target_class_id()
        
        for data in self.parsed_data:
            try:
                student = self._find_target_student(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'] or f'学生{data["student_no"]}',
                        class_id=class_id
                    )
                    db.session.add(student)
                    db.session.flush()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                
                practice = StudentPractice.get_by_student_id(student.id)
                if not practice:
                    practice = StudentPractice(student_id=student.id)
                
                practice.activity_score = data['activity_score']
                practice.total_score = practice.total_score or 0.0
                practice.avg_experiment_score = practice.avg_experiment_score or 0.0
                practice.assignment_count = practice.assignment_count or 0
                practice.high_retry_count = practice.high_retry_count or 0
                practice.practice_score = practice.calculate_practice_score()
                practice.practice_level = StudentPractice.calculate_practice_level(practice.practice_score)
                db.session.add(practice)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存失败: {str(e)}')
        
        db.session.flush()
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
    
    def _read_all_sheets(self) -> List[Tuple[int, str, pd.DataFrame]]:
        """读取所有sheet的DataFrame列表，保留sheet顺序和名称。"""
        sheets = []
        xls = None
        for eng in ['openpyxl', 'xlrd']:
            try:
                xls = pd.ExcelFile(self.file_path, engine=eng)
                break
            except Exception:
                continue
        if xls is None:
            raise ValueError(f'无法读取文件: {self.file_path}')
        
        for sheet_order, sheet in enumerate(xls.sheet_names, start=1):
            try:
                df = read_excel_smart(self.file_path, sheet_name=sheet)
                sheets.append((sheet_order, sheet, df))
            except Exception as e:
                self.warnings.append(f'跳过sheet {sheet}: {e}')
        return sheets
    
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
        student_high_retries = {}
        student_details = {}
        student_last_submit_times = {}
        
        for sheet_order, sheet_name, df in all_sheets:
            student_no_col = self._find_column_in_sheet(df, ['学号'])
            name_col = self._find_column_in_sheet(df, ['真实姓名', '姓名'])
            score_col = self._find_column_in_sheet(df, ['最终成绩', '总分'])
            challenge_score_col = self._find_column_in_sheet(df, ['关卡得分'])
            retry_col = self._find_column_in_sheet(df, ['总评测次数'])
            status_col = self._find_column_in_sheet(df, ['提交状态'])
            deadline_progress_col = self._find_column_in_sheet(df, ['截止前完成关卡'])
            latest_progress_col = self._find_column_in_sheet(df, ['最新完成关卡'])
            pass_time_col = self._find_column_in_sheet(df, ['通关时间'])
            time_cost_col = self._find_column_in_sheet(df, ['本实训总耗时'])
            last_submit_col = self._find_column_in_sheet(df, ['最后完成时间', '更新时间', '通关时间'])
            challenge_columns = self._detect_challenge_columns(df)
            
            if not student_no_col:
                self.warnings.append(f'Sheet {sheet_order}: 找不到学号列，跳过')
                continue
            
            for idx, row in df.iterrows():
                student_no = clean_student_no(row.get(student_no_col))
                if not student_no:
                    continue
                
                score = safe_float(row.get(score_col), None) if score_col else None
                challenge_score = safe_float(row.get(challenge_score_col), None) if challenge_score_col else None
                retry_count = safe_int(row.get(retry_col)) if retry_col else 0
                
                if student_no not in student_scores:
                    student_scores[student_no] = []
                    student_names[student_no] = clean_name(row.get(name_col)) if name_col else None
                    student_high_retries[student_no] = 0
                    student_details[student_no] = []
                
                if score is not None:
                    student_scores[student_no].append(score)
                if retry_count > 5:
                    student_high_retries[student_no] += 1

                last_submit_time = self._parse_datetime(row.get(last_submit_col)) if last_submit_col else None
                if last_submit_time:
                    existing_time = student_last_submit_times.get(student_no)
                    if existing_time is None or last_submit_time > existing_time:
                        student_last_submit_times[student_no] = last_submit_time

                challenges = self._extract_challenges(row, challenge_columns)
                latest_progress = self._clean_optional_text(row.get(latest_progress_col)) if latest_progress_col else None
                completed_count, total_count = self._count_challenges(challenges, latest_progress)
                completion_rate = round(completed_count / total_count * 100, 2) if total_count else 0.0

                student_details[student_no].append({
                    'assignment_name': sheet_name,
                    'sheet_order': sheet_order,
                    'submit_status': self._clean_optional_text(row.get(status_col)) if status_col else '--',
                    'deadline_progress': self._clean_optional_text(row.get(deadline_progress_col)) if deadline_progress_col else None,
                    'latest_progress': latest_progress,
                    'score': score,
                    'challenge_score': challenge_score,
                    'time_cost': self._clean_optional_text(row.get(time_cost_col)) if time_cost_col else '--',
                    'retry_count': retry_count,
                    'total_challenge_count': total_count,
                    'completed_challenge_count': completed_count,
                    'challenge_completion_rate': completion_rate,
                    'pass_time': self._parse_datetime(row.get(pass_time_col)) if pass_time_col else None,
                    'last_finish_time': last_submit_time,
                    'challenges': challenges,
                })
        
        # 汇总
        for student_no, scores in student_scores.items():
            name = student_names.get(student_no)
            avg_score = sum(scores) / len(scores) if scores else 0
            
            self.parsed_data.append({
                'student_no': student_no,
                'name': name,
                'avg_experiment_score': avg_score,
                'assignment_count': len(scores),
                'high_retry_count': student_high_retries.get(student_no, 0),
                'last_submit_time': student_last_submit_times.get(student_no),
                'assignments': student_details.get(student_no, [])
            })
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors

    @staticmethod
    def _parse_datetime(value):
        if value is None or pd.isna(value):
            return None
        try:
            parsed = pd.to_datetime(value, errors='coerce')
            if pd.isna(parsed):
                return None
            return parsed.to_pydatetime()
        except Exception:
            return None

    @staticmethod
    def _clean_optional_text(value):
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text or text.lower() == 'nan':
            return None
        return text

    @staticmethod
    def _parse_progress(value) -> Tuple[Optional[int], Optional[int]]:
        text = EducoderAssignmentImporter._clean_optional_text(value)
        if not text:
            return None, None
        match = re.search(r'(\d+)\s*/\s*(\d+)', text)
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2))

    def _detect_challenge_columns(self, df: pd.DataFrame) -> List[Dict]:
        """识别一个 sheet 中的第 N 关重复列组。"""
        challenge_map = {}
        pattern = re.compile(r'^第(\d+)关(.+)$')
        for col in df.columns:
            match = pattern.match(str(col).strip())
            if not match:
                continue
            order = int(match.group(1))
            field_name = match.group(2).strip()
            challenge_map.setdefault(order, {})[field_name] = col

        return [
            {
                'order': order,
                'name_col': fields.get('关卡名称'),
                'start_col': fields.get('开始时间'),
                'finish_col': fields.get('完成时间'),
                'status_col': fields.get('状态'),
                'retry_col': fields.get('评测次数'),
                'comment_col': fields.get('评语'),
            }
            for order, fields in sorted(challenge_map.items())
        ]

    def _extract_challenges(self, row, challenge_columns: List[Dict]) -> List[Dict]:
        challenges = []
        for info in challenge_columns:
            name = self._clean_optional_text(row.get(info['name_col'])) if info.get('name_col') else None
            status = self._clean_optional_text(row.get(info['status_col'])) if info.get('status_col') else None
            start_time = self._parse_datetime(row.get(info['start_col'])) if info.get('start_col') else None
            finish_time = self._parse_datetime(row.get(info['finish_col'])) if info.get('finish_col') else None
            retry_count = safe_int(row.get(info['retry_col'])) if info.get('retry_col') else 0
            comment = self._clean_optional_text(row.get(info['comment_col'])) if info.get('comment_col') else None

            if not any([name, status, start_time, finish_time, retry_count, comment]):
                continue

            challenges.append({
                'challenge_order': info['order'],
                'challenge_name': name,
                'status': status,
                'start_time': start_time,
                'finish_time': finish_time,
                'retry_count': retry_count,
                'comment': comment,
            })
        return challenges

    @staticmethod
    def _is_challenge_completed(challenge: Dict) -> bool:
        status = challenge.get('status') or ''
        if any(keyword in status for keyword in ['通过', '完成', '已完成']):
            return True
        return challenge.get('finish_time') is not None

    def _count_challenges(self, challenges: List[Dict], latest_progress: Optional[str]) -> Tuple[int, int]:
        total_count = len(challenges)
        completed_count = len([item for item in challenges if self._is_challenge_completed(item)])

        progress_completed, progress_total = self._parse_progress(latest_progress)
        if progress_total is not None:
            total_count = max(total_count, progress_total)
        if progress_completed is not None:
            completed_count = max(completed_count, progress_completed)

        return completed_count, total_count

    def _save_to_db(self) -> int:
        success_count = 0

        class_id = self._get_target_class_id()
        student_ids = db.session.query(Student.id).filter(Student.class_id == class_id)
        StudentAssignmentChallenge.query.filter(
            StudentAssignmentChallenge.source_file == self.filename,
            StudentAssignmentChallenge.student_id.in_(student_ids),
        ).delete(synchronize_session=False)
        StudentAssignmentDetail.query.filter(
            StudentAssignmentDetail.source_file == self.filename,
            StudentAssignmentDetail.student_id.in_(student_ids),
        ).delete(synchronize_session=False)

        for data in self.parsed_data:
            try:
                student = self._find_target_student(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'] or f'学生{data["student_no"]}',
                        class_id=class_id
                    )
                    db.session.add(student)
                    db.session.flush()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']

                practice = StudentPractice.get_by_student_id(student.id)
                if not practice:
                    practice = StudentPractice(student_id=student.id)

                practice.activity_score = practice.activity_score or 0.0
                practice.total_score = practice.total_score or 0.0
                practice.avg_experiment_score = data['avg_experiment_score']
                practice.assignment_count = data['assignment_count']
                practice.high_retry_count = data['high_retry_count']
                practice.last_submit_time = data['last_submit_time']

                practice.practice_score = practice.calculate_practice_score()
                practice.practice_level = StudentPractice.calculate_practice_level(practice.practice_score)

                db.session.add(practice)
                for assignment in data.get('assignments', []):
                    detail = StudentAssignmentDetail(
                        student_id=student.id,
                        assignment_name=assignment['assignment_name'],
                        sheet_order=assignment['sheet_order'],
                        submit_status=assignment['submit_status'],
                        deadline_progress=assignment['deadline_progress'],
                        latest_progress=assignment['latest_progress'],
                        score=assignment['score'],
                        challenge_score=assignment['challenge_score'],
                        time_cost=assignment['time_cost'],
                        retry_count=assignment['retry_count'],
                        total_challenge_count=assignment['total_challenge_count'],
                        completed_challenge_count=assignment['completed_challenge_count'],
                        challenge_completion_rate=assignment['challenge_completion_rate'],
                        pass_time=assignment['pass_time'],
                        last_finish_time=assignment['last_finish_time'],
                        source_file=self.filename
                    )
                    db.session.add(detail)
                    db.session.flush()

                    for challenge in assignment.get('challenges', []):
                        db.session.add(StudentAssignmentChallenge(
                            assignment_detail_id=detail.id,
                            student_id=student.id,
                            assignment_name=assignment['assignment_name'],
                            sheet_order=assignment['sheet_order'],
                            challenge_order=challenge['challenge_order'],
                            challenge_name=challenge['challenge_name'],
                            status=challenge['status'],
                            start_time=challenge['start_time'],
                            finish_time=challenge['finish_time'],
                            retry_count=challenge['retry_count'],
                            comment=challenge['comment'],
                            source_file=self.filename
                        ))

                success_count += 1

            except Exception as e:
                self.errors.append(f'保存学生{data.get("student_no", "未知")}失败: {str(e)}')

        db.session.flush()
        return success_count
