from uuid import UUID
from flask import Blueprint, g
from extensions import db
from models import Activity, ActivityTracking, User
from models.learning import utcnow
from routes.auth import token_required
from routes.learning_access import LearningError, install_errors, payload
from services.activity import record_activity

logout_bp = Blueprint('logout', __name__, url_prefix='/api/auth')
install_errors(logout_bp)


@logout_bp.post('/logout')
@token_required
def logout(user):
    data = payload({'request_id'}, {'request_id'})
    try:
        key = str(UUID(data['request_id']))
    except (TypeError, ValueError, AttributeError):
        raise LearningError('Request ID tidak valid')
    db.session.execute(db.select(User.id_user).where(User.id_user == user.id_user).with_for_update()).scalar_one()
    existing = db.session.execute(db.select(ActivityTracking).where(ActivityTracking.request_id == key)).scalar_one_or_none()
    if existing:
        if existing.activity.id_user != user.id_user or existing.activity.jenis_aktivitas != 'logout':
            raise LearningError('Request ID sudah digunakan', 409)
        return {'message': 'Logout tercatat'}
    now = utcnow()
    login_id = getattr(g, 'login_activity_id', None)
    if login_id is not None:
        ended = db.session.execute(db.select(ActivityTracking).join(Activity,
            Activity.id_activity == ActivityTracking.id_activity).where(
            ActivityTracking.id_login_activity == login_id, Activity.jenis_aktivitas == 'logout')).first()
        if ended:
            return {'message': 'Logout tercatat'}
    tracks = db.session.execute(db.select(ActivityTracking).join(Activity, Activity.id_activity == ActivityTracking.id_activity).where(
        Activity.id_user == user.id_user, ActivityTracking.id_login_activity == login_id,
        ActivityTracking.finished.is_(False)).with_for_update()).scalars().all()
    for track in tracks:
        gap = (now - track.last_seen).total_seconds()
        if track.running and 0 <= gap <= 45:
            before = track.credited_ms // 1000
            track.credited_ms += int(gap * 1000)
            track.activity.waktu_selesai = now
            if track.activity.jenis_aktivitas == 'sesi' and login_id:
                login = db.session.get(Activity, login_id)
                login.durasi = (login.durasi or 0) + track.credited_ms // 1000 - before
                login.waktu_selesai = now
        track.activity.durasi = track.credited_ms // 1000
        track.running, track.finished = False, True
    event = record_activity(user.id_user, 'logout', waktu_dimulai=now)
    db.session.flush()
    db.session.add(ActivityTracking(activity=event, request_id=key, last_seen=now,
                                   running=False, finished=True, credited_ms=0,
                                   id_login_activity=login_id))
    db.session.commit()
    return {'message': 'Logout tercatat'}
