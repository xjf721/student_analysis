"""Class-scoped data access for student portrait images."""
from typing import Optional

from sqlalchemy import or_

from models import Student, StudentImage


class StudentImageRepository:
    """Queries image records without allowing cross-class access."""

    @staticmethod
    def get_by_id(image_id: int, class_id: int) -> Optional[StudentImage]:
        """Return an image only when it belongs to the requested class."""
        return StudentImage.query.filter_by(id=image_id, class_id=class_id).first()

    @staticmethod
    def get_for_student(student_id: int, class_id: int) -> Optional[StudentImage]:
        """Return a student's image only within the requested class."""
        return StudentImage.query.filter_by(student_id=student_id, class_id=class_id).first()

    @staticmethod
    def find_duplicate(class_id: int, content_hash: str) -> Optional[StudentImage]:
        """Find an identical image hash within one class."""
        return StudentImage.query.filter_by(class_id=class_id, content_hash=content_hash).first()

    @staticmethod
    def list_page(
        class_id: int,
        status: Optional[str],
        keyword: str,
        page: int,
        per_page: int,
    ):
        """Return a bounded, searchable page of images from one class."""
        query = StudentImage.query.outerjoin(Student).filter(StudentImage.class_id == class_id)
        if status is not None:
            query = query.filter(StudentImage.match_status == status)

        normalized_keyword = (keyword or '').strip()
        if normalized_keyword:
            escaped_keyword = (
                normalized_keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            )
            pattern = f'%{escaped_keyword}%'
            query = query.filter(or_(
                StudentImage.original_filename.like(pattern, escape='\\'),
                StudentImage.parsed_name.like(pattern, escape='\\'),
                StudentImage.parsed_student_no.like(pattern, escape='\\'),
                Student.name.like(pattern, escape='\\'),
                Student.student_no.like(pattern, escape='\\'),
            ))

        return query.order_by(StudentImage.created_at.desc(), StudentImage.id.desc()).paginate(
            page=max(page, 1), per_page=min(max(per_page, 1), 100), error_out=False
        )
