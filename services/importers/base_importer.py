# -*- coding: utf-8 -*-
"""
数据导入器基类

所有数据导入器必须继承此类并实现相应方法。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import hashlib
import pandas as pd

from models import db, ImportRecord
from .parser_utils import extract_class_info_from_filename, read_excel_smart


def calculate_file_hash(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class BaseImporter(ABC):
    """
    数据导入器抽象基类
    
    定义了数据导入的标准流程：
    1. validate() - 数据校验
    2. clean() - 数据清洗
    3. parse() - 数据解析
    4. save() - 数据保存
    """
    
    def __init__(self, file_path: str, class_id: int, uploaded_by: str,
                 display_filename: str = None, file_hash: str = None):
        """
        初始化导入器
        
        Args:
            file_path: 导入文件路径
            class_id: 用户明确选择的目标班级ID
            uploaded_by: 执行导入的管理员用户名
            display_filename: 用于展示的原始文件名（如原始中文文件名），
                              若不提供则使用 file_path 的文件名
            file_hash: 可复用的SHA-256文件摘要
        """
        self.file_path = Path(file_path)
        self.display_filename = display_filename or self.file_path.name
        self.filename = self.display_filename
        self.df: pd.DataFrame = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.parsed_data: List[Dict] = []
        self.import_record: ImportRecord = None
        self.class_id = class_id
        self.file_hash = file_hash or calculate_file_hash(self.file_path)
        self.uploaded_by = uploaded_by
        
        # 文件名中的班级仅供控制器提示冲突，绝不决定数据归属。
        self.detected_class_info = extract_class_info_from_filename(self.display_filename)
        
    @property
    @abstractmethod
    def import_type(self) -> str:
        """
        导入类型标识
        
        Returns:
            导入类型字符串，如 '雨课堂'、'头歌'
        """
        pass
    
    @abstractmethod
    def get_expected_columns(self) -> List[str]:
        """
        获取期望的列名列表
        
        Returns:
            期望的列名列表
        """
        pass
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        数据校验
        
        校验项包括：
        - 文件是否存在
        - 文件格式是否正确
        - 必要字段是否存在
        - 学号是否为空
        - 是否重复导入
        
        Returns:
            (是否通过校验, 错误信息列表)
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
        
        # 检查必要字段
        expected_columns = self.get_expected_columns()
        missing_columns = self._check_missing_columns(expected_columns)
        if missing_columns:
            errors.append(f'缺少必要字段: {", ".join(missing_columns)}')
        
        self.errors = errors
        return len(errors) == 0, errors
    
    def clean(self) -> Tuple[bool, List[str]]:
        """
        数据清洗
        
        清洗项包括：
        - 去除空白行
        - 处理空值
        - 去除重复学生
        - 数据类型转换
        
        Returns:
            (是否清洗成功, 警告信息列表)
        """
        warnings = []
        
        if self.df is None:
            return False, ['数据未加载']
        
        # 去除完全空白的行
        original_count = len(self.df)
        self.df = self.df.dropna(how='all')
        if len(self.df) < original_count:
            warnings.append(f'移除了 {original_count - len(self.df)} 行空白数据')
        
        # 检查学号为空的记录
        if '学号' in self.df.columns:
            null_count = self.df['学号'].isna().sum()
            if null_count > 0:
                self.df = self.df.dropna(subset=['学号'])
                warnings.append(f'移除了 {null_count} 条学号为空的记录')
        
        # 去除重复学号
        if '学号' in self.df.columns:
            duplicate_count = self.df.duplicated(subset=['学号'], keep='first').sum()
            if duplicate_count > 0:
                self.df = self.df.drop_duplicates(subset=['学号'], keep='first')
                warnings.append(f'移除了 {duplicate_count} 条重复学号记录')
        
        self.warnings = warnings
        return True, warnings
    
    @abstractmethod
    def parse(self) -> Tuple[bool, List[str]]:
        """
        数据解析
        
        将DataFrame解析为结构化数据
        
        Returns:
            (是否解析成功, 错误信息列表)
        """
        pass
    
    def save(self) -> Tuple[bool, str]:
        """
        保存数据到数据库
        
        Returns:
            (是否保存成功, 消息)
        """
        if not self.parsed_data:
            self._record_failed_import('没有数据需要保存')
            return False, '没有数据需要保存'
        
        try:
            self._get_target_class_id()

            # 清理旧导入记录（支持重新导入）
            ImportRecord.query.filter_by(
                class_id=self.class_id,
                file_hash=self.file_hash,
            ).delete(synchronize_session=False)
            # 创建新的导入记录
            self.import_record = ImportRecord(
                class_id=self.class_id,
                filename=self.filename,
                file_hash=self.file_hash,
                uploaded_by=self.uploaded_by,
                import_type=self.import_type,
                import_status='进行中'
            )
            db.session.add(self.import_record)
            db.session.flush()
            
            # 调用子类的保存逻辑
            success_count = self._save_to_db()
            
            # 任一行保存失败都回滚整个文件，避免半成功导入。
            if self.errors:
                raise ValueError('; '.join(self.errors))
            
            # 更新导入记录
            if success_count == 0:
                error_detail = '; '.join(self.errors[:3]) if self.errors else '未知原因'
                raise ValueError(f'成功0条, 错误: {error_detail}')

            self.import_record.import_status = '成功'
            self.import_record.success_count = success_count
            db.session.commit()
            
            return True, f'成功导入 {success_count} 条记录'
            
        except Exception as e:
            self._record_failed_import(str(e))
            return False, f'保存失败: {str(e)}'
    
    @abstractmethod
    def _save_to_db(self) -> int:
        """
        保存数据到数据库（子类实现）
        
        Returns:
            成功保存的记录数
        """
        pass
    
    def execute(self) -> Dict[str, Any]:
        """
        执行完整的导入流程
        
        Returns:
            导入结果字典
        """
        result = {
            'success': False,
            'message': '',
            'errors': [],
            'warnings': [],
            'imported_count': 0
        }
        
        # 1. 校验
        valid, errors = self.validate()
        if not valid:
            result['errors'] = errors if errors else ['数据校验失败（无详细错误）']
            result['message'] = '数据校验失败'
            self._record_failed_import('; '.join(result['errors']))
            return result
        
        # 2. 清洗
        cleaned, warnings = self.clean()
        result['warnings'] = warnings
        if not cleaned:
            result['errors'] = warnings if warnings else ['数据清洗失败']
            result['message'] = '数据清洗失败'
            self._record_failed_import('; '.join(result['errors']))
            return result
        
        # 3. 解析
        parsed, parse_errors = self.parse()
        if not parsed:
            result['errors'] = parse_errors if parse_errors else [f'数据解析失败: df有{len(self.df)}行但无有效数据']
            result['message'] = '数据解析失败'
            self._record_failed_import('; '.join(result['errors']))
            return result
        
        # 4. 保存
        saved, message = self.save()
        result['success'] = saved
        result['message'] = message
        if not saved:
            result['errors'] = [message]
        if saved:
            result['imported_count'] = self.import_record.success_count if self.import_record else 0
        
        return result
    
    def _read_file(self) -> pd.DataFrame:
        """
        读取Excel文件
        
        Returns:
            DataFrame对象
        """
        return read_excel_smart(self.file_path)
    
    def _check_missing_columns(self, expected_columns: List[str]) -> List[str]:
        """
        检查缺失的列
        
        Args:
            expected_columns: 期望的列名列表
            
        Returns:
            缺失的列名列表
        """
        actual_columns = self.df.columns.tolist()
        missing = []
        
        for col in expected_columns:
            if col not in actual_columns:
                missing.append(col)
        
        return missing
    
    def _get_target_class_id(self) -> int:
        """校验并返回用户明确选择的活动班级。"""
        from models import ClassInfo

        item = ClassInfo.query.filter_by(id=self.class_id, status='active').first()
        if item is None:
            raise ValueError('目标班级不存在或已归档')
        return item.id

    def _find_target_student(self, student_no: str):
        """查找当前班学生，并拒绝复用其他班级的同号学生。"""
        from models import Student

        student = Student.find_by_student_no_flex(student_no)
        if student is not None and student.class_id != self.class_id:
            raise ValueError(
                f'学号 {student_no} 已属于其他班级，不能导入到当前班级'
            )
        return student

    def _record_failed_import(self, error_message: str) -> None:
        """回滚当前文件的数据变更，再单独持久化失败审计记录。"""
        db.session.rollback()
        self.import_record = ImportRecord(
            class_id=self.class_id,
            filename=self.filename,
            file_hash=self.file_hash,
            uploaded_by=self.uploaded_by,
            import_type=self.import_type,
            import_status='失败',
            error_message=error_message,
        )
        try:
            db.session.add(self.import_record)
            db.session.commit()
        except Exception:
            db.session.rollback()
    
    def _safe_get_value(self, row, column: str, default: Any = 0) -> Any:
        """
        安全获取DataFrame行的值
        
        Args:
            row: DataFrame行
            column: 列名
            default: 默认值
            
        Returns:
            列值或默认值
        """
        try:
            value = row.get(column, default)
            if pd.isna(value):
                return default
            return value
        except:
            return default
