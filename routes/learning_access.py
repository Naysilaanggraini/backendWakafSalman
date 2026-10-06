from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Course, Enrollment, Material, Question


class LearningError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def install_errors(bp):
    @bp.errorhandler(LearningError)
    def validation(error):
        db.session.rollback()
        return {"message": error.message}, error.status

    @bp.errorhandler(IntegrityError)
    def conflict(error):
        db.session.rollback()
        return {"message": "Data berubah bersamaan. Muat ulang dan coba lagi."}, 409

    @bp.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        return {"message": error.description}, error.code


def payload(allowed, required=()):
    from flask import request
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - set(allowed) or not set(required) <= set(data):
        raise LearningError("Payload tidak valid atau berisi field yang tidak diizinkan")
    return data


def positive_id(value):
    return type(value) is int and value > 0


def course_access(user, course_id, lock=False):
    course = db.session.get(Course, course_id)
    if not course:
        raise LearningError("Course tidak ditemukan", 404)
    if course.status != "aktif":
        raise LearningError("Course tidak dapat diakses", 403)
    query = db.select(Enrollment).where(Enrollment.id_user == user.id_user, Enrollment.id_course == course_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    enrollment = db.session.execute(query).scalar_one_or_none()
    if not enrollment:
        raise LearningError("Anda tidak memiliki akses pada course ini", 403)
    return course, enrollment


def discussion_context(user, context_type, context_id):
    if context_type not in {"course", "material", "test"}:
        raise LearningError("Context discussion tidak valid")
    material = None
    if context_type == "material":
        material = db.session.get(Material, context_id)
        if not material:
            raise LearningError("Materi tidak ditemukan", 404)
        if material.status != "aktif":
            raise LearningError("Materi tidak dapat diakses", 403)
    course_id = material.id_course if material else context_id
    course_access(user, course_id)
    if context_type == "test" and not db.session.execute(db.select(Question.id_soal).where(
        Question.id_course == course_id, Question.status == "aktif").limit(1)).first():
        raise LearningError("Test tidak ditemukan", 404)
    return course_id, material.id_materi if material else None
