from flask import Blueprint, request, current_app, url_for, send_from_directory
from pathlib import Path
from uuid import uuid4
import re
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Course, Materi, Kategori
from routes.auth import token_required, admin_required

materi_bp = Blueprint("materi", __name__, url_prefix="/api")

PDF_LIMIT = 10 * 1024 * 1024


def pdf_directory():
    return Path(current_app.config.get('MATERIAL_PDF_DIR', Path(current_app.instance_path) / 'materials'))


@materi_bp.post('/course/<int:id_course>/materi/pdf')
@token_required
@admin_required
def upload_pdf(user, id_course):
    if db.session.get(Course, id_course) is None:
        return {'message': 'Course tidak ditemukan'}, 404
    request.max_content_length = PDF_LIMIT + 1024 * 1024
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename or not uploaded.filename.lower().endswith('.pdf'):
        return {'message': 'Pilih file PDF yang valid'}, 400
    contents = uploaded.stream.read(PDF_LIMIT + 1)
    if len(contents) > PDF_LIMIT:
        return {'message': 'Ukuran PDF maksimal 10 MB'}, 413
    if not contents.startswith(b'%PDF-') or b'%%EOF' not in contents[-4096:]:
        return {'message': 'Isi file bukan dokumen PDF yang valid'}, 400
    filename = f'{uuid4().hex}.pdf'
    link = url_for('materi.download_pdf', filename=filename, _external=True)
    if len(link) > 500:
        return {'message': 'Alamat server terlalu panjang untuk tautan materi'}, 400
    try:
        directory = pdf_directory()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_bytes(contents)
    except OSError:
        return {'message': 'PDF belum dapat disimpan. Periksa penyimpanan server.'}, 503
    return {'message': 'PDF berhasil diupload', 'url': link}, 201


@materi_bp.get('/files/materials/<filename>')
def download_pdf(filename):
    if not re.fullmatch(r'[0-9a-f]{32}\.pdf', filename):
        return {'message': 'PDF tidak ditemukan'}, 404
    # Only publish files attached to an active material in an active catalog.
    item = db.session.execute(db.select(Materi.id_materi).join(Course).join(Kategori)
        .where(Materi.jenis_file == 'pdf', Materi.status == 'aktif', Course.status == 'aktif',
               Kategori.status == 'aktif', Materi.tautan_file.endswith('/api/files/materials/' + filename))
        .limit(1)).first()
    if item is None:
        return {'message': 'PDF tidak ditemukan'}, 404
    response = send_from_directory(pdf_directory(), filename, mimetype='application/pdf', conditional=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


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
