from extensions import db
from sqlalchemy.dialects.mysql import BIGINT, INTEGER


ACTIVITY_TYPES = (
    "login", "buka_course", "buka_materi", "selesai_materi",
    "selesai_course", "mulai_test", "selesai_test",
    "logout", "buka_dashboard", "putar_video", "kirim_komentar", "sesi",
)


class Activity(db.Model):
    """Existing audit table; never a progress or scoring source.

    Existing domain foreign keys remain enforced by MySQL; reporting joins
    the shared course/material models without changing historic audit rows.
    """
    __tablename__ = "activity"

    id_activity = db.Column(BIGINT(unsigned=True).with_variant(db.Integer(), "sqlite"), primary_key=True, autoincrement=True)
    id_user = db.Column(INTEGER(unsigned=True), db.ForeignKey("users.id_user"), nullable=False)
    id_course = db.Column(INTEGER(unsigned=True))
    id_materi = db.Column(INTEGER(unsigned=True))
    id_penilaian = db.Column(INTEGER(unsigned=True))
    jenis_aktivitas = db.Column(db.Enum(*ACTIVITY_TYPES), nullable=False)
    durasi = db.Column(INTEGER(unsigned=True))
    waktu_dimulai = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    waktu_selesai = db.Column(db.DateTime)
    time_basis = db.Column(db.String(10))

    def to_dict(self):
        return {
            "id_activity": self.id_activity, "id_user": self.id_user,
            "id_course": self.id_course, "id_materi": self.id_materi,
            "id_penilaian": self.id_penilaian, "jenis_aktivitas": self.jenis_aktivitas,
            "durasi": self.durasi,
            "waktu_dimulai": self.waktu_dimulai.isoformat() + ('Z' if self.time_basis == 'UTC' else '') if self.waktu_dimulai else None,
            "waktu_selesai": self.waktu_selesai.isoformat() + ('Z' if self.time_basis == 'UTC' else '') if self.waktu_selesai else None,
            "time_basis": self.time_basis,
        }


class ActivityTracking(db.Model):
    """Heartbeat state separate from immutable legacy audit rows."""
    __tablename__ = 'activity_tracking'
    id_activity = db.Column(BIGINT(unsigned=True).with_variant(db.Integer(), 'sqlite'),
                            db.ForeignKey('activity.id_activity'), primary_key=True)
    request_id = db.Column(db.String(36), nullable=False, unique=True)
    last_seen = db.Column(db.DateTime, nullable=False)
    running = db.Column(db.Boolean, nullable=False, default=False)
    finished = db.Column(db.Boolean, nullable=False, default=False)
    credited_ms = db.Column(db.BigInteger, nullable=False, default=0)
    id_login_activity = db.Column(BIGINT(unsigned=True).with_variant(db.Integer(), 'sqlite'), db.ForeignKey('activity.id_activity'))
    activity = db.relationship('Activity', foreign_keys=[id_activity])
