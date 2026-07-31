# -*- coding: utf-8 -*-
"""Student portrait metadata model."""
from sqlalchemy import Column, ForeignKey, Index, Integer, String, and_, event, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, foreign, relationship

from .base import BaseModel
from .student import Student


class StudentImage(BaseModel):
    """Stores a protected portrait image and its class-scoped match state."""

    __tablename__ = 'student_image'
    __table_args__ = (
        Index('ix_student_image_class_status', 'class_id', 'match_status'),
        Index('ix_student_image_class_parsed_name', 'class_id', 'parsed_name'),
        Index('ix_student_image_class_parsed_student_no', 'class_id', 'parsed_student_no'),
        Index('ix_student_image_class_content_hash', 'class_id', 'content_hash'),
    )

    class_id = Column(Integer, ForeignKey('class_info.id'), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=True, unique=True)
    original_filename = Column(String(255), nullable=False)
    storage_filename = Column(String(255), nullable=False, unique=True)
    parsed_student_no = Column(String(50), nullable=True)
    number_match_type = Column(String(20), nullable=True)
    parsed_name = Column(String(100), nullable=True)
    match_status = Column(String(20), nullable=False)
    match_message = Column(String(255), nullable=True)
    mime_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)

    student = relationship(
        'Student',
        primaryjoin=lambda: and_(
            foreign(StudentImage.student_id) == Student.id,
            StudentImage.class_id == Student.class_id,
        ),
        back_populates='image',
    )

    @property
    def media_url(self) -> str:
        """Return the protected media endpoint for this image."""
        return f'/media/student-images/{self.id}'

    def to_dict(self) -> dict:
        """Serialize image metadata for image-library responses."""
        return {
            'id': self.id,
            'class_id': self.class_id,
            'student_id': self.student_id,
            'student_no': self.student.student_no if self.student else None,
            'student_name': self.student.name if self.student else None,
            'original_filename': self.original_filename,
            'parsed_student_no': self.parsed_student_no,
            'number_match_type': self.number_match_type,
            'parsed_name': self.parsed_name,
            'match_status': self.match_status,
            'match_message': self.match_message,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
            'avatar_url': self.media_url,
        }


@event.listens_for(StudentImage, 'before_insert')
@event.listens_for(StudentImage, 'before_update')
def validate_student_class(
    mapper: Mapper,
    connection: Connection,
    target: StudentImage,
) -> None:
    """Reject image bindings that would cross the student's class boundary."""
    if target.student_id is None:
        return

    student_class_id = connection.execute(
        select(Student.class_id).where(Student.id == target.student_id)
    ).scalar_one_or_none()
    if student_class_id != target.class_id:
        raise ValueError('student_id must belong to the same class_id as the image')
