from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Course, Kategori
from routes.auth import token_required, admin_required


course_bp = Blueprint("course", __name__, url_prefix="/api/course")


def validate_course_data(data, *, create=False):
    if not isinstance(data, dict) or not data:
        return None, "Data course wajib diisi"
    allowed = {"judul_course", "deskripsi", "id_kategori", "key_point", "credit", "thumbnail", "status"}
    if set(data) - allowed:
        return None, "Ada field yang tidak dapat diubah"
    values = {}
    limits = {"judul_course": 150, "credit": 150, "thumbnail": 500}
    for key, value in data.items():
        if key == "id_kategori":
            if type(value) is not int or not 1 <= value <= 4294967295:
                return None, "id_kategori harus berupa integer positif dalam rentang INT UNSIGNED"
        elif key in {"deskripsi", "key_point", "credit", "thumbnail"} and value is None:
            pass
        else:
            if not isinstance(value, str):
                return None, f"{key} harus berupa teks"
            value = value.strip()
            if key == "judul_course" and not value:
                return None, "judul_course wajib diisi"
            if key in limits and len(value) > limits[key]:
                return None, f"{key} maksimal {limits[key]} karakter"
            if key in {"deskripsi", "key_point"}:
                try:
                    size = len(value.encode("utf-8"))
                except UnicodeEncodeError:
                    return None, f"{key} mengandung teks tidak valid"
                if size > 65535:
                    return None, f"{key} maksimal 65535 byte UTF-8"
            if key == "status" and value not in {"aktif", "nonaktif"}:
                return None, "Status tidak valid"
        values[key] = value
    if create:
        for key in ("judul_course", "id_kategori"):
            if key not in values:
                return None, f"{key} wajib diisi"
    return values, None


def integrity_response(error):
    db.session.rollback()
    code = error.orig.args[0] if getattr(error.orig, "args", ()) else None
    if code in {1451, 1452}:
        return {"message": "Course masih digunakan atau memiliki relasi tidak valid"}, 409
    raise error


@course_bp.route("", methods=["GET"])
@token_required
def list_course(user):
    query = db.select(Course).order_by(Course.id_course.desc())
    if user.role != "admin":
        query = query.where(Course.status == "aktif", Course.kategori.has(Kategori.status == "aktif"))
    items = db.session.execute(query).scalars().all()
    return {"course": [item.to_dict() for item in items]}, 200


@course_bp.route("/<int:course_id>", methods=["GET"])
@token_required
def detail_course(user, course_id):
    item = db.session.get(Course, course_id)
    if item is None or (user.role != "admin" and (
            item.status != "aktif" or item.kategori is None or item.kategori.status != "aktif")):
        return {"message": "Course tidak ditemukan"}, 404
    return {"course": item.to_dict()}, 200


@course_bp.route("", methods=["POST"])
@token_required
@admin_required
def create_course(user):
    values, error = validate_course_data(request.get_json(silent=True), create=True)
    if error:
        return {"message": error}, 400
    kategori = db.session.get(Kategori, values["id_kategori"])
    if kategori is None:
        return {"message": "Kategori tidak ditemukan"}, 404
    values.setdefault("status", "aktif")
    item = Course(**values)
    item.kategori = kategori
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Course berhasil ditambahkan", "course": item.to_dict()}, 201


@course_bp.route("/<int:course_id>", methods=["PATCH"])
@token_required
@admin_required
def update_course(user, course_id):
    item = db.session.get(Course, course_id)
    if item is None:
        return {"message": "Course tidak ditemukan"}, 404
    values, error = validate_course_data(request.get_json(silent=True))
    if error:
        return {"message": error}, 400
    if "id_kategori" in values:
        kategori = db.session.get(Kategori, values["id_kategori"])
        if kategori is None:
            return {"message": "Kategori tidak ditemukan"}, 404
        item.kategori = kategori
    for key, value in values.items():
        setattr(item, key, value)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Course berhasil diperbarui", "course": item.to_dict()}, 200


@course_bp.route("/<int:course_id>", methods=["DELETE"])
@token_required
@admin_required
def delete_course(user, course_id):
    item = db.session.get(Course, course_id)
    if item is None:
        return {"message": "Course tidak ditemukan"}, 404
    db.session.delete(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Course berhasil dihapus"}, 200
