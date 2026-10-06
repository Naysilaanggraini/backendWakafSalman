from extensions import db
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT


class Materi(db.Model):
    __tablename__ = "materi"
    __table_args__ = (
        db.UniqueConstraint("id_course", "urutan", name="uq_materi_urutan"),
        db.Index("idx_materi_course", "id_course"),
    )
    id_materi = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    id_course = db.Column(INTEGER(unsigned=True), db.ForeignKey("course.id_course", name="fk_materi_course", onupdate="CASCADE"), nullable=False)
    judul_materi = db.Column(db.String(150), nullable=False)
    jenis_file = db.Column(db.Enum("pdf", "youtube", "drive"), nullable=False)
    tautan_file = db.Column(db.String(500), nullable=False)
    durasi = db.Column(INTEGER(unsigned=True), nullable=True)
    urutan = db.Column(SMALLINT(unsigned=True), nullable=False, server_default="1")
    status = db.Column(db.Enum("aktif", "nonaktif"), nullable=False, server_default="aktif")
    tanggal_dibuat = db.Column(db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp())
    tanggal_diperbarui = db.Column(db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp(), server_onupdate=db.FetchedValue())
    course = db.relationship("Course", back_populates="materi")

    def to_dict(self):
        return {"id_materi": self.id_materi, "id_course": self.id_course,
                "judul_materi": self.judul_materi, "jenis_file": self.jenis_file,
                "tautan_file": self.tautan_file, "durasi": self.durasi,
                "urutan": self.urutan, "status": self.status,
                "tanggal_dibuat": self.tanggal_dibuat.isoformat() if self.tanggal_dibuat else None,
                "tanggal_diperbarui": self.tanggal_diperbarui.isoformat() if self.tanggal_diperbarui else None}
