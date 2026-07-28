# -*- coding: utf-8 -*-
"""知识点名称的自然序号排序工具。"""
import re
from typing import Optional, Tuple


def extract_knowledge_sequence(knowledge_name: str) -> Optional[Tuple[int, ...]]:
    """提取知识点名称开头的层级序号，如 ``1.10.2``。"""
    match = re.match(r'^\s*(\d+(?:\.\d+)*)', knowledge_name or '')
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split('.'))


def knowledge_name_sort_key(knowledge_name: str) -> tuple:
    """生成自然排序键；没有序号的知识点排在有序号知识点之后。"""
    sequence = extract_knowledge_sequence(knowledge_name)
    if sequence is None:
        return (1, (), knowledge_name or '')
    return (0, sequence, knowledge_name or '')
