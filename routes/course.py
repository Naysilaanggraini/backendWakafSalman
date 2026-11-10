from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from extensions import db
from models import Course, Kategori, UserCourse, User
from routes.auth import token_required, admin_required
from services.thumbnail import thumbnail_error
from services.object_storage import upload_object, StorageError
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError


course_bp = Blueprint("course", __name__, url_prefix="/api/course")


@course_bp.post('/thumbnail')
@token_required
@admin_required
def upload_thumbnail(user):
    limit = 512 * 1024
    request.max_content_length = limit + 64 * 1024
    uploaded = request.files.get('file')
    if uploaded is None or set(request.files) != {'file'} or len(request.files.getlist('file')) != 1:
        return {'message': 'Kirim satu file thumbnail'}, 400
    content = uploaded.stream.read(limit + 1)
    if len(content) > limit:
        return {'message': 'Ukuran thumbnail maksimal 512 KB'}, 413
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 16_000_000:
                    raise ValueError()
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGBA')
                image.thumbnail((1280, 1280))
                clean = Image.new('RGBA', image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format='PNG')
    except (ValueError, UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return {'message': 'Pilih gambar JPG, PNG, atau WebP yang valid'}, 400
    try:
        stored = upload_object(output.getvalue(), folder='thumbnails', extension='.png', content_type='image/png')
    except StorageError:
        return {'message': 'Thumbnail belum dapat disimpan ke S3. Periksa konfigurasi atau coba lagi.'}, 503
    return {'message': 'Thumbnail berhasil diupload', 'url': stored.url}, 201


def validate_course_data(data, *, create=False):
    if not isinstance(data, dict) or not data:
        return None, "Data course wajib diisi"
    allowed = {"judul_course", "deskripsi", "id_kategori", "key_point", "credit", "thumbnail", "status"}
    if set(data) - allowed:
        return None, "Ada field yang tidak dapat diubah"
    values = {}
    limits = {"judul_course": 150, "credit": 150}
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
            if key == 'thumbnail':
                error = thumbnail_error(value)
                if error:
                    return None, error
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
    return {"message": "Course memiliki konflik data. Muat ulang dan coba lagi."}, 409


@course_bp.route("/public", methods=["GET"])
def public_courses():
    participants = db.select(UserCourse.id_course.label('course_id'),
        func.count(func.distinct(UserCourse.id_user)).label('total'))\
        .join(User, User.id_user == UserCourse.id_user).where(User.role == 'user')\
        .group_by(UserCourse.id_course).subquery()
    rows = db.session.execute(db.select(Course, Kategori.nama_kategori)
        .join(Kategori, Course.id_kategori == Kategori.id_kategori)
        .outerjoin(participants, participants.c.course_id == Course.id_course)
        .where(Course.status == 'aktif', Kategori.status == 'aktif')
        .order_by(func.coalesce(participants.c.total, 0).desc(), Course.id_course.desc()).limit(6)).all()
    return {'course': [{'id': course.id_course, 'judul': course.judul_course,
                       'thumbnail': course.thumbnail, 'category': category}
                      for course, category in rows]}, 200


@course_bp.route("", methods=["GET"])
@token_required
def list_course(user):
    query = db.select(Course).options(selectinload(Course.materi)).order_by(Course.id_course.desc())
    if user.role != "admin":
        query = query.where(Course.status == "aktif", Course.kategori.has(Kategori.status == "aktif"))
    else:
        query = query.where(Course.status == "aktif")
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
    from services.deletion import remove_course, DeleteConflict
    item = db.session.get(Course, course_id, with_for_update=True)
    if item is None:
        return {"message": "Course tidak ditemukan"}, 404
    try:
        preserved = remove_course(item)
        db.session.commit()
    except DeleteConflict as error:
        db.session.rollback()
        return {"message": str(error)}, 409
    except IntegrityError as error:
        return integrity_response(error)
    message = "Course dihapus dari daftar; riwayat peserta tetap tersimpan." if preserved else "Course berhasil dihapus permanen."
    return {"message": message}, 200
