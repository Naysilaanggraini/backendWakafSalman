from datetime import datetime
from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError, OperationalError
from extensions import db
from models import Course, Materi, UserCourse, UserMateri
from routes.auth import token_required
from routes.materi import course_visible
from services.learning_progress import course_progress, sync_enrollment


progress_bp = Blueprint("progress", __name__, url_prefix="/api/me")


def validate_progress_data(data):
    if not isinstance(data, dict) or not data:
        return None, "Data progress wajib diisi"
    if set(data) - {"status", "durasi"}:
        return None, "Ada field yang tidak dapat diubah"
    if "status" in data and (not isinstance(data["status"], str) or data["status"] not in {"belum_mulai", "berlangsung", "selesai"}):
        return None, "Status tidak valid"
    if "durasi" in data and data["durasi"] is not None and (
        type(data["durasi"]) is not int or not 0 <= data["durasi"] <= 4294967295):
        return None, "durasi harus berupa integer unsigned yang valid"
    return dict(data), None


def find_enrollment(id_user, id_course, *, lock=False):
    query = db.select(UserCourse).where(UserCourse.id_user == id_user, UserCourse.id_course == id_course)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.session.execute(query).scalar_one_or_none()


def find_progress(id_user, id_materi):
    return db.session.execute(db.select(UserMateri).where(
        UserMateri.id_user == id_user, UserMateri.id_materi == id_materi)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()


def progress_error(error):
    db.session.rollback()
    code = error.orig.args[0] if getattr(error.orig, "args", ()) else None
    if isinstance(error, IntegrityError) and code in {1062, 1451, 1452}:
        return {"message": "Progress memiliki konflik data atau relasi"}, 409
    if isinstance(error, OperationalError) and code in {1205, 1213}:
        return {"message": "Progress sedang diperbarui, silakan coba lagi"}, 409
    if isinstance(error, IntegrityError):
        return {"message": "Progress memiliki konflik constraint database"}, 409
    return {"message": "Progress belum dapat disimpan, silakan coba lagi"}, 503


def get_materi(user, id_materi):
    item = db.session.get(Materi, id_materi)
    if item is None or not course_visible(user, item.course) or (user.role != "admin" and item.status != "aktif"):
        return None
    return item


@progress_bp.route("/materi/<int:id_materi>/progress", methods=["GET"])
@token_required
def detail_progress(user, id_materi):
    materi = get_materi(user, id_materi)
    if materi is None:
        return {"message": "Materi tidak ditemukan"}, 404
    if find_enrollment(user.id_user, materi.id_course) is None:
        return {"message": "Anda belum terdaftar pada course"}, 403
    item = db.session.execute(db.select(UserMateri).where(
        UserMateri.id_user == user.id_user, UserMateri.id_materi == id_materi)).scalar_one_or_none()
    if item is None:
        # Virtual state only: GET does not insert a record.
        item = UserMateri(id_user=user.id_user, id_materi=id_materi, status="belum_mulai")
    return {"progress": item.to_dict()}, 200


@progress_bp.route("/materi/<int:id_materi>/progress", methods=["PATCH"])
@token_required
def update_progress(user, id_materi):
    values, error = validate_progress_data(request.get_json(silent=True))
    if error:
        return {"message": error}, 400
    materi = get_materi(user, id_materi)
    if materi is None:
        return {"message": "Materi tidak ditemukan"}, 404
    if materi.status != "aktif" or materi.course.status != "aktif" or materi.course.kategori.status != "aktif":
        return {"message": "Materi, course, atau kategori tidak aktif"}, 403
    try:
        enrollment = find_enrollment(user.id_user, materi.id_course, lock=True)
        if enrollment is None:
            db.session.rollback()
            return {"message": "Anda belum terdaftar pada course"}, 403
        item = find_progress(user.id_user, id_materi)
        if item is None:
            item = UserMateri(id_user=user.id_user, id_materi=id_materi, materi=materi, status="belum_mulai")
            db.session.add(item)
        now = datetime.now()
        status = values.get("status", item.status)
        if status == "belum_mulai":
            item.waktu_mulai = None
            item.waktu_selesai = None
        else:
            if item.waktu_mulai is None:
                item.waktu_mulai = now
            if status == "selesai":
                if item.waktu_selesai is None:
                    item.waktu_selesai = now
            else:
                item.waktu_selesai = None
        item.status = status
        if "durasi" in values:
            item.durasi = values["durasi"]
        db.session.flush()
        summary = course_progress(user.id_user, materi.id_course, lock=True)
        sync_enrollment(enrollment, summary, now)
        db.session.commit()
    except (IntegrityError, OperationalError) as error:
        return progress_error(error)
    return {"message": "Progress berhasil diperbarui", "progress": item.to_dict(), "course_progress": summary}, 200


@progress_bp.route("/course/<int:id_course>/progress", methods=["GET"])
@token_required
def detail_course_progress(user, id_course):
    course = db.session.get(Course, id_course)
    if not course_visible(user, course):
        return {"message": "Course tidak ditemukan"}, 404
    if find_enrollment(user.id_user, id_course) is None:
        return {"message": "Anda belum terdaftar pada course"}, 403
    return {"progress": course_progress(user.id_user, id_course)}, 200
