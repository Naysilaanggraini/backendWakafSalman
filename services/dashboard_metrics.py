from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func, extract, text
from extensions import db
from models import User, UserCourse, Course, Activity, TestAttempt


def rankings():
    best = db.select(TestAttempt.id_user.label('uid'), TestAttempt.id_course.label('cid'),
        func.max(TestAttempt.nilai).label('score'),
        func.max(case((TestAttempt.status == 'lulus', 1), else_=0)).label('passed'))\
        .where(TestAttempt.status_attempt == 'completed').group_by(TestAttempt.id_user, TestAttempt.id_course).subquery()
    finished = case(( (UserCourse.status == 'selesai') & (best.c.passed == 1), 1), else_=0)
    rows = db.session.execute(db.select(User.id_user, User.nama,
        func.count(UserCourse.id_user_course).label('courses'), func.sum(finished).label('completed'),
        func.coalesce(func.avg(best.c.score), 0).label('score'),
        func.max(case((finished == 1, UserCourse.tanggal_selesai))).label('finished_at'))
        .join(UserCourse, UserCourse.id_user == User.id_user)
        .outerjoin(best, (best.c.uid == User.id_user) & (best.c.cid == UserCourse.id_course))
        .where(User.role == 'user', User.status == 'aktif')
        .group_by(User.id_user, User.nama)).all()
    rows = sorted(rows, key=lambda r: (-int(r.completed or 0), -float(r.score), r.finished_at or datetime.max, r.id_user))
    return [{'rank': i + 1, 'user_id': r.id_user, 'name': r.nama, 'courses': r.courses,
             'completed_courses': int(r.completed or 0), 'score': round(float(r.score), 2)} for i, r in enumerate(rows)]


def analytics(year):
    shifted = func.datetime(Activity.waktu_dimulai, '+7 hours') if db.engine.dialect.name == 'sqlite' else func.timestampadd(text('HOUR'), 7, Activity.waktu_dimulai)
    local = case((Activity.time_basis == 'UTC', shifted), else_=Activity.waktu_dimulai)
    query = db.select(extract('year', local).label('year'), extract('month', local).label('month'), func.count().label('count'))\
        .join(User, User.id_user == Activity.id_user).where(User.role == 'user', Activity.id_course.is_not(None),
        Activity.jenis_aktivitas.in_(['buka_course', 'buka_materi', 'putar_video', 'mulai_test', 'selesai_test']))\
        .group_by(extract('year', local), extract('month', local))
    rows = db.session.execute(query).all()
    years = sorted({int(r.year) for r in rows} | {year, (datetime.now(timezone.utc) + timedelta(hours=7)).year}, reverse=True)
    counts = {int(r.month): r.count for r in rows if int(r.year) == year}
    total = sum(counts.values())
    names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    return {'year': year, 'years': years, 'total': total, 'months': [{'month': name, 'count': counts.get(i+1, 0),
        'percentage': counts.get(i+1, 0) / total * 100 if total else 0} for i, name in enumerate(names)]}


def recent_activity():
    rows = db.session.execute(db.select(Activity, User.nama, Course.judul_course)
        .join(User, User.id_user == Activity.id_user).outerjoin(Course, Course.id_course == Activity.id_course)
        .order_by(Activity.waktu_dimulai.desc(), Activity.id_activity.desc()).limit(5)).all()
    return [{**event.to_dict(), 'user_name': name, 'course_title': course} for event, name, course in rows]
