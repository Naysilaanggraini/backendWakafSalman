from datetime import datetime, timezone

from extensions import db
from models.activity import Activity, ACTIVITY_TYPES


def record_activity(actor_id, kind, *, id_course=None, id_materi=None,
                    id_penilaian=None, durasi=None, waktu_dimulai=None,
                    waktu_selesai=None):
    """Stage an audit event in the caller's transaction, without commit.

    Trusted backend callers must validate domain ownership/permissions first.
    API callers must validate actor/context; only schema-supported events are accepted.
    """
    if kind not in ACTIVITY_TYPES:
        raise ValueError("Jenis aktivitas belum didukung schema")
    for name, value in (("id_user", actor_id), ("id_course", id_course),
                        ("id_materi", id_materi), ("id_penilaian", id_penilaian)):
        if value is None and name != "id_user":
            continue
        if type(value) is not int or not 0 < value <= 4294967295:
            raise ValueError(f"{name} harus berupa ID positif")
    if durasi is not None and (type(durasi) is not int or not 0 <= durasi <= 4294967295):
        raise ValueError("Durasi harus berupa detik nonnegatif")
    start = waktu_dimulai if waktu_dimulai is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    if not isinstance(start, datetime) or start.tzinfo is not None:
        raise ValueError("Waktu event baru harus datetime UTC tanpa tzinfo, sesuai kolom database")
    if waktu_selesai is not None:
        if not isinstance(waktu_selesai, datetime) or waktu_selesai.tzinfo is not None or waktu_selesai < start:
            raise ValueError("Waktu selesai tidak valid")
    event = Activity(id_user=actor_id, jenis_aktivitas=kind, id_course=id_course,
                     id_materi=id_materi, id_penilaian=id_penilaian, durasi=durasi,
                     waktu_dimulai=start, waktu_selesai=waktu_selesai, time_basis='UTC')
    db.session.add(event)
    return event
