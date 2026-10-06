from flask import Blueprint, request
from sqlalchemy import case, func

from extensions import db
from models import User, Activity
from models.activity import ACTIVITY_TYPES
from routes.auth import token_required, admin_required


reporting_bp = Blueprint("reporting", __name__, url_prefix="/api")


@reporting_bp.get("/activity")
@token_required
@admin_required
def activity_log(user):
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
        actor = request.args.get("id_user")
        actor = int(actor) if actor is not None else None
        if not 1 <= page <= 1000000 or not 1 <= per_page <= 100 or (actor is not None and not 0 < actor <= 4294967295):
            raise ValueError()
    except ValueError:
        return {"message": "Parameter pagination atau id_user tidak valid"}, 400
    kind = request.args.get("jenis_aktivitas")
    if kind is not None and kind not in ACTIVITY_TYPES:
        return {"message": "Jenis aktivitas tidak valid"}, 400
    filters = []
    if actor is not None:
        filters.append(Activity.id_user == actor)
    if kind is not None:
        filters.append(Activity.jenis_aktivitas == kind)
    total = db.session.scalar(db.select(func.count()).select_from(Activity).where(*filters))
    rows = db.session.execute(db.select(Activity).where(*filters)
                              .order_by(Activity.waktu_dimulai.desc(), Activity.id_activity.desc())
                              .offset((page - 1) * per_page).limit(per_page)).scalars().all()
    return {"activities": [row.to_dict() for row in rows], "pagination": {
        "page": page, "per_page": per_page, "total": total,
        "pages": (total + per_page - 1) // per_page,
    }}, 200


@reporting_bp.get("/dashboard")
@token_required
@admin_required
def dashboard(user):
    counts = db.session.execute(db.select(
        func.count(User.id_user),
        func.coalesce(func.sum(case((User.status == "aktif", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.status == "nonaktif", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.role == "admin", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.role == "user", 1), else_=0)), 0),
    )).one()
    return {
        "identity": dict(zip(("total_users", "active_users", "inactive_users", "admins", "regular_users"), map(int, counts))),
        "learning": None,
        "assessment": None,
        "dependencies": ["[DEPENDENCY DEV 2] Learning statistics", "[DEPENDENCY DEV 3] Assessment statistics"],
    }, 200


@reporting_bp.get("/leaderboard")
@token_required
def leaderboard(user):
    # Explicitly unavailable: an empty list/zero scores would imply a real ranking.
    return {
        "status": "pending_dependencies",
        "message": "Leaderboard menunggu kontrak data dan aturan ranking yang disepakati",
        "dependencies": [
            "[DEPENDENCY DEV 2] Enrollment dan completion",
            "[DEPENDENCY DEV 3] Penilaian final dan aturan pemilihan attempt",
            "Keputusan tim: points, periode, eligibility, dan tie-break",
        ],
    }, 501
