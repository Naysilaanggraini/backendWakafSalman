from extensions import db
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT, TINYINT


class Course(db.Model):
    __tablename__ = "course"
    __table_args__ = (db.Index("idx_course_kategori", "id_kategori"),)

    id_course = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    judul_course = db.Column(db.String(150), nullable=False)
    deskripsi = db.Column(db.Text, nullable=True)
    id_kategori = db.Column(INTEGER(unsigned=True), db.ForeignKey(
        "kategori.id_kategori", name="fk_course_kategori", onupdate="CASCADE"), nullable=False)
    key_point = db.Column(db.Text, nullable=True)
    credit = db.Column(db.String(150), nullable=True)
    thumbnail = db.Column(db.String(500), nullable=True)
    # Existing schema fields; managed by the assessment developer, not this API.
    passing_grade = db.Column(TINYINT(unsigned=True).with_variant(db.SmallInteger(), "sqlite"), nullable=False, server_default="70")
    maksimal_attempt = db.Column(SMALLINT(unsigned=True), nullable=False, server_default="3")
    masa_tunggu_test_hari = db.Column(SMALLINT(unsigned=True), nullable=False, server_default="7")
    status = db.Column(db.Enum("aktif", "nonaktif"), nullable=False, server_default="aktif")
    tanggal_dibuat = db.Column(db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp())
    tanggal_diperbarui = db.Column(db.TIMESTAMP, nullable=False,
        server_default=db.func.current_timestamp(), server_onupdate=db.FetchedValue())
    kategori = db.relationship("Kategori", back_populates="courses")
    materi = db.relationship("Materi", back_populates="course", passive_deletes="all")

    questions = db.relationship("Question", back_populates="course", order_by="Question.urutan")

    def to_dict(self):
        return {
            "id_course": self.id_course,
            "judul_course": self.judul_course,
            "deskripsi": self.deskripsi,
            "id_kategori": self.id_kategori,
            "key_point": self.key_point,
            "credit": self.credit,
            "thumbnail": self.thumbnail,
            "status": self.status,
            "tanggal_dibuat": self.tanggal_dibuat.isoformat() if self.tanggal_dibuat else None,
            "tanggal_diperbarui": self.tanggal_diperbarui.isoformat() if self.tanggal_diperbarui else None,
        }
