from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from extensions import db
from models import User
from routes.auth import admin_required, token_required
from routes.user_validation import validate_user_data
from services.profile import apply_phone


users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("", methods=["GET"])
@token_required
@admin_required
def list_users(user):
    if user.status != "aktif":
        return {"message": "Akun tidak aktif"}, 403

    users = db.session.execute(
        db.select(User).order_by(User.id_user.desc())
    ).scalars().all()
    return {"users": [account.to_dict() for account in users]}, 200


@users_bp.route("", methods=["POST"])
@token_required
@admin_required
def create_user(user):
    if user.status != "aktif":
        return {"message": "Akun tidak aktif"}, 403
    values, error = validate_user_data(request.get_json(silent=True), create=True, admin=True, allow_phone=True)
    if error:
        return {"message": error}, 400
    values["password"] = generate_password_hash(values["password"])
    values.setdefault("role", "user")
    values.setdefault("status", "aktif")
    account = User()
    apply_phone(account, values)
    for key, value in values.items():
        setattr(account, key, value)
    db.session.add(account)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"message": "Email sudah terdaftar"}, 409
    return {"message": "User berhasil ditambahkan", "user": account.to_dict()}, 201


@users_bp.route("/<int:user_id>", methods=["PATCH"])
@token_required
@admin_required
def update_user(user, user_id):
    values, error = validate_user_data(request.get_json(silent=True), admin=True, allow_phone=True)
    if error:
        return {"message": error}, 400

    # Serialize status/role updates so concurrent edits cannot remove every active admin.
    accounts = db.session.execute(
        db.select(User).order_by(User.id_user).with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().all()
    actor = next((item for item in accounts if item.id_user == user.id_user), None)
    account = next((item for item in accounts if item.id_user == user_id), None)
    if not actor or actor.role != "admin" or actor.status != "aktif":
        db.session.rollback()
        return {"message": "Akses hanya untuk admin aktif"}, 403
    if not account:
        db.session.rollback()
        return {"message": "User tidak ditemukan"}, 404
    next_role = values.get("role", account.role)
    next_status = values.get("status", account.status)
    if account.id_user == actor.id_user and (next_role != "admin" or next_status != "aktif"):
        db.session.rollback()
        return {"message": "Anda tidak dapat menonaktifkan atau mengubah role akun sendiri"}, 400
    if account.role == "admin" and account.status == "aktif" and (next_role != "admin" or next_status != "aktif"):
        if not any(item.id_user != user_id and item.role == "admin" and item.status == "aktif" for item in accounts):
            db.session.rollback()
            return {"message": "Minimal satu admin harus tetap aktif"}, 400
    apply_phone(account, values)
    for key, value in values.items():
        setattr(account, key, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"message": "Email sudah terdaftar"}, 409
    return {"message": "User berhasil diperbarui", "user": account.to_dict()}, 200
