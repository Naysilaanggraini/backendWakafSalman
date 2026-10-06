from sqlalchemy import and_
from extensions import db
from models import Materi, UserMateri


def course_progress(id_user, id_course, *, lock=False):
    query = db.select(Materi, UserMateri).outerjoin(UserMateri, and_(
        UserMateri.id_materi == Materi.id_materi, UserMateri.id_user == id_user)
    ).where(Materi.id_course == id_course, Materi.status == "aktif").order_by(Materi.urutan)
    if lock:
        # Current reads after the enrollment lock avoid stale concurrent snapshots.
        query = query.with_for_update().execution_options(populate_existing=True)
    rows = db.session.execute(query).all()
    total = len(rows)
    selesai = sum(1 for _, progress in rows if progress is not None and progress.status == "selesai")
    started = any(progress is not None and progress.status != "belum_mulai" for _, progress in rows)
    status = "selesai" if total > 0 and selesai == total else "berlangsung" if started else "belum_mulai"
    return {"id_course": id_course, "total_materi": total, "materi_selesai": selesai,
            "progress": round(selesai / total * 100, 2) if total else 0,
            "status": status,
            "materi": [{"id_materi": materi.id_materi, "judul_materi": materi.judul_materi,
                        "urutan": materi.urutan, "status": progress.status if progress else "belum_mulai"}
                       for materi, progress in rows]}


def sync_enrollment(enrollment, summary, now):
    enrollment.status = summary["status"]
    if enrollment.status == "selesai":
        if enrollment.tanggal_selesai is None:
            enrollment.tanggal_selesai = now
    else:
        enrollment.tanggal_selesai = None
