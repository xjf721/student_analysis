"""Deterministic parsing and class-scoped matching for student images."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

from sqlalchemy import false
from sqlalchemy.sql.elements import ColumnElement

from models import Student


SUFFIX_PATTERN = re.compile(r'^(?P<number>\d{2})-(?P<name>.+)$')
FULL_PATTERN = re.compile(r'^(?P<number>\d{3,})(?P<name>[^\d].*)$')


@dataclass(frozen=True)
class ParsedStudentImage:
    """Identity information deterministically extracted from an image filename."""

    student_no: Optional[str]
    number_match_type: Optional[str]
    name: Optional[str]


@dataclass(frozen=True)
class ImageMatchResult:
    """Outcome of attempting to associate an image with one student."""

    status: str
    student: Optional[Student]
    message: str


def _normalize_name(value: str) -> str:
    """Remove filename separators surrounding an otherwise exact name."""
    return value.strip().strip('_- ').strip()


def _student_number_predicate(
    parsed: ParsedStudentImage,
) -> ColumnElement[bool]:
    """Build the exact full-number or SQL suffix predicate for parsed evidence."""
    if parsed.number_match_type == 'suffix':
        return Student.student_no.endswith(parsed.student_no)
    if parsed.number_match_type == 'full':
        return Student.student_no == parsed.student_no
    return false()


def _query_exact_candidates(
    class_id: int,
    parsed: ParsedStudentImage,
) -> list[Student]:
    """Return candidates whose number and normalized filename name both agree."""
    normalized_name = _normalize_name(parsed.name or '')
    return Student.query.filter(
        Student.class_id == class_id,
        _student_number_predicate(parsed),
        Student.name == normalized_name,
    ).all()


def _number_or_name_conflicts(class_id: int, parsed: ParsedStudentImage) -> bool:
    """Detect contradictory number/name evidence within the active class only."""
    normalized_name = _normalize_name(parsed.name or '')
    return Student.query.filter(
        Student.class_id == class_id,
        (
            _student_number_predicate(parsed)
            | (Student.name == normalized_name)
        ),
    ).first() is not None


class StudentImageService:
    """Parse student image filenames and match them within an active class."""

    @staticmethod
    def parse_filename(filename: str) -> ParsedStudentImage:
        """Parse one of the supported, fully anchored filename conventions."""
        stem = Path(filename).stem
        for pattern, match_type in (
            (SUFFIX_PATTERN, 'suffix'),
            (FULL_PATTERN, 'full'),
        ):
            match = pattern.fullmatch(stem)
            if match is None:
                continue
            name = _normalize_name(match.group('name'))
            if name:
                return ParsedStudentImage(match.group('number'), match_type, name)
        return ParsedStudentImage(None, None, None)

    @staticmethod
    def match_student(class_id: int, parsed: ParsedStudentImage) -> ImageMatchResult:
        """Match parsed identity evidence against students in one class."""
        if not parsed.student_no or not parsed.name:
            return ImageMatchResult('pending', None, '文件名无法提取完整匹配信息')

        candidates = _query_exact_candidates(class_id, parsed)
        if len(candidates) == 1:
            return ImageMatchResult('matched', candidates[0], '已自动关联')
        if len(candidates) > 1:
            return ImageMatchResult('conflict', None, '当前班级存在多个候选学生')
        if _number_or_name_conflicts(class_id, parsed):
            return ImageMatchResult('conflict', None, '学号信息与姓名不一致')
        return ImageMatchResult('pending', None, '当前班级尚无匹配学生')
