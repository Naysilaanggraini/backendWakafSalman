from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Course, UserCourse
from routes.auth import token_required


enrollment_bp = Blueprint("enrollment", __name__, url_prefix="/api")


@enrollment_bp.route("/course/<int:id_course>/enrollment", methods=["POST"])
@token_required
def enroll_course(user, id_course):
    # The URL and authenticated account are the only enrollment inputs.
    if request.get_data() and request.get_json(silent=True) != {}:
        return {"message": "Enrollment tidak menerima field dari client"}, 400
    course = db.session.get(Course, id_course)
    if course is None:
        return {"message": "Course tidak ditemukan"}, 404
    if course.status != "aktif" or course.kategori is None or course.kategori.status != "aktif":
        return {"message": "Course atau kategori tidak aktif"}, 403
    existing = db.session.execute(db.select(UserCourse).where(
        UserCourse.id_user == user.id_user, UserCourse.id_course == id_course)).scalar_one_or_none()
    if existing is not None:
        return {"message": "Anda sudah terdaftar pada course"}, 409
    item = UserCourse(id_user=user.id_user, id_course=id_course, course=course, status="belum_mulai")
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        code = error.orig.args[0] if getattr(error.orig, "args", ()) else None
        if code == 1062:
            return {"message": "Anda sudah terdaftar pada course"}, 409
        if code in {1451, 1452}:
            return {"message": "Enrollment memiliki konflik relasi"}, 409
        return {"message": "Enrollment memiliki konflik constraint database"}, 409
    return {"message": "Enrollment berhasil", "enrollment": item.to_dict()}, 201


@enrollment_bp.route("/me/enrollments", methods=["GET"])
@token_required
def list_enrollments(user):
    items = db.session.execute(db.select(UserCourse).where(
        UserCourse.id_user == user.id_user).order_by(UserCourse.id_user_course.desc())).scalars().all()
    return {"enrollments": [item.to_dict() for item in items]}, 200


@enrollment_bp.route("/me/enrollments/<int:id_user_course>", methods=["GET"])
@token_required
def detail_enrollment(user, id_user_course):
    item = db.session.execute(db.select(UserCourse).where(
        UserCourse.id_user_course == id_user_course, UserCourse.id_user == user.id_user)).scalar_one_or_none()
    if item is None:
        return {"message": "Enrollment tidak ditemukan"}, 404
    return {"enrollment": item.to_dict()}, 200
