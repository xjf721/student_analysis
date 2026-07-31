"""Deterministic parsing and class-scoped matching for student images."""

from io import BytesIO
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from typing import BinaryIO, Optional, Sequence
from uuid import uuid4
import zipfile

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import false
from sqlalchemy.sql.elements import ColumnElement

from models import Student, StudentImage, db
from repositories import StudentImageRepository
from werkzeug.datastructures import FileStorage


SUFFIX_PATTERN = re.compile(r'^(?P<number>\d{2})-(?P<name>.+)$')
FULL_PATTERN = re.compile(r'^(?P<number>\d{3,})(?P<name>[^\d].*)$')


class ImageProcessingError(ValueError):
    """A user-correctable image processing failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
    def _read_source(filename: str, stream: BinaryIO) -> bytes:
        """Read and validate one bounded source image into memory."""
        extension = Path(filename or '').suffix.lower().lstrip('.')
        allowed = current_app.config['STUDENT_IMAGE_ALLOWED_EXTENSIONS']
        if extension not in allowed:
            raise ImageProcessingError('unsupported_extension', '不支持的图片格式')

        maximum = int(current_app.config['STUDENT_IMAGE_MAX_FILE_SIZE'])
        source = stream.read(maximum + 1)
        if len(source) > maximum:
            raise ImageProcessingError('file_too_large', '单张图片不能超过 5 MB')
        if not source:
            raise ImageProcessingError('invalid_image', '图片文件为空')

        try:
            with Image.open(BytesIO(source)) as candidate:
                candidate.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
            raise ImageProcessingError('invalid_image', '文件不是有效图片') from error
        return source

    @staticmethod
    def _storage_paths(class_id: int) -> tuple[Path, Path, str]:
        """Create safe generated temporary and final paths below the image root."""
        root = Path(current_app.config['STUDENT_IMAGE_FOLDER']).resolve()
        class_directory = (root / str(class_id)).resolve()
        try:
            class_directory.relative_to(root)
        except ValueError as error:
            raise ImageProcessingError('unsafe_path', '图片存储路径越界') from error
        class_directory.mkdir(parents=True, exist_ok=True)

        storage_filename = f'{uuid4().hex}.jpg'
        final_path = (class_directory / storage_filename).resolve()
        temporary_path = final_path.with_name(f'{final_path.name}.tmp')
        try:
            final_path.relative_to(root)
            temporary_path.relative_to(root)
        except ValueError as error:
            raise ImageProcessingError('unsafe_path', '图片存储路径越界') from error
        return temporary_path, final_path, storage_filename

    @staticmethod
    def _normalize_to_temporary(source: bytes, temporary_path: Path) -> int:
        """Normalize verified source bytes into a bounded RGB JPEG temporary file."""
        try:
            with Image.open(BytesIO(source)) as opened:
                normalized = ImageOps.exif_transpose(opened).convert('RGB')
                normalized.thumbnail((1024, 1024))
                normalized.save(temporary_path, format='JPEG', quality=85)
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
            temporary_path.unlink(missing_ok=True)
            raise ImageProcessingError('invalid_image', '图片无法完成标准化') from error
        return temporary_path.stat().st_size

    @staticmethod
    def get_storage_path(image: StudentImage) -> Path:
        """Resolve a model's generated storage path without allowing root escape."""
        root = Path(current_app.config['STUDENT_IMAGE_FOLDER']).resolve()
        storage_path = (root / str(image.class_id) / image.storage_filename).resolve()
        try:
            storage_path.relative_to(root)
        except ValueError as error:
            raise ImageProcessingError('unsafe_path', '图片存储路径越界') from error
        return storage_path

    @classmethod
    def process_upload(
        cls,
        class_id: int,
        file: FileStorage,
        preferred_student_id: Optional[int] = None,
    ) -> dict:
        """Validate, normalize, match, and atomically persist one uploaded image."""
        original_filename = file.filename or ''
        if not original_filename or len(original_filename) > 255:
            raise ImageProcessingError('invalid_filename', '图片文件名无效')
        preferred_student: Optional[Student] = None
        if preferred_student_id is not None:
            preferred_student = Student.query.filter_by(
                id=preferred_student_id, class_id=class_id
            ).first()
            if preferred_student is None:
                raise ImageProcessingError(
                    'student_not_found', '当前班级中不存在该学生'
                )
        source = cls._read_source(original_filename, file.stream)
        content_hash = hashlib.sha256(source).hexdigest()
        duplicate = StudentImageRepository.find_duplicate(class_id, content_hash)
        if duplicate is not None:
            return {
                'success': True,
                'status': 'duplicate',
                'filename': original_filename,
                'image': duplicate.to_dict(),
            }

        parsed = cls.parse_filename(original_filename)
        if preferred_student is None:
            match = cls.match_student(class_id, parsed)
        else:
            match = ImageMatchResult(
                'matched', preferred_student, '已按指定学生关联'
            )

        temporary_path, final_path, storage_filename = cls._storage_paths(class_id)
        normalized_size = cls._normalize_to_temporary(source, temporary_path)
        old_path: Optional[Path] = None
        image: Optional[StudentImage] = None
        try:
            if match.student is not None:
                image = StudentImageRepository.get_for_student(match.student.id, class_id)
            if image is None:
                image = StudentImage(class_id=class_id)
                db.session.add(image)
            else:
                old_path = cls.get_storage_path(image)

            image.student_id = match.student.id if match.student is not None else None
            image.original_filename = original_filename
            image.storage_filename = storage_filename
            image.parsed_student_no = parsed.student_no
            image.number_match_type = parsed.number_match_type
            image.parsed_name = parsed.name
            image.match_status = match.status
            image.match_message = match.message
            image.mime_type = 'image/jpeg'
            image.file_size = normalized_size
            image.content_hash = content_hash
            db.session.flush()
            os.replace(temporary_path, final_path)
            db.session.commit()
        except Exception:
            db.session.rollback()
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise

        if old_path is not None and old_path != final_path:
            old_path.unlink(missing_ok=True)
        return {
            'success': True,
            'status': image.match_status,
            'filename': original_filename,
            'image': image.to_dict(),
        }

    @staticmethod
    def _validate_zip_entry(info: zipfile.ZipInfo) -> None:
        """Reject unsafe, nested, linked, or unsupported archive members."""
        normalized_name = info.filename.replace('\\', '/')
        member_path = PurePosixPath(normalized_name)
        if (
            member_path.is_absolute()
            or '..' in member_path.parts
            or (member_path.parts and ':' in member_path.parts[0])
        ):
            raise ImageProcessingError('unsafe_zip_entry', 'ZIP 中包含不安全路径')
        unix_mode = info.external_attr >> 16
        if (unix_mode & 0o170000) == 0o120000:
            raise ImageProcessingError('unsafe_zip_entry', 'ZIP 中不允许符号链接')
        extension = member_path.suffix.lower().lstrip('.')
        if extension == 'zip':
            raise ImageProcessingError('nested_zip', '不允许嵌套 ZIP 文件')
        if extension not in current_app.config['STUDENT_IMAGE_ALLOWED_EXTENSIONS']:
            raise ImageProcessingError('unsupported_extension', 'ZIP 中包含不支持的文件')

    @classmethod
    def _collect_batch_entries(
        cls,
        files: Sequence[FileStorage],
    ) -> list[tuple[str, bytes]]:
        """Preflight and materialize a bounded stream of regular and ZIP entries."""
        maximum_files = int(current_app.config['STUDENT_IMAGE_MAX_BATCH_FILES'])
        expanded_limit = int(current_app.config['MAX_CONTENT_LENGTH'])
        source_limit = int(current_app.config['STUDENT_IMAGE_MAX_FILE_SIZE'])
        if len(files) > maximum_files:
            raise ImageProcessingError('too_many_files', '单批图片数量不能超过 200 张')

        entries: list[tuple[str, bytes]] = []
        expanded_size = 0
        for upload in files:
            display_filename = upload.filename or ''
            if Path(display_filename).suffix.lower() != '.zip':
                content = upload.stream.read(source_limit + 1)
                entries.append((display_filename, content))
                expanded_size += len(content)
            else:
                archive_bytes = upload.stream.read(expanded_limit + 1)
                if len(archive_bytes) > expanded_limit:
                    raise ImageProcessingError('batch_too_large', '批量上传内容超过上限')
                try:
                    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
                        members = [info for info in archive.infolist() if not info.is_dir()]
                        for info in members:
                            cls._validate_zip_entry(info)
                            entries.append((info.filename, b''))
                            expanded_size += info.file_size
                            if len(entries) > maximum_files:
                                raise ImageProcessingError(
                                    'too_many_files', '单批图片数量不能超过 200 张'
                                )
                            if expanded_size > expanded_limit:
                                raise ImageProcessingError(
                                    'batch_too_large', '批量上传展开内容超过上限'
                                )

                        first_index = len(entries) - len(members)
                        for offset, info in enumerate(members):
                            try:
                                with archive.open(info) as member_stream:
                                    content = member_stream.read(source_limit + 1)
                            except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                                raise ImageProcessingError(
                                    'invalid_zip', 'ZIP 条目无法安全读取'
                                ) from error
                            entries[first_index + offset] = (info.filename, content)
                except zipfile.BadZipFile as error:
                    raise ImageProcessingError('invalid_zip', '文件不是有效 ZIP') from error

            if len(entries) > maximum_files:
                raise ImageProcessingError('too_many_files', '单批图片数量不能超过 200 张')
            if expanded_size > expanded_limit:
                raise ImageProcessingError('batch_too_large', '批量上传展开内容超过上限')
        return entries

    @classmethod
    def process_batch(cls, class_id: int, files: Sequence[FileStorage]) -> dict:
        """Preflight a batch, then process each image as an independent transaction."""
        entries = cls._collect_batch_entries(files)
        counts = {
            'matched': 0,
            'pending': 0,
            'conflict': 0,
            'duplicate': 0,
            'failed': 0,
        }
        results: list[dict] = []
        for display_filename, content in entries:
            try:
                result = cls.process_upload(
                    class_id,
                    FileStorage(stream=BytesIO(content), filename=display_filename),
                )
                counts[result['status']] += 1
            except ImageProcessingError as error:
                counts['failed'] += 1
                result = {
                    'success': False,
                    'status': 'failed',
                    'filename': display_filename,
                    'error': {'code': error.code, 'message': error.message},
                }
            results.append(result)

        return {
            'success': counts['failed'] == 0,
            'total_files': len(entries),
            'matched_count': counts['matched'],
            'pending_count': counts['pending'],
            'conflict_count': counts['conflict'],
            'duplicate_count': counts['duplicate'],
            'failed_count': counts['failed'],
            'results': results,
        }

    @classmethod
    def bind_image(
        cls,
        class_id: int,
        image_id: int,
        student_id: int,
        confirm_replace: bool = False,
    ) -> dict:
        """Bind or rebind one class-scoped image, requiring destructive confirmation."""
        image = StudentImageRepository.get_by_id(image_id, class_id)
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if image is None or student is None:
            raise ImageProcessingError('not_found', '当前班级中不存在该图片或学生')

        target = StudentImageRepository.get_for_student(student_id, class_id)
        source_is_reassigned = image.student_id not in (None, student_id)
        target_is_replaced = target is not None and target.id != image.id
        if (source_is_reassigned or target_is_replaced) and not confirm_replace:
            raise ImageProcessingError(
                'binding_conflict', '绑定将改绑或替换现有头像，需要确认'
            )

        displaced_path: Optional[Path] = None
        try:
            if target_is_replaced:
                displaced_path = cls.get_storage_path(target)
                db.session.delete(target)
                db.session.flush()
            image.student_id = student_id
            image.match_status = 'matched'
            image.match_message = '已手动关联'
            db.session.flush()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        if displaced_path is not None:
            displaced_path.unlink(missing_ok=True)
        return image.to_dict()

    @classmethod
    def delete_image(cls, class_id: int, image_id: int) -> bool:
        """Delete one class-scoped image row, then remove its protected media file."""
        image = StudentImageRepository.get_by_id(image_id, class_id)
        if image is None:
            return False
        storage_path = cls.get_storage_path(image)
        try:
            db.session.delete(image)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        storage_path.unlink(missing_ok=True)
        return True

    @classmethod
    def rematch_pending(cls, class_id: int) -> dict:
        """Re-run deterministic matching only for unresolved images in one class."""
        images = StudentImage.query.filter(
            StudentImage.class_id == class_id,
            StudentImage.match_status.in_(('pending', 'conflict')),
        ).all()
        matched_count = 0
        try:
            for image in images:
                parsed = ParsedStudentImage(
                    image.parsed_student_no,
                    image.number_match_type,
                    image.parsed_name,
                )
                match = cls.match_student(class_id, parsed)
                if match.student is not None:
                    existing = StudentImageRepository.get_for_student(
                        match.student.id, class_id
                    )
                    if existing is not None and existing.id != image.id:
                        image.student_id = None
                        image.match_status = 'conflict'
                        image.match_message = '匹配学生已有头像'
                        continue
                    image.student_id = match.student.id
                    image.match_status = 'matched'
                    image.match_message = match.message
                    matched_count += 1
                else:
                    image.student_id = None
                    image.match_status = match.status
                    image.match_message = match.message
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        checked_count = len(images)
        return {
            'checked_count': checked_count,
            'matched_count': matched_count,
            'remaining_count': checked_count - matched_count,
        }

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
