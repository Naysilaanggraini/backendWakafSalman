from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Kategori
from routes.auth import token_required, admin_required


kategori_bp = Blueprint("kategori", __name__, url_prefix="/api/kategori")


def validate_kategori_data(data, *, create=False):
    if not isinstance(data, dict) or not data:
        return None, "Data kategori wajib diisi"
    if set(data) - {"nama_kategori", "thumbnail", "status"}:
        return None, "Ada field yang tidak dapat diubah"
    values = {}
    for key, value in data.items():
        if key == "thumbnail" and value is None:
            values[key] = None
            continue
        if not isinstance(value, str):
            return None, f"{key} harus berupa teks"
        value = value.strip()
        if key == "nama_kategori":
            if not value:
                return None, "nama_kategori wajib diisi"
            if len(value) > 100:
                return None, "nama_kategori maksimal 100 karakter"
        if key == "thumbnail" and len(value) > 255:
            return None, "thumbnail maksimal 255 karakter"
        if key == "status" and value not in {"aktif", "nonaktif"}:
            return None, "Status tidak valid"
        values[key] = value
    if create and "nama_kategori" not in values:
        return None, "nama_kategori wajib diisi"
    return values, None


def integrity_response(error):
    db.session.rollback()
    code = error.orig.args[0] if getattr(error.orig, "args", ()) else None
    if code == 1062:
        return {"message": "Nama kategori sudah terdaftar"}, 409
    if code in {1451, 1452}:
        return {"message": "Kategori masih digunakan atau memiliki relasi tidak valid"}, 409
    raise error


@kategori_bp.route("", methods=["GET"])
@token_required
def list_kategori(user):
    query = db.select(Kategori).order_by(Kategori.id_kategori.desc())
    if user.role != "admin":
        query = query.where(Kategori.status == "aktif")
    items = db.session.execute(query).scalars().all()
    return {"kategori": [item.to_dict() for item in items]}, 200


def visible_kategori(user, kategori_id):
    item = db.session.get(Kategori, kategori_id)
    if item is None or (user.role != "admin" and item.status != "aktif"):
        return None
    return item


@kategori_bp.route("/<int:kategori_id>", methods=["GET"])
@token_required
def detail_kategori(user, kategori_id):
    item = visible_kategori(user, kategori_id)
    if item is None:
        return {"message": "Kategori tidak ditemukan"}, 404
    return {"kategori": item.to_dict()}, 200


@kategori_bp.route("", methods=["POST"])
@token_required
@admin_required
def create_kategori(user):
    values, error = validate_kategori_data(request.get_json(silent=True), create=True)
    if error:
        return {"message": error}, 400
    values.setdefault("status", "aktif")
    item = Kategori(**values)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Kategori berhasil ditambahkan", "kategori": item.to_dict()}, 201


@kategori_bp.route("/<int:kategori_id>", methods=["PATCH"])
@token_required
@admin_required
def update_kategori(user, kategori_id):
    item = db.session.get(Kategori, kategori_id)
    if item is None:
        return {"message": "Kategori tidak ditemukan"}, 404
    values, error = validate_kategori_data(request.get_json(silent=True))
    if error:
        return {"message": error}, 400
    for key, value in values.items():
        setattr(item, key, value)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Kategori berhasil diperbarui", "kategori": item.to_dict()}, 200


@kategori_bp.route("/<int:kategori_id>", methods=["DELETE"])
@token_required
@admin_required
def delete_kategori(user, kategori_id):
    item = db.session.get(Kategori, kategori_id)
    if item is None:
        return {"message": "Kategori tidak ditemukan"}, 404
    db.session.delete(item)
    try:
        db.session.commit()
    except IntegrityError as error:
        return integrity_response(error)
    return {"message": "Kategori berhasil dihapus"}, 200

