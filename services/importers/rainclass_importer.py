# -*- coding: utf-8 -*-
"""
雨课堂数据导入器

负责导入雨课堂学习过程数据，包括：
- 到课率
- 视频完成率
- 作答率
- 得分率
"""
from typing import List, Dict, Tuple
import pandas as pd

from .base_importer import BaseImporter
from .parser_utils import (
    safe_float, safe_int, extract_rate, 
    clean_student_no, clean_name, auto_map_columns, read_excel_smart
)
from models import db, Student, StudentBehavior, StudentKnowledgeMastery, KnowledgePointSummary


class RainClassSummaryImporter(BaseImporter):
    """
    雨课堂学生汇总表导入器
    
    支持导入雨课堂学生汇总表（.xls格式）
    数据字段：学号、姓名、知识点掌握率、完成情况、完成率、自测作答情况、正确情况、正确率
    """
    
    @property
    def import_type(self) -> str:
        return '雨课堂-学生汇总'
    
    def get_expected_columns(self) -> List[str]:
        return ['学号', '姓名']
    
    def _read_file(self) -> pd.DataFrame:
        """
        读取学生汇总表
        优先查找包含"数据结构"或"学生汇总"的sheet
        """
        # 尝试多种引擎打开 ExcelFile
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
        
        # 优先查找包含"数据结构"或"汇总"的sheet
        target_sheet = None
        for sheet_name in sheet_names:
            if '数据结构' in sheet_name or '汇总' in sheet_name:
                target_sheet = sheet_name
                break
        
        if not target_sheet:
            target_sheet = sheet_names[0] if sheet_names else None
        
        if target_sheet:
            df = read_excel_smart(self.file_path, sheet_name=target_sheet)
        else:
            df = read_excel_smart(self.file_path)
        
        # 处理列名映射（'学生' -> '姓名'）
        if '学生' in df.columns and '姓名' not in df.columns:
            df = df.rename(columns={'学生': '姓名'})
        
        return df
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析学生汇总数据
        """
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 使用自动列名映射
        df = auto_map_columns(self.df)
        
        # 过滤有效数据行（学号为数字的行）
        df = df[df['学号'].apply(lambda x: str(x).strip().isdigit() if pd.notna(x) else False)]
        
        for idx, row in df.iterrows():
            try:
                student_no = clean_student_no(row.get('学号'))
                name = clean_name(row.get('姓名'))
                
                if not student_no:
                    continue
                
                # 提取汇总数据
                summary_data = {
                    'student_no': student_no,
                    'name': name,
                    'overall_mastery_rate': extract_rate(row.get('知识点掌握率', 0)),
                    'completion_rate': extract_rate(row.get('完成率', 0)),
                    'self_test_correct_rate': extract_rate(row.get('正确率', 0)),
                    'knowledge_completion_count': safe_int(row.get('完成情况', 0)),
                }
                
                self.parsed_data.append(summary_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        保存汇总数据到数据库
        更新学生的知识点掌握概览
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
                        name=data['name'],
                        class_id=class_id
                    )
                    student.save()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                    
                    # 关联班级（如果学生还没有班级）
                    if class_id and not student.class_id:
                        student.class_id = class_id
                
                # 更新或创建知识点掌握概览记录
                # '__汇总__' 为内部占位符，存储学生在所有知识点上的整体掌握率，
                # 来源于雨课堂学生汇总表的"知识点掌握率"列，非Excel中的实际知识点名称。
                # 该占位符已在所有对外API中过滤，前端不可见。
                mastery = StudentKnowledgeMastery.get_student_knowledge(
                    student.id, '__汇总__'
                )
                
                if not mastery:
                    mastery = StudentKnowledgeMastery(
                        student_id=student.id,
                        knowledge_name='__汇总__',
                        source='雨课堂-汇总'
                    )
                
                mastery.mastery_rate = data['overall_mastery_rate']
                mastery.completion_rate = data['completion_rate']
                mastery.correct_rate = data['self_test_correct_rate']
                mastery.mastery_level = StudentKnowledgeMastery.calculate_mastery_level(
                    data['overall_mastery_rate']
                )
                mastery.source = '雨课堂-汇总'
                
                db.session.add(mastery)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存学生{data.get("student_no", "未知")}失败: {str(e)}')
        
        db.session.commit()
        return success_count


class RainClassKnowledgeDetailImporter(BaseImporter):
    """
    雨课堂知识图谱学习数据明细表导入器（预留扩展）
    
    支持导入知识点宽表结构：
    - 每个知识点占3列（完成率、自测习题正确率、掌握率）
    - 第一行为知识点名称，第二行为指标名称
    - 从第三行开始为学生数据
    
    注意：此导入器为后续扩展预留，当前版本暂不启用
    """
    
    @property
    def import_type(self) -> str:
        return '雨课堂-知识图谱明细'
    
    def get_expected_columns(self) -> List[str]:
        return []
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        重写校验方法，知识图谱明细表用 header=None 读取，
        列名为整数，不能通过列名校验
        """
        errors = []
        
        if not self.file_path.exists():
            errors.append(f'文件不存在: {self.file_path}')
            return False, errors
        
        if self.file_path.suffix.lower() not in ['.xlsx', '.xls']:
            errors.append(f'不支持的文件格式: {self.file_path.suffix}')
            return False, errors
        
        from models import ImportRecord
        try:
            self._prepare_legacy_import_context()
        except ValueError as exc:
            errors.append(str(exc))
            return False, errors
        # 检查是否重复导入（允许覆盖，仅警告）
        if ImportRecord.is_imported(self.class_id, self.file_hash):
            self.warnings.append(f'文件已导入过: {self.filename}，将覆盖原有数据')
        
        try:
            self.df = self._read_file()
        except Exception as e:
            errors.append(f'文件读取失败: {str(e)}')
            return False, errors
        
        self.errors = errors
        return True, errors
    
    def _read_file(self) -> pd.DataFrame:
        """
        读取知识图谱明细表
        优先查找包含"数据结构"或"知识图谱"的sheet
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
            if '数据结构' in sheet_name or '知识图谱' in sheet_name or '知识' in sheet_name:
                target_sheet = sheet_name
                break
        
        if not target_sheet:
            target_sheet = sheet_names[0] if sheet_names else None
        
        if target_sheet:
            return read_excel_smart(self.file_path, sheet_name=target_sheet, header=None)
        return read_excel_smart(self.file_path, header=None)
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析知识点宽表数据
        """
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 第一行是知识点名称，第二行是指标名称
        knowledge_row = self.df.iloc[0].tolist()
        metric_row = self.df.iloc[1].tolist()
        
        # 解析知识点列结构（每个知识点占3列：完成率、正确率、掌握率）
        knowledge_columns = []
        i = 2
        while i < len(knowledge_row):
            kp_name = knowledge_row[i]
            if pd.notna(kp_name) and str(kp_name).strip() and 'Unnamed' not in str(kp_name):
                kp_name = str(kp_name).strip()
                # 跳过非知识点列
                if kp_name not in ['完成率', '自测习题正确率', '掌握率', '']:
                    knowledge_columns.append({
                        'name': kp_name,
                        'completion_col': i,
                        'correct_col': i + 1 if i + 1 < len(metric_row) else None,
                        'mastery_col': i + 2 if i + 2 < len(metric_row) else None,
                    })
                    i += 3
                    continue
            i += 1
        
        # 从第三行开始是学生数据
        data_rows = self.df.iloc[2:].copy()
        data_rows = data_rows.dropna(how='all')
        
        for idx, row in data_rows.iterrows():
            try:
                student_no = clean_student_no(row.iloc[0])
                name = clean_name(row.iloc[1])
                
                if not student_no:
                    continue
                
                # 遍历所有知识点
                for kp in knowledge_columns:
                    mastery_rate = None
                    completion_rate = None
                    correct_rate = None
                    
                    if kp['mastery_col'] is not None:
                        mastery_rate = extract_rate(row.iloc[kp['mastery_col']], None)
                    if kp['completion_col'] is not None:
                        completion_rate = extract_rate(row.iloc[kp['completion_col']], None)
                    if kp['correct_col'] is not None:
                        correct_rate = extract_rate(row.iloc[kp['correct_col']], None)
                    
                    # 掌握率缺失不能按 0 处理，否则会把未评估知识点误算成低掌握。
                    if mastery_rate is None:
                        continue
                    
                    knowledge_data = {
                        'student_no': student_no,
                        'name': name,
                        'knowledge_name': kp['name'],
                        'mastery_rate': mastery_rate,
                        'completion_rate': completion_rate,
                        'correct_rate': correct_rate,
                        'source': '雨课堂-知识图谱明细'
                    }
                    
                    self.parsed_data.append(knowledge_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        保存知识点明细数据到数据库
        """
        success_count = 0
        
        # 获取或创建班级
        class_id = self._get_or_create_class()

        # 重新导入时先清掉旧的明细记录，避免历史版本把缺失掌握率按 0 保存后继续参与统计。
        old_query = StudentKnowledgeMastery.query.filter(
            StudentKnowledgeMastery.source == '雨课堂-知识图谱明细'
        )
        if class_id:
            student_ids = db.session.query(Student.id).filter(Student.class_id == class_id)
            old_query = old_query.filter(StudentKnowledgeMastery.student_id.in_(student_ids))
        old_query.delete(synchronize_session=False)
        
        for data in self.parsed_data:
            try:
                student = Student.find_by_student_no_flex(data['student_no'])
                if not student:
                    student = Student(
                        student_no=data['student_no'],
                        name=data['name'],
                        class_id=class_id
                    )
                    student.save()
                else:
                    if class_id and not student.class_id:
                        student.class_id = class_id
                
                mastery = StudentKnowledgeMastery.get_student_knowledge(
                    student.id, data['knowledge_name']
                )
                
                if not mastery:
                    mastery = StudentKnowledgeMastery(
                        student_id=student.id,
                        knowledge_name=data['knowledge_name'],
                        source=data['source']
                    )
                
                mastery.mastery_rate = data['mastery_rate']
                mastery.completion_rate = data['completion_rate']
                mastery.correct_rate = data['correct_rate']
                mastery.mastery_level = StudentKnowledgeMastery.calculate_mastery_level(
                    data['mastery_rate']
                )
                mastery.source = data['source']
                
                db.session.add(mastery)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存知识点数据失败: {str(e)}')
        
        db.session.commit()
        return success_count


class RainClassKnowledgePointSummaryImporter(BaseImporter):
    """
    雨课堂按知识点汇总导入器。

    文件粒度为知识点，不包含学生，因此写入独立的知识点汇总表。
    """

    @property
    def import_type(self) -> str:
        return '雨课堂-知识点汇总'

    def get_expected_columns(self) -> List[str]:
        return ['知识点', '掌握率']

    def _read_file(self) -> pd.DataFrame:
        xls = None
        for eng in ['openpyxl', 'xlrd']:
            try:
                xls = pd.ExcelFile(self.file_path, engine=eng)
                break
            except Exception:
                continue
        if xls is None:
            raise ValueError(f'无法读取文件: {self.file_path}')

        target_sheet = None
        for sheet_name in xls.sheet_names:
            if '数据结构' in sheet_name or '知识' in sheet_name:
                target_sheet = sheet_name
                break

        target_sheet = target_sheet or (xls.sheet_names[0] if xls.sheet_names else None)
        if target_sheet:
            return read_excel_smart(self.file_path, sheet_name=target_sheet)
        return read_excel_smart(self.file_path)

    def parse(self) -> Tuple[bool, List[str]]:
        errors = []
        self.parsed_data = []

        if self.df is None:
            return False, ['数据未加载']

        df = self.df.dropna(how='all').copy()

        for idx, row in df.iterrows():
            try:
                knowledge_name = row.get('知识点')
                if pd.isna(knowledge_name) or not str(knowledge_name).strip():
                    continue

                content_status = self._safe_text(row.get('完成情况（未开始/进行中/已完成）')) or ''
                content_counts = self._parse_counts(content_status, 3)
                quiz_status = self._safe_text(row.get('作答情况（未作答/已作答）')) or ''
                quiz_counts = self._parse_counts(quiz_status, 2)

                self.parsed_data.append({
                    'knowledge_name': str(knowledge_name).strip(),
                    'mastery_rate': extract_rate(row.get('掌握率', 0)),
                    'published_contents': self._safe_text(row.get('发布学习内容')),
                    'content_status': content_status,
                    'content_not_started_count': content_counts[0],
                    'content_in_progress_count': content_counts[1],
                    'content_completed_count': content_counts[2],
                    'content_completion_rate': extract_rate(row.get('完成率', 0)),
                    'quiz_count': safe_int(row.get('自测习题', 0)),
                    'quiz_status': quiz_status,
                    'quiz_unanswered_count': quiz_counts[0],
                    'quiz_answered_count': quiz_counts[1],
                    'quiz_completion_rate': extract_rate(row.get('完成率.1', 0)),
                    'quiz_correct_rate': extract_rate(row.get('正确率', 0)),
                })

            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')

        self.errors = errors
        return len(self.parsed_data) > 0, errors

    def _save_to_db(self) -> int:
        success_count = 0
        class_id = self._get_or_create_class()

        old_query = KnowledgePointSummary.query.filter_by(source_file=self.filename)
        old_query.delete(synchronize_session=False)

        for data in self.parsed_data:
            try:
                summary = KnowledgePointSummary(
                    class_id=class_id,
                    source_file=self.filename,
                    source='雨课堂-知识点汇总',
                    **data
                )
                db.session.add(summary)
                success_count += 1
            except Exception as e:
                self.errors.append(f'保存知识点{data.get("knowledge_name", "未知")}失败: {str(e)}')

        db.session.commit()
        return success_count

    @staticmethod
    def _parse_counts(value, expected_count: int) -> List[int]:
        parts = str(value or '').replace('／', '/').split('/')
        counts = []
        for part in parts[:expected_count]:
            counts.append(safe_int(part.strip(), 0))
        while len(counts) < expected_count:
            counts.append(0)
        return counts

    @staticmethod
    def _safe_text(value):
        if pd.isna(value):
            return None
        text = str(value).strip()
        return text or None


class RainClassImporter(BaseImporter):
    """
    雨课堂学习过程数据导入器
    
    支持导入：
    - 雨课堂学习过程数据（多行表头结构）
    """
    
    def _read_file(self) -> pd.DataFrame:
        """
        读取Excel文件并处理多行表头
        
        雨课堂文件可能包含多个sheet，需要智能识别并读取正确的sheet
        学习过程数据通常包含学生个体数据
        
        Returns:
            DataFrame对象（已处理列名）
        """
        # 获取所有sheet名称
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
        
        # 优先查找包含"学习过程数据"的sheet
        target_sheet = None
        for sheet_name in sheet_names:
            if '学习过程数据' in sheet_name:
                target_sheet = sheet_name
                break
        
        # 如果没有找到学习过程数据，尝试查找包含"雨课堂"或"班级"的sheet
        if not target_sheet:
            for sheet_name in sheet_names:
                if '雨课堂' in sheet_name or '班级' in sheet_name or '数据' in sheet_name:
                    target_sheet = sheet_name
                    break
        
        # 如果都没找到，使用第一个sheet
        if not target_sheet:
            target_sheet = sheet_names[0] if sheet_names else None
        
        if target_sheet:
            df = read_excel_smart(self.file_path, sheet_name=target_sheet, header=None)
        else:
            df = read_excel_smart(self.file_path)
        
        # 处理多行表头结构
        df = self._process_multirow_header(df)
        
        return df
    
    def _process_multirow_header(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理多行表头结构
        
        Args:
            df: 原始DataFrame（header=None）
            
        Returns:
            处理后的DataFrame（带有正确的列名）
        """
        def _make_unique_columns(columns):
            """确保列名唯一，重复的添加序号后缀"""
            seen = {}
            result = []
            for c in columns:
                c_str = str(c).strip()
                if c_str in seen:
                    seen[c_str] += 1
                    result.append(f'{c_str}_{seen[c_str]}')
                else:
                    seen[c_str] = 0
                    result.append(c_str)
            return result
        
        # 查找包含'学号'的行作为主表头行
        header_row_idx = None
        for idx in range(min(5, len(df))):
            row_values = df.iloc[idx].astype(str).tolist()
            if '学号' in row_values:
                header_row_idx = idx
                break
        
        # 如果找到表头行，重新构建DataFrame
        if header_row_idx is not None:
            # 检查下一行是否有子表头
            sub_header_idx = header_row_idx + 1
            has_sub_header = False
            if sub_header_idx < len(df):
                sub_row_values = [str(v) for v in df.iloc[sub_header_idx].tolist()]
                key_fields = ['到课率', '视频完成率', '作答率', '得分率', '课件观看率']
                has_sub_header = any(field in '|'.join(sub_row_values) for field in key_fields)
            
            if has_sub_header:
                columns = df.iloc[sub_header_idx].tolist()
                cleaned_columns = []
                for i, col in enumerate(columns):
                    if pd.isna(col) or str(col).strip() == '' or 'Unnamed' in str(col) or 'nan' in str(col).lower():
                        main_col = df.iloc[header_row_idx, i]
                        if pd.notna(main_col) and str(main_col).strip():
                            cleaned_columns.append(str(main_col).strip())
                        else:
                            cleaned_columns.append(f'col_{i}')
                    else:
                        cleaned_columns.append(str(col).strip())
                
                data_start_idx = sub_header_idx + 1
                data_rows = df.iloc[data_start_idx:].copy()
                data_rows.columns = _make_unique_columns(cleaned_columns)
                data_rows = data_rows.dropna(how='all')
                
                if '学号' not in cleaned_columns and len(data_rows.columns) > 2:
                    main_columns = df.iloc[header_row_idx].tolist()
                    for i, col in enumerate(main_columns):
                        if col == '学号' and i < len(cleaned_columns):
                            cleaned_columns[i] = '学号'
                        elif col == '姓名' and i < len(cleaned_columns):
                            cleaned_columns[i] = '姓名'
                    data_rows.columns = _make_unique_columns(cleaned_columns)
                
                data_rows = auto_map_columns(data_rows)
                return data_rows
            else:
                columns = df.iloc[header_row_idx].tolist()
                cleaned_columns = []
                for i, col in enumerate(columns):
                    if pd.isna(col) or str(col).strip() == '' or 'Unnamed' in str(col):
                        cleaned_columns.append(f'col_{i}')
                    else:
                        cleaned_columns.append(str(col).strip())
                
                data_rows = df.iloc[header_row_idx + 1:].copy()
                data_rows.columns = _make_unique_columns(cleaned_columns)
                data_rows = data_rows.dropna(how='all')
                
                data_rows = auto_map_columns(data_rows)
                return data_rows
        else:
            if len(df.columns) > 2:
                df = df.rename(columns={
                    df.columns[1]: '姓名',
                    df.columns[2]: '学号',
                })
                df = auto_map_columns(df)
            return df
    
    @property
    def import_type(self) -> str:
        return '雨课堂'
    
    def get_expected_columns(self) -> List[str]:
        """
        获取期望的列名
        
        雨课堂文件通常包含学号和姓名
        """
        return ['学号', '姓名']
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析雨课堂数据
        
        解析学生的行为数据，包括到课率、视频完成率等
        注意：表头处理已在_read_file中完成
        """
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 获取所有列名，检测重复列
        df_columns_list = self.df.columns.tolist()
        df_columns = set(df_columns_list)
        if len(df_columns) != len(df_columns_list):
            dupes = [c for c in df_columns_list if df_columns_list.count(c) > 1]
            dupes = list(dict.fromkeys(dupes))
            self.warnings.append(f'检测到重复列名: {", ".join(dupes)}，已自动处理')
        
        # 安全获取标量值
        def get_scalar(col, default=0):
            if col in df_columns:
                val = row[col]
                if hasattr(val, '__len__') and not isinstance(val, str):
                    return default
                return val
            return default
        
        # 解析数据（表头已在_read_file中处理，列名已自动映射）
        for idx, row in self.df.iterrows():
            try:
                # 提取学号和姓名（使用 get_scalar 避免重复列名导致返回Series）
                student_no = clean_student_no(get_scalar('学号', None))
                name = clean_name(get_scalar('姓名', None))
                
                if not student_no:
                    self.warnings.append(f'第{idx+1}行: 学号为空，跳过')
                    continue
                
                behavior_data = {
                    'student_no': student_no,
                    'name': name,
                    'attendance_rate': extract_rate(get_scalar('到课率')),
                    'ppt_view_rate': extract_rate(get_scalar('课件观看率')),
                    'video_finish_rate': extract_rate(get_scalar('视频完成率')),
                    'exercise_submit_rate': extract_rate(get_scalar('作答率')),
                    'exercise_score_rate': extract_rate(get_scalar('得分率')),
                    'discussion_count': safe_int(get_scalar('学生发帖数')),
                    'reply_count': safe_int(get_scalar('学生回帖数')),
                }
                
                self.parsed_data.append(behavior_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        保存数据到数据库
        
        Returns:
            成功保存的记录数
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
                        name=data['name'],
                        class_id=class_id
                    )
                    student.save()
                else:
                    # 更新姓名（如果不同）
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                    
                    # 关联班级（如果学生还没有班级）
                    if class_id and not student.class_id:
                        student.class_id = class_id
                
                # 更新或创建行为数据
                behavior = StudentBehavior.get_by_student_id(student.id)
                if not behavior:
                    behavior = StudentBehavior(student_id=student.id)
                
                behavior.attendance_rate = data['attendance_rate']
                behavior.ppt_view_rate = data['ppt_view_rate']
                behavior.video_finish_rate = data['video_finish_rate']
                behavior.exercise_submit_rate = data['exercise_submit_rate']
                behavior.exercise_score_rate = data['exercise_score_rate']
                behavior.discussion_count = data['discussion_count']
                behavior.reply_count = data['reply_count']
                
                # 计算综合评分
                behavior.behavior_score = behavior.calculate_behavior_score()
                behavior.attendance_level = StudentKnowledgeMastery.calculate_mastery_level(
                    behavior.attendance_rate
                )
                
                db.session.add(behavior)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存学生{data.get("student_no", "未知")}失败: {str(e)}')
        
        db.session.commit()
        return success_count


class RainClassKnowledgeImporter(BaseImporter):
    """
    雨课堂知识点数据导入器（长表格式）
    
    负责导入学生的知识点掌握情况（长表格式，每行一个知识点）
    """
    
    @property
    def import_type(self) -> str:
        return '雨课堂-知识图谱'
    
    def get_expected_columns(self) -> List[str]:
        return ['学号', '姓名', '知识点']
    
    def parse(self) -> Tuple[bool, List[str]]:
        """
        解析知识点掌握数据
        """
        errors = []
        self.parsed_data = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        for idx, row in self.df.iterrows():
            try:
                student_no = clean_student_no(row.get('学号'))
                name = clean_name(row.get('姓名'))
                knowledge_name = row.get('知识点', row.get('知识节点', ''))
                
                if not student_no:
                    continue
                
                if pd.isna(knowledge_name) or not str(knowledge_name).strip():
                    continue
                
                knowledge_data = {
                    'student_no': student_no,
                    'name': name,
                    'knowledge_name': str(knowledge_name).strip(),
                    'mastery_rate': extract_rate(row.get('掌握率', row.get('正确率', 0))),
                    'source': '雨课堂'
                }
                
                self.parsed_data.append(knowledge_data)
                
            except Exception as e:
                errors.append(f'第{idx+1}行解析错误: {str(e)}')
        
        self.errors = errors
        return len(self.parsed_data) > 0, errors
    
    def _save_to_db(self) -> int:
        """
        保存知识点数据到数据库
        """
        from models import StudentKnowledgeMastery
        
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
                        name=data['name'],
                        class_id=class_id
                    )
                    student.save()
                else:
                    if data['name'] and student.name != data['name']:
                        student.name = data['name']
                    if class_id and not student.class_id:
                        student.class_id = class_id
                
                # 更新或创建知识点掌握记录
                mastery = StudentKnowledgeMastery.get_student_knowledge(
                    student.id, data['knowledge_name']
                )
                
                if not mastery:
                    mastery = StudentKnowledgeMastery(
                        student_id=student.id,
                        knowledge_name=data['knowledge_name'],
                        source=data['source']
                    )
                
                mastery.mastery_rate = data['mastery_rate']
                mastery.completion_rate = None
                mastery.correct_rate = None
                mastery.mastery_level = StudentKnowledgeMastery.calculate_mastery_level(
                    data['mastery_rate']
                )
                mastery.source = data['source']
                
                db.session.add(mastery)
                success_count += 1
                
            except Exception as e:
                self.errors.append(f'保存知识点数据失败: {str(e)}')
        
        db.session.commit()
        return success_count
