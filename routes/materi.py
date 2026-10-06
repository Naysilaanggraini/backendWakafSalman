from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Course, Materi
from routes.auth import token_required, admin_required

materi_bp = Blueprint("materi", __name__, url_prefix="/api")


def validate_materi_data(data, *, create=False):
    if not isinstance(data, dict) or not data:
        return None, "Data materi wajib diisi"
    if set(data) - {"judul_materi", "jenis_file", "tautan_file", "durasi", "urutan", "status"}:
        return None, "Ada field yang tidak dapat diubah"
    values = {}
    for key, value in data.items():
        if key in {"durasi", "urutan"}:
            if key == "durasi" and value is None:
                values[key] = None
                continue
            maximum = 4294967295 if key == "durasi" else 65535
            if type(value) is not int or not 0 <= value <= maximum:
                return None, f"{key} harus berupa integer unsigned yang valid"
        else:
            if not isinstance(value, str):
                return None, f"{key} harus berupa teks"
            value = value.strip()
            if key in {"judul_materi", "tautan_file"}:
                maximum = 150 if key == "judul_materi" else 500
                if not value or len(value) > maximum:
                    return None, f"{key} wajib diisi dan maksimal {maximum} karakter"
            if key == "jenis_file" and value not in {"pdf", "youtube", "drive"}:
                return None, "jenis_file tidak valid"
            if key == "status" and value not in {"aktif", "nonaktif"}:
                return None, "Status tidak valid"
        values[key] = value
    if create and not {"judul_materi", "jenis_file", "tautan_file"} <= set(values):
        return None, "judul_materi, jenis_file, dan tautan_file wajib diisi"
    return values, None


def course_visible(user, course):
    return course is not None and (user.role == "admin" or (
        course.status == "aktif" and course.kategori is not None and course.kategori.status == "aktif"))


def integrity_response(error):
    db.session.rollback()
    code = error.orig.args[0] if getattr(error.orig, "args", ()) else None
    if code == 1062:
        return {"message": "Urutan materi sudah digunakan dalam course"}, 409
    if code in {1451, 1452}:
        return {"message": "Materi masih digunakan atau memiliki relasi tidak valid"}, 409
    return {"message": "Materi memiliki konflik constraint database"}, 409


@materi_bp.route("/course/<int:id_course>/materi", methods=["GET"])
@token_required
def list_materi(user, id_course):
    course = db.session.get(Course, id_course)
    if not course_visible(user, course):
        return {"message": "Course tidak ditemukan"}, 404
    query = db.select(Materi).where(Materi.id_course == id_course).order_by(Materi.urutan)
    if user.role != "admin":
        query = query.where(Materi.status == "aktif")
    return {"materi": [item.to_dict() for item in db.session.execute(query).scalars().all()]}, 200


@materi_bp.route("/materi/<int:id_materi>", methods=["GET"])
@token_required
def detail_materi(user, id_materi):
    item = db.session.get(Materi, id_materi)
    if item is None or not course_visible(user, item.course) or (user.role != "admin" and item.status != "aktif"):
        return {"message": "Materi tidak ditemukan"}, 404
    return {"materi": item.to_dict()}, 200


@materi_bp.route("/course/<int:id_course>/materi", methods=["POST"])
@token_required
@admin_required
def create_materi(user, id_course):
    values, error = validate_materi_data(request.get_json(silent=True), create=True)
    if error:
        return {"message": error}, 400
    course = db.session.get(Course, id_course)
    if course is None:
        return {"message": "Course tidak ditemukan"}, 404
    values.setdefault("urutan", 1)
    values.setdefault("status", "aktif")
    item = Materi(id_course=id_course, course=course, **values)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Materi berhasil ditambahkan", "materi": item.to_dict()}, 201


@materi_bp.route("/materi/<int:id_materi>", methods=["PATCH"])
@token_required
@admin_required
def update_materi(user, id_materi):
    item = db.session.get(Materi, id_materi)
    if item is None:
        return {"message": "Materi tidak ditemukan"}, 404
    values, error = validate_materi_data(request.get_json(silent=True))
    if error:
        return {"message": error}, 400
    for key, value in values.items():
        setattr(item, key, value)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Materi berhasil diperbarui", "materi": item.to_dict()}, 200


@materi_bp.route("/materi/<int:id_materi>", methods=["DELETE"])
@token_required
@admin_required
def delete_materi(user, id_materi):
    item = db.session.get(Materi, id_materi)
    if item is None:
        return {"message": "Materi tidak ditemukan"}, 404
    db.session.delete(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Materi berhasil dihapus"}, 200
