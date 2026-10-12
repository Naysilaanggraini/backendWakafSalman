from flask import Blueprint, request
from sqlalchemy import case, func, or_, and_
from datetime import date, datetime, time, timedelta, timezone

from extensions import db
from models import User, Activity, Course, Materi, ActivityTracking, UserCourse, TestAttempt
from models.activity import ACTIVITY_TYPES
from routes.auth import token_required, admin_required
from routes.learning_access import install_errors
from services.dashboard_metrics import rankings, analytics, recent_activity


reporting_bp = Blueprint("reporting", __name__, url_prefix="/api")
install_errors(reporting_bp)


@reporting_bp.get('/admin/courses/participants')
@token_required
@admin_required
def course_participants(user):
    total = db.session.scalar(db.select(func.count(func.distinct(UserCourse.id_user)))
        .join(User, User.id_user == UserCourse.id_user).where(User.role == 'user'))
    return {'total_participants': total or 0}


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
    try:
        year = int(request.args.get('year', (datetime.now(timezone.utc) + timedelta(hours=7)).year))
        if not 1900 <= year <= 9998:
            raise ValueError()
    except ValueError:
        return {'message': 'Tahun tidak valid'}, 400
    total_courses = db.session.scalar(db.select(func.count(Course.id_course)))
    passed = db.select(TestAttempt.id_penilaian).where(TestAttempt.id_user == UserCourse.id_user,
        TestAttempt.id_course == UserCourse.id_course, TestAttempt.status_attempt == 'completed',
        TestAttempt.status == 'lulus').exists()
    enrolled, completed = db.session.execute(db.select(func.count(UserCourse.id_user_course),
        func.coalesce(func.sum(case(((UserCourse.status == 'selesai') & passed, 1), else_=0)), 0))
        .join(User, User.id_user == UserCourse.id_user).where(User.role == 'user')).one()
    learning = {'total_courses': total_courses or 0, 'total_enrollments': enrolled,
                'completed_enrollments': int(completed),
                'completion_rate': round(completed / enrolled * 100, 1) if enrolled else 0}
    participants = func.count(func.distinct(UserCourse.id_user))
    rows = db.session.execute(db.select(Course.id_course, Course.id_kategori,
        Course.judul_course, participants.label('participants'))
        .join(UserCourse, UserCourse.id_course == Course.id_course)
        .join(User, User.id_user == UserCourse.id_user).where(User.role == 'user')
        .group_by(Course.id_course, Course.id_kategori, Course.judul_course)
        .order_by(participants.desc(), Course.id_course.asc())).all()
    popular = [{'id': row.id_course, 'category_id': row.id_kategori,
                'name': row.judul_course, 'participants': row.participants} for row in rows]
    counts = db.session.execute(db.select(
        func.count(User.id_user),
        func.coalesce(func.sum(case((User.status == "aktif", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.status == "nonaktif", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.role == "admin", 1), else_=0)), 0),
        func.coalesce(func.sum(case((User.role == "user", 1), else_=0)), 0),
    )).one()
    return {
        "identity": dict(zip(("total_users", "active_users", "inactive_users", "admins", "regular_users"), map(int, counts))),
        "learning": learning,
        'popular_courses': popular[:5],
        'all_popular_courses': popular,
        'analytics': analytics(year),
        'leaderboard': rankings()[:5],
        'recent_activity': recent_activity(),
        "assessment": None,
        "dependencies": ["[DEPENDENCY DEV 3] Assessment statistics"],
    }, 200


@reporting_bp.get("/leaderboard")
@token_required
def leaderboard(user):
    try:
        page, size = int(request.args.get('page', 1)), int(request.args.get('per_page', 20))
        if not 1 <= page <= 1000000 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        return {'message': 'Pagination tidak valid'}, 400
    items = rankings()
    return {'rankings': items[(page-1)*size:page*size], 'top_three': items[:3],
        'my_rank': next((row for row in items if row['user_id'] == user.id_user), None),
        'pagination': {'page': page, 'per_page': size, 'total': len(items), 'pages': (len(items)+size-1)//size}}
