from flask import Blueprint, request
from sqlalchemy import case, func, or_, and_
from datetime import date, datetime, time, timedelta

from extensions import db
from models import User, Activity, Course, Materi, ActivityTracking
from models.activity import ACTIVITY_TYPES
from routes.auth import token_required, admin_required
from routes.learning_access import install_errors


reporting_bp = Blueprint("reporting", __name__, url_prefix="/api")
install_errors(reporting_bp)


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
    search = request.args.get('search', '').strip()
    user_search = request.args.get('user', '').strip()
    course_search = request.args.get('course', '').strip()
    if any(len(value) > 200 for value in (search, user_search, course_search)):
        return {'message': 'Pencarian maksimal 200 karakter'}, 400
    if search:
        filters.append(or_(User.nama.icontains(search, autoescape=True), User.email.icontains(search, autoescape=True),
                           Course.judul_course.icontains(search, autoescape=True)))
    if user_search:
        filters.append(or_(User.nama.icontains(user_search, autoescape=True), User.email.icontains(user_search, autoescape=True)))
    if course_search:
        filters.append(Course.judul_course.icontains(course_search, autoescape=True))
    try:
        start, end = request.args.get('date_from'), request.args.get('date_to')
        start = date.fromisoformat(start) if start else None
        end = date.fromisoformat(end) if end else None
        if start and end and start > end:
            raise ValueError()
        for value, lower in ((start, True), (end, False)):
            if value:
                local = datetime.combine(value, time.min) + (timedelta() if lower else timedelta(days=1))
                utc = local - timedelta(hours=7)
                comparison_utc = Activity.waktu_dimulai >= utc if lower else Activity.waktu_dimulai < utc
                comparison_legacy = Activity.waktu_dimulai >= local if lower else Activity.waktu_dimulai < local
                filters.append(or_(and_(Activity.time_basis == 'UTC', comparison_utc),
                                   and_(Activity.time_basis.is_(None), comparison_legacy)))
    except (ValueError, OverflowError):
        return {'message': 'Rentang tanggal tidak valid (gunakan YYYY-MM-DD, WIB)'}, 400
    query = db.select(Activity, User, Course, Materi, ActivityTracking).join(User, User.id_user == Activity.id_user) \
        .outerjoin(Materi, Materi.id_materi == Activity.id_materi) \
        .outerjoin(ActivityTracking, ActivityTracking.id_activity == Activity.id_activity) \
        .outerjoin(Course, Course.id_course == func.coalesce(Activity.id_course, Materi.id_course)).where(*filters)
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(query
                              .order_by(Activity.waktu_dimulai.desc(), Activity.id_activity.desc())
                              .offset((page - 1) * per_page).limit(per_page)).all()
    return {"activities": [{**event.to_dict(), 'user_name': actor.nama,
                            'course_title': course.judul_course if course else None,
                            'material_title': material.judul_materi if material else None,
                            'duration_status': ('completed' if track.finished else 'confirmed_partial') if track else ('unavailable' if event.durasi is None else 'recorded'),
                            'description': event.jenis_aktivitas.replace('_', ' ')}
                           for event, actor, course, material, track in rows], "pagination": {
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
