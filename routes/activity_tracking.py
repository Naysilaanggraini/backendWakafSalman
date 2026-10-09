"""Confirmed foreground time only; heartbeat gaps >45s never earn time."""
from uuid import UUID
from flask import Blueprint, g
from extensions import db
from models import Activity, ActivityTracking, User, Material
from models.learning import utcnow
from routes.auth import token_required
from routes.learning_access import LearningError, course_access, install_errors, payload, positive_id
from services.activity import record_activity

tracking_bp = Blueprint('activity_tracking', __name__, url_prefix='/api/me')
install_errors(tracking_bp)
TRACKED = {'sesi', 'buka_dashboard', 'buka_course', 'buka_materi', 'putar_video'}
MAX_GAP = 45


@tracking_bp.post('/activity')
@token_required
def pulse(user):
    data = payload({'request_id', 'previous_request_id', 'kind', 'course_id', 'material_id', 'action'}, {'request_id', 'kind', 'action'})
    try:
        key = str(UUID(data['request_id']))
    except (ValueError, TypeError, AttributeError):
        raise LearningError('Request ID tidak valid')
    kind, action = data['kind'], data['action']
    if not isinstance(kind, str) or not isinstance(action, str) or kind not in TRACKED or action not in {'active', 'pause', 'end'}:
        raise LearningError('Aktivitas atau action tidak valid')
    course_id, material_id = data.get('course_id'), data.get('material_id')
    if kind in {'sesi', 'buka_dashboard'}:
        if course_id is not None or material_id is not None:
            raise LearningError('Aktivitas umum tidak memiliki course/materi')
    else:
        if not positive_id(course_id):
            raise LearningError('Course tidak valid')
        course_access(user, course_id)
        if kind in {'buka_materi', 'putar_video'}:
            material = db.session.get(Material, material_id) if positive_id(material_id) else None
            if not material or material.id_course != course_id or material.status != 'aktif':
                raise LearningError('Materi tidak sesuai course', 403)
            if kind == 'putar_video' and material.jenis_file not in {'youtube', 'drive'}:
                raise LearningError('Materi bukan video', 400)
        elif material_id is not None:
            raise LearningError('Aktivitas course tidak memiliki materi')
    # All tracking mutations serialize per actor, including concurrent tab starts.
    db.session.execute(db.select(User.id_user).where(User.id_user == user.id_user).with_for_update()).scalar_one()
    now = utcnow()
    login_id = getattr(g, 'login_activity_id', None)
    login = db.session.get(Activity, login_id) if positive_id(login_id) else None
    if login and (login.id_user != user.id_user or login.jenis_aktivitas != 'login'):
        raise LearningError('Sesi login tidak valid', 403)
    previous_key = data.get('previous_request_id')
    if previous_key is not None:
        try:
            previous_key = str(UUID(previous_key))
        except (ValueError, TypeError, AttributeError):
            raise LearningError('Previous request ID tidak valid')
        if previous_key == key:
            raise LearningError('Previous request harus berbeda')
        previous = db.session.execute(db.select(ActivityTracking).where(
            ActivityTracking.request_id == previous_key).with_for_update()).scalar_one_or_none()
        if previous and (previous.activity.id_user != user.id_user or previous.activity.jenis_aktivitas != kind):
            raise LearningError('Aktivitas sebelumnya bukan milik/konteks Anda', 403)
        if previous and not previous.finished:
            gap = (now - previous.last_seen).total_seconds()
            if previous.running and 0 <= gap <= MAX_GAP:
                before = previous.credited_ms // 1000
                previous.credited_ms += int(gap * 1000)
                if kind == 'sesi' and previous.id_login_activity:
                    previous_login = db.session.get(Activity, previous.id_login_activity)
                    previous_login.durasi = (previous_login.durasi or 0) + previous.credited_ms // 1000 - before
                    previous_login.waktu_selesai = now
                previous.activity.waktu_selesai = now
            previous.activity.durasi = previous.credited_ms // 1000
            previous.running, previous.finished = False, True
    track = db.session.execute(db.select(ActivityTracking).where(ActivityTracking.request_id == key)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if track:
        event = track.activity
        if event.id_user != user.id_user:
            raise LearningError('Aktivitas bukan milik Anda', 403)
        if (event.jenis_aktivitas, event.id_course, event.id_materi) != (kind, course_id, material_id):
            raise LearningError('Konteks aktivitas berubah', 409)
        if track.id_login_activity != (login.id_activity if login else None):
            raise LearningError('Aktivitas berasal dari sesi login lain', 403)
        if track.finished:
            return {'activity': event.to_dict(), 'finished': True}
    else:
        event = record_activity(user.id_user, kind, id_course=course_id, id_materi=material_id,
                                durasi=0, waktu_dimulai=now)
        db.session.flush()
        track = ActivityTracking(activity=event, request_id=key, last_seen=now,
                                 credited_ms=0, running=False, finished=False,
                                 id_login_activity=login.id_activity if login else None)
        db.session.add(track)
    gap = (now - track.last_seen).total_seconds()
    if track.running and 0 <= gap <= MAX_GAP:
        credited = int(gap * 1000)
        before = track.credited_ms // 1000
        track.credited_ms += credited
        if kind == 'sesi' and login:
            login.durasi = (login.durasi or 0) + track.credited_ms // 1000 - before
            login.waktu_selesai = now
    # A single lease per actor/event kind prevents concurrent tabs counting twice.
    other = db.session.execute(db.select(ActivityTracking).join(Activity, Activity.id_activity == ActivityTracking.id_activity).where(
        Activity.id_user == user.id_user, Activity.jenis_aktivitas == kind,
        ActivityTracking.request_id != key, ActivityTracking.running.is_(True),
        ActivityTracking.finished.is_(False))).scalars().all()
    occupied = any(0 <= (now - t.last_seen).total_seconds() <= MAX_GAP for t in other)
    track.running = action == 'active' and not occupied
    track.finished = action == 'end'
    track.last_seen = now
    event.durasi = track.credited_ms // 1000
    # Last confirmed boundary, including abrupt exits; never extrapolate to now.
    event.waktu_selesai = now
    db.session.commit()
    return {'activity': event.to_dict(), 'finished': track.finished}
