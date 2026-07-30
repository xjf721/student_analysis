from sqlalchemy import func

from models import ClassInfo, ImportRecord, KnowledgePointSummary, Student, db


class ClassRepository:
    @staticmethod
    def get_by_id(class_id: int):
        return db.session.get(ClassInfo, class_id)

    @staticmethod
    def get_all():
        return ClassInfo.query.order_by(ClassInfo.term.desc(), ClassInfo.class_name).all()

    @staticmethod
    def get_active():
        return ClassInfo.query.filter_by(status='active').order_by(ClassInfo.term.desc(), ClassInfo.class_name).all()

    @staticmethod
    def create(data: dict):
        item = ClassInfo(
            class_name=data['class_name'].strip(),
            teacher_name=(data.get('teacher_name') or '').strip() or None,
            term=(data.get('term') or '').strip() or None,
            notes=(data.get('notes') or '').strip() or None,
            status='active',
        )
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    def has_data(class_id: int) -> bool:
        checks = (
            Student.query.filter_by(class_id=class_id).first(),
            ImportRecord.query.filter_by(class_id=class_id).first(),
            KnowledgePointSummary.query.filter_by(class_id=class_id).first(),
        )
        return any(checks)

    @staticmethod
    def delete_empty(item: ClassInfo) -> bool:
        if ClassRepository.has_data(item.id):
            return False
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def get_overview(class_id: int) -> dict:
        return {
            'student_count': Student.query.filter_by(class_id=class_id).count(),
            'import_count': ImportRecord.query.filter_by(class_id=class_id).count(),
            'latest_import_at': db.session.query(func.max(ImportRecord.created_at)).filter(
                ImportRecord.class_id == class_id
            ).scalar(),
        }

    @staticmethod
    def get_recent_imports(class_id: int, limit: int = 10):
        return ImportRecord.query.filter_by(class_id=class_id).order_by(
            ImportRecord.created_at.desc()
        ).limit(limit).all()
