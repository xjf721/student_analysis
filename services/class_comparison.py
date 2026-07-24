from models import ClassInfo
from repositories import (
    BehaviorRepository,
    KnowledgeRepository,
    StudentRepository,
    WarningRepository,
)
from services.analysis import PracticeAnalyzer


class ClassNotFoundError(ValueError):
    def __init__(self, class_id: int):
        super().__init__(f'班级不存在: {class_id}')
        self.class_id = class_id


class ClassComparisonService:
    @staticmethod
    def compare(class_ids: list[int]) -> list[dict]:
        class_ids = list(dict.fromkeys(class_ids))
        if len(class_ids) < 2:
            raise ValueError('至少选择两个不同班级')

        classes_by_id = {
            item.id: item
            for item in ClassInfo.query.filter(ClassInfo.id.in_(class_ids)).all()
        }
        for class_id in class_ids:
            if class_id not in classes_by_id:
                raise ClassNotFoundError(class_id)

        rows = []
        for class_id in class_ids:
            class_info = classes_by_id[class_id]
            behavior = BehaviorRepository.get_statistics(class_id)
            practice = PracticeAnalyzer(class_id).get_class_statistics()
            knowledge = KnowledgeRepository.get_knowledge_statistics(class_id)
            warnings = WarningRepository.get_statistics(class_id)
            student_count = StudentRepository.get_count(class_id)
            avg_mastery = (
                sum(item['avg_mastery_rate'] for item in knowledge) / len(knowledge)
                if knowledge else None
            )
            warning_count = warnings['warning_student_count']
            rows.append({
                'class_id': class_id,
                'class_name': class_info.class_name,
                'class_label': (
                    f'{class_info.class_name}（{class_info.term}）'
                    if class_info.term else class_info.class_name
                ),
                'student_count': student_count,
                'avg_attendance_rate': behavior['avg_attendance_rate'],
                'avg_practice_score': practice['avg_experiment_score'],
                'avg_mastery_rate': round(avg_mastery, 2) if avg_mastery is not None else None,
                'warning_count': warning_count,
                'warning_rate': round(warning_count / student_count * 100, 2) if student_count else 0,
            })

        return rows
