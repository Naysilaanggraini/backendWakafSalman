from extensions import db
from sqlalchemy.dialects.mysql import BIGINT, INTEGER


ACTIVITY_TYPES = (
    "login", "buka_course", "buka_materi", "selesai_materi",
    "selesai_course", "mulai_test", "selesai_test",
)


class Activity(db.Model):
    """Existing audit table; never a progress or scoring source.

    Domain foreign keys remain enforced by MySQL. Their ORM relationships
    are deferred until Dev 2/3 models exist; no placeholder domain tables.
    """
    __tablename__ = "activity"

    id_activity = db.Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    id_user = db.Column(INTEGER(unsigned=True), db.ForeignKey("users.id_user"), nullable=False)
    id_course = db.Column(INTEGER(unsigned=True))
    id_materi = db.Column(INTEGER(unsigned=True))
    id_penilaian = db.Column(INTEGER(unsigned=True))
    jenis_aktivitas = db.Column(db.Enum(*ACTIVITY_TYPES), nullable=False)
    durasi = db.Column(INTEGER(unsigned=True))
    waktu_dimulai = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    waktu_selesai = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id_activity": self.id_activity, "id_user": self.id_user,
            "id_course": self.id_course, "id_materi": self.id_materi,
            "id_penilaian": self.id_penilaian, "jenis_aktivitas": self.jenis_aktivitas,
            "durasi": self.durasi,
            "waktu_dimulai": self.waktu_dimulai.isoformat() if self.waktu_dimulai else None,
            "waktu_selesai": self.waktu_selesai.isoformat() if self.waktu_selesai else None,
        }
