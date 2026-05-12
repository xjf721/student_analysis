# -*- coding: utf-8 -*-
"""
解析工具函数

提供数据导入过程中的通用解析功能。
"""
from typing import Any, Optional, Dict, List
import pandas as pd
import re
import json
from pathlib import Path


# 加载列名映射配置
_column_mapping_cache = None


def _get_config_path() -> Path:
    """获取配置文件路径"""
    try:
        # 正常导入时使用__file__
        return Path(__file__).parent.parent.parent / 'config' / 'column_mapping.json'
    except NameError:
        # exec执行时使用当前工作目录
        import os
        return Path(os.getcwd()) / 'config' / 'column_mapping.json'


def _load_column_mapping() -> Dict:
    """加载列名映射配置（带缓存）"""
    global _column_mapping_cache
    if _column_mapping_cache is None:
        try:
            config_path = _get_config_path()
            with open(config_path, 'r', encoding='utf-8') as f:
                _column_mapping_cache = json.load(f)
        except Exception:
            # 如果配置文件不存在，使用默认配置
            _column_mapping_cache = {'column_mappings': {}}
    return _column_mapping_cache


def match_column_name(actual_col: str) -> Optional[str]:
    """
    智能匹配列名到标准名称
    
    支持：
    - 精确匹配标准名称
    - 精确匹配别名
    - 自动去除Excel常见格式后缀（如(%)、(分)、（%）等）
    
    Args:
        actual_col: 实际列名
        
    Returns:
        标准列名，如果无法匹配则返回None
    """
    config = _load_column_mapping()
    mappings = config.get('column_mappings', {})
    
    actual_col_clean = str(actual_col).strip().replace('\n', '')
    
    def _normalize(s):
        s = str(s).strip().replace('\n', '')
        s = re.sub(r'[(（][^)）]*[)）]', '', s).strip()
        s = re.sub(r'[（(]\s*%?\s*[）)]', '', s).strip()
        return s
    
    actual_normalized = _normalize(actual_col_clean)
    
    # 1. 精确匹配标准名称（原始和归一化后）
    for field, mapping in mappings.items():
        canonical = mapping.get('canonical')
        if actual_col_clean == canonical:
            return canonical
        if actual_normalized == canonical:
            return canonical
    
    # 2. 匹配别名（原始和归一化后）
    for field, mapping in mappings.items():
        aliases = mapping.get('aliases', [])
        if actual_col_clean in aliases:
            return mapping['canonical']
        if actual_normalized in aliases:
            return mapping['canonical']
    
    return None


def auto_map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    自动映射DataFrame的列名到标准名称
    
    处理重复映射：如果多个原始列名映射到同一个标准名，
    第一个保留标准名，后续的添加 _序号 后缀避免重复。
    
    Args:
        df: 原始DataFrame
        
    Returns:
        列名已映射的DataFrame
    """
    columns = df.columns.tolist()
    col_mapping = {}
    used_names = set(columns)  # 记录已占用的列名
    
    for col in columns:
        standard_name = match_column_name(col)
        if standard_name:
            # 处理重复映射
            final_name = standard_name
            counter = 1
            while final_name in used_names and final_name != col:
                final_name = f'{standard_name}_{counter}'
                counter += 1
            col_mapping[col] = final_name
            used_names.add(final_name)
    
    if col_mapping:
        return df.rename(columns=col_mapping)
    return df


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    安全转换为浮点数
    
    Args:
        value: 输入值
        default: 默认值
        
    Returns:
        浮点数值
    """
    if pd.isna(value):
        return default
    
    try:
        if isinstance(value, str):
            # 处理百分号
            value = value.replace('%', '').strip()
            return float(value)
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    安全转换为整数
    
    Args:
        value: 输入值
        default: 默认值
        
    Returns:
        整数值
    """
    if pd.isna(value):
        return default
    
    try:
        if isinstance(value, str):
            value = value.strip()
        return int(float(value))
    except (ValueError, TypeError):
        return default


def extract_rate(value: Any, default: float = 0.0) -> float:
    """
    提取比率值（处理百分号和比率格式）
    
    Args:
        value: 输入值（可能是 '95%'、'0.95' 或 95）
        default: 默认值
        
    Returns:
        比率值（0-100）
    """
    if pd.isna(value):
        return default
    
    try:
        if isinstance(value, str):
            value = value.strip()
            if '%' in value:
                # 95% -> 95
                return safe_float(value.replace('%', ''), default)
            else:
                # 可能是 0.95 格式
                num = safe_float(value, default)
                if 0 <= num <= 1:
                    return num * 100
                return num
        else:
            num = float(value)
            if 0 <= num <= 1:
                return num * 100
            return num
    except:
        return default


def clean_student_no(value: Any) -> Optional[str]:
    """
    清洗学号格式
    
    Args:
        value: 学号值
        
    Returns:
        清洗后的学号或None
    """
    if pd.isna(value):
        return None
    
    # 转换为字符串并去除空白
    student_no = str(value).strip()
    
    # 如果是科学计数法，转换为普通数字
    if 'E' in student_no.upper():
        try:
            student_no = str(int(float(student_no)))
        except:
            pass
    
    # 去除前导零（统一格式，防止Excel不同单元格格式导致重复学生）
    student_no = student_no.lstrip('0') or '0'
    
    return student_no if student_no else None


def clean_name(value: Any) -> Optional[str]:
    """
    清洗姓名格式
    
    Args:
        value: 姓名值
        
    Returns:
        清洗后的姓名或None
    """
    if pd.isna(value):
        return None
    
    name = str(value).strip()
    return name if name else None


def extract_class_info_from_filename(filename: str) -> Dict[str, Optional[str]]:
    """
    从文件名中提取班级信息
    
    支持的文件名格式：
    - 2026春-24大数据管理与应用(数据保障)(青年1班)-雨课堂-学生汇总表.xls
    - 2026春-24大数据管理与应用(数据保障)(青年1班)-雨课堂-班级数据统计与学习过程数据.xlsx
    
    Args:
        filename: 文件名
        
    Returns:
        包含班级信息的字典：
        - class_name: 班级名称（如：24大数据管理与应用(数据保障)(青年1班)）
        - term: 学期（如：2026春）
        - teacher_name: 教师姓名（如果文件名中包含）
    """
    result = {
        'class_name': None,
        'term': None,
        'teacher_name': None
    }
    
    # 移除文件扩展名
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    
    # 提取学期（格式如：2026春、2025秋）
    import re
    term_match = re.match(r'(\d{4}[春秋])', name_without_ext)
    if term_match:
        result['term'] = term_match.group(1)
    
    # 提取班级名称（通常在学期之后，平台名称之前）
    # 格式：学期-班级名称-平台-...
    parts = name_without_ext.split('-')
    if len(parts) >= 2:
        # 跳过学期部分，取下一部分作为班级名称
        class_name_parts = []
        for i, part in enumerate(parts):
            if i == 0 and re.match(r'\d{4}[春秋]', part):
                continue  # 跳过学期
            # 检查是否是平台名称
            if any(platform in part for platform in ['雨课堂', '头歌', 'educoder']):
                break
            class_name_parts.append(part)
        
        if class_name_parts:
            result['class_name'] = '-'.join(class_name_parts)
    
    return result


def detect_file_type(df: pd.DataFrame, file_path: str = None) -> Optional[str]:
    """
    自动检测文件类型
    
    通过检查列名特征和文件名判断文件类型
    
    Args:
        df: DataFrame对象
        file_path: 文件路径（可选，用于检查文件名）
        
    Returns:
        文件类型标识或None
    """
    # 首先检查文件名
    if file_path:
        filename = str(file_path).lower()
        if '雨课堂' in filename:
            return '雨课堂'
        if '头歌' in filename or 'educoder' in filename:
            return '头歌'
    
    # 检查列名
    columns = [str(col).lower() for col in df.columns]
    column_str = '|'.join(columns)
    
    # 雨课堂特征列
    rainclass_keywords = ['到课率', '视频', '作答', 'ppt', '雨课堂', '课件', '得分率', '学生汇总']
    if any(kw in column_str for kw in rainclass_keywords):
        return '雨课堂'
    
    # 头歌特征列
    educoder_keywords = ['头歌', 'educoder', '实验', '作业成绩', '活跃度']
    if any(kw in column_str for kw in educoder_keywords):
        return '头歌'
    
    # 检查是否有学号和姓名列（通用学生数据）
    if '学号' in columns and '姓名' in columns:
        return '雨课堂'  # 默认当作雨课堂处理
    
    return None


def calculate_avg(values: list, default: float = 0.0) -> float:
    """
    计算平均值（忽略None和NaN）
    
    Args:
        values: 数值列表
        default: 默认值
        
    Returns:
        平均值
    """
    valid_values = [v for v in values if v is not None and not pd.isna(v)]
    if not valid_values:
        return default
    return sum(valid_values) / len(valid_values)


_UNSET = object()  # 哨兵值，区分"未传header"和"header=None"

def read_excel_smart(file_path, sheet_name=None, header=_UNSET):
    """
    安全读取 Excel 文件，自动处理 .xls 实为 .xlsx 的问题
    
    优先按扩展名选择引擎，失败时自动降级尝试另一个引擎。
    
    Args:
        file_path: 文件路径（字符串或Path对象）
        sheet_name: sheet名称（可选）
        header: 表头行号（None=不指定表头, 0=第一行作为表头, 不传=使用pandas默认0）
        
    Returns:
        DataFrame对象
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    
    # 按扩展名确定主引擎和备用引擎
    if suffix == '.xlsx':
        primary_engine = 'openpyxl'
        fallback_engine = 'xlrd'
    else:
        primary_engine = 'xlrd'
        fallback_engine = 'openpyxl'
    
    kwargs = {}
    if sheet_name is not None:
        kwargs['sheet_name'] = sheet_name
    if header is not _UNSET:
        kwargs['header'] = header
    
    try:
        return pd.read_excel(file_path, engine=primary_engine, **kwargs)
    except Exception:
        try:
            return pd.read_excel(file_path, engine=fallback_engine, **kwargs)
        except Exception:
            raise
