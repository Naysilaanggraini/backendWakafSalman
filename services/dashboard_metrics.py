from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func, extract, text
from extensions import db
from models import User, UserCourse, Course, Activity, TestAttempt
from calendar import monthrange


def course_activity_trend(period, year, month, kind):
    shifted = func.datetime(Activity.waktu_dimulai, '+7 hours') if db.engine.dialect.name == 'sqlite' else func.timestampadd(text('HOUR'), 7, Activity.waktu_dimulai)
    local = case((Activity.time_basis == 'UTC', shifted), else_=Activity.waktu_dimulai)
    filters = (User.role == 'user', Activity.id_course.is_not(None))
    # First course visit per learner/course, including historical records.
    starts = db.select(func.min(local).label('at')).join(User, User.id_user == Activity.id_user).where(
        *filters, Activity.jenis_aktivitas == 'buka_course').group_by(Activity.id_user, Activity.id_course).subquery()
    sources = []
    if kind in ('all', 'course_started'):
        sources.append((starts.c.at, db.select(starts.c.at)))
    kinds = {'material_completed': 'selesai_materi', 'course_completed': 'selesai_course'}
    if kind != 'course_started':
        events = list(kinds.values()) if kind == 'all' else [kinds[kind]]
        sources.append((local, db.select(local).join(User, User.id_user == Activity.id_user).where(
            *filters, Activity.jenis_aktivitas.in_(events))))
    if period == 'daily':
        keys = [f'{year:04d}-{month:02d}-{day:02d}' for day in range(1, monthrange(year, month)[1] + 1)]
    elif period == 'monthly':
        keys = [f'{year:04d}-{m:02d}' for m in range(1, 13)]
    else:
        keys = [str(y) for y in range(year - 4, year + 1)]
    counts = dict.fromkeys(keys, 0)
    for timestamp, query in sources:
        parts = [extract('year', timestamp)]
        if period != 'yearly':
            parts.append(extract('month', timestamp))
        if period == 'daily':
            parts.append(extract('day', timestamp))
        query = query.with_only_columns(*parts, func.count()).group_by(*parts)
        query = query.where(parts[0].between(year - 4, year) if period == 'yearly' else parts[0] == year)
        if period == 'daily':
            query = query.where(parts[1] == month)
        for row in db.session.execute(query):
            key = '-'.join(str(int(value)).zfill(4 if i == 0 else 2) for i, value in enumerate(row[:-1]))
            if key in counts:
                counts[key] += row[-1]
    return {'period': period, 'year': year, 'month': month, 'kind': kind, 'timezone': 'Asia/Jakarta',
            'points': [{'date': key, 'count': count} for key, count in counts.items()], 'total': sum(counts.values())}


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
