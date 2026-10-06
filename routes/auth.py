from flask import Blueprint, request, current_app, send_from_directory, abort
import re
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from functools import wraps

import jwt

from extensions import db
from models import User
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from services.activity import record_activity
from services.profile import apply_phone
from routes.user_validation import validate_user_data
from routes.profile_photos import MAX_PHOTO_BYTES, photo_directory, save_profile_photo


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# =========================================================
# JWT TOKEN CHECK
# =========================================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return {
                "message": "Token tidak ditemukan"
            }, 401

        try:
            parts = auth_header.split()

            if len(parts) != 2 or parts[0].lower() != "bearer":
                return {
                    "message": "Format token tidak valid"
                }, 401

            token = parts[1]

            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"],
                options={"require": ["exp", "id_user"]}
            )

            if type(payload["id_user"]) is not int or payload["id_user"] <= 0:
                return {"message": "Token tidak valid"}, 401

            user = db.session.get(
                User,
                payload["id_user"]
            )

            if not user:
                return {
                    "message": "User tidak ditemukan"
                }, 404

            if user.status != "aktif":
                return {"message": "Akun tidak aktif"}, 403

        except jwt.ExpiredSignatureError:
            return {
                "message": "Token sudah kedaluwarsa"
            }, 401

        except jwt.InvalidTokenError:
            return {
                "message": "Token tidak valid"
            }, 401

        return f(user, *args, **kwargs)

    return decorated


# =========================================================
# ADMIN CHECK
# =========================================================

def admin_required(f):
    @wraps(f)
    def decorated(user, *args, **kwargs):
        if user.role != "admin":
            return {
                "message": "Akses hanya untuk admin"
            }, 403

        return f(user, *args, **kwargs)

    return decorated


# =========================================================
# REGISTER
# =========================================================

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return {
            "message": "Data registrasi tidak ditemukan"
        }, 400

    # Preserve public registration's existing behavior: extra role/status ignored.
    values, error = validate_user_data(
        {key: data.get(key) for key in ("nama", "email", "password")}, create=True)
    if error:
        return {"message": error}, 400
    nama, email, password = (values[key] for key in ("nama", "email", "password"))

    existing_user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()

    if existing_user:
        return {
            "message": "Email sudah terdaftar"
        }, 409

    new_user = User(
        nama=nama,
        email=email,
        password=generate_password_hash(password),
        role="user",
        status="aktif"
    )

    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"message": "Email sudah terdaftar"}, 409

    return {
        "message": "Registrasi berhasil"
    }, 201


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return {
            "message": "Data login tidak ditemukan"
        }, 400

    email = data.get("email")
    password = data.get("password")

    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return {
            "message": "Email dan password wajib diisi"
        }, 400

    user = db.session.execute(
        db.select(User).where(User.email == email.strip())
    ).scalar_one_or_none()

    if not user:
        return {
            "message": "Email atau password salah"
        }, 401

    if user.status != "aktif":
        return {
            "message": "Akun tidak aktif"
        }, 403

    if not check_password_hash(user.password, password):
        return {
            "message": "Email atau password salah"
        }, 401

    user.terakhir_login = datetime.now()

    payload = {
        "id_user": user.id_user,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8)
    }

    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256"
    )

    record_activity(user.id_user, "login", waktu_dimulai=user.terakhir_login)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Login belum dapat disimpan. Coba lagi."}, 503

    return {
        "message": "Login berhasil",
        "token": token,
        "user": {
            "id_user": user.id_user,
            "nama": user.nama,
            "email": user.email,
            "role": user.role
        }
    }, 200


# =========================================================
# GET CURRENT USER
# =========================================================

@auth_bp.route("/me", methods=["GET"])
@token_required
def me(user):
    if user.status != "aktif":
        return {"message": "Akun tidak aktif"}, 403
    return user.to_dict(), 200


@auth_bp.route("/me", methods=["PATCH"])
@token_required
def update_me(user):
    request.max_content_length = MAX_PHOTO_BYTES + 64 * 1024
    multipart = request.mimetype == "multipart/form-data"
    data = request.form.to_dict() if multipart else request.get_json(silent=True)
    if multipart and not data and request.files:
        data = {"foto_profil": ""}
    values, error = validate_user_data(data, allow_phone=True)
    if error:
        return {"message": error}, 400
    photo_path = None
    if multipart and request.files:
        if set(request.files) != {"foto"} or len(request.files.getlist("foto")) != 1:
            return {"message": "Kirim satu file foto profil"}, 400
        try:
            photo_path = save_profile_photo(request.files["foto"])
        except ValueError as error:
            return {"message": str(error)}, 400
        except OSError:
            return {"message": "Foto belum dapat disimpan. Coba lagi."}, 503
        values["foto_profil"] = "/api/auth/profile-photos/" + photo_path.name
    apply_phone(user, values)
    for key, value in values.items():
        setattr(user, key, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if photo_path:
            photo_path.unlink(missing_ok=True)
        return {"message": "Email sudah terdaftar"}, 409
    except Exception:
        db.session.rollback()
        if photo_path:
            photo_path.unlink(missing_ok=True)
        raise
    return {"message": "Profil berhasil diperbarui", "user": user.to_dict()}, 200


@auth_bp.errorhandler(RequestEntityTooLarge)
def photo_too_large(error):
    return {"message": "Ukuran foto maksimal 2 MB"}, 413


@auth_bp.route("/profile-photos/<filename>", methods=["GET"])
def profile_photo(filename):
    if not re.fullmatch(r"[a-f0-9]{32}\.png", filename):
        abort(404)
    response = send_from_directory(photo_directory(), filename, mimetype="image/png", max_age=86400)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# =========================================================
# ADMIN TEST
# =========================================================

@auth_bp.route("/admin-test", methods=["GET"])
@token_required
@admin_required
def admin_test(user):
    return {
        "message": "Akses admin berhasil",
        "user": {
            "id_user": user.id_user,
            "nama": user.nama,
            "role": user.role
        }
    }, 200
