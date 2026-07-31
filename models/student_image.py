# -*- coding: utf-8 -*-
"""Student portrait metadata model."""
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from .base import BaseModel


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

    student = relationship('Student', back_populates='image')

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
