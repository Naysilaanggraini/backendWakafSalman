from extensions import db
from sqlalchemy.dialects.mysql import BIGINT, INTEGER


class UserMateri(db.Model):
    __tablename__ = "user_materi"
    __table_args__ = (
        db.UniqueConstraint("id_user", "id_materi", name="uq_user_materi"),
        db.Index("idx_user_materi_user", "id_user"), db.Index("idx_user_materi_materi", "id_materi"),
        db.Index("idx_user_materi_status", "status"),
    )
    id_user_materi = db.Column(db.Integer().with_variant(BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)
    id_user = db.Column(INTEGER(unsigned=True), db.ForeignKey("users.id_user", name="fk_user_materi_user", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    id_materi = db.Column(INTEGER(unsigned=True), db.ForeignKey("materi.id_materi", name="fk_user_materi_materi", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    status = db.Column(db.Enum("belum_mulai", "berlangsung", "selesai"), nullable=False, server_default="belum_mulai")
    waktu_mulai = db.Column(db.DateTime, nullable=True)
    waktu_selesai = db.Column(db.DateTime, nullable=True)
    durasi = db.Column(INTEGER(unsigned=True), nullable=True)
    materi = db.relationship("Materi")

    def to_dict(self):
        return {"id_user_materi": self.id_user_materi, "id_user": self.id_user,
                "id_materi": self.id_materi, "status": self.status,
                "waktu_mulai": self.waktu_mulai.isoformat() if self.waktu_mulai else None,
                "waktu_selesai": self.waktu_selesai.isoformat() if self.waktu_selesai else None,
                "durasi": self.durasi}
