"""Transactional catalog deletion; callers own commit/rollback."""
from extensions import db
from models import Materi, UserCourse, UserMateri, Question, TestAttempt, UserAnswer, Discussion, Activity, User


class DeleteConflict(Exception):
    pass


def rows(model, *conditions):
    return db.session.execute(db.select(model).where(*conditions).with_for_update()).scalars().all()


def question_used(question):
    if rows(UserAnswer, UserAnswer.id_soal == question.id_soal):
        return True
    for attempt in rows(TestAttempt, TestAttempt.id_course == question.id_course):
        # Legacy attempts have no snapshot: retain potentially referenced questions.
        if attempt.question_snapshot is None or any(
                q['question_id'] == question.id_soal for q in attempt.question_snapshot):
            return True
    return False


def delete_question(question):
    for option in list(question.options):
        db.session.delete(option)
    db.session.flush()
    db.session.delete(question)
    db.session.flush()


def delete_material(material):
    if rows(UserMateri, UserMateri.id_materi == material.id_materi):
        raise DeleteConflict('Materi memiliki progres peserta dan tidak dapat dihapus tanpa menghapus riwayat.')
    if rows(Discussion, Discussion.id_materi == material.id_materi):
        raise DeleteConflict('Materi memiliki diskusi peserta dan tidak dapat dihapus tanpa menghapus riwayat.')
    for activity in rows(Activity, Activity.id_materi == material.id_materi):
        activity.id_materi = None
    db.session.flush()
    db.session.delete(material)
    db.session.flush()


def ensure_unused(course):
    materials = db.select(Materi.id_materi).where(Materi.id_course == course.id_course)
    checks = (
        (UserCourse, UserCourse.id_course == course.id_course, 'pendaftaran peserta'),
        (TestAttempt, TestAttempt.id_course == course.id_course, 'riwayat tes peserta'),
        (UserMateri, UserMateri.id_materi.in_(materials), 'progres materi peserta'),
        (Discussion, Discussion.id_course == course.id_course, 'diskusi'),
        (Activity, db.and_(Activity.id_course == course.id_course,
            Activity.id_user.in_(db.select(User.id_user).where(User.role == 'user'))), 'aktivitas peserta'),
    )
    for model, condition, reason in checks:
        if rows(model, condition):
            raise DeleteConflict(f'Course "{course.judul_course}" memiliki {reason}. '
                                 'Riwayat dipertahankan; pindahkan course jika ingin menghapus kategorinya.')


def delete_course_tree(course):
    ensure_unused(course)
    for question in rows(Question, Question.id_course == course.id_course):
        if question_used(question):
            raise DeleteConflict('Course memiliki soal yang digunakan peserta.')
        delete_question(question)
    for material in rows(Materi, Materi.id_course == course.id_course):
        delete_material(material)
    for activity in rows(Activity, Activity.id_course == course.id_course):
        activity.id_course = None
    db.session.flush()
    # Explicit child deletes avoid ORM attempting to null non-null child FKs.
    db.session.expire(course, ['questions', 'materi'])
    db.session.delete(course)
    db.session.flush()


def remove_course(course):
    """Remove from management, retaining the complete tree when history exists."""
    try:
        ensure_unused(course)
    except DeleteConflict:
        course.status = 'nonaktif'
        db.session.flush()
        return True
    delete_course_tree(course)
    return False
