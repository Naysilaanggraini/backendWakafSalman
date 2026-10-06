from extensions import db
from sqlalchemy.dialects.mysql import BIGINT, INTEGER


class UserCourse(db.Model):
    __tablename__ = "user_course"
    __table_args__ = (
        db.UniqueConstraint("id_user", "id_course", name="uq_user_course"),
        db.Index("idx_user_course_user", "id_user"), db.Index("idx_user_course_course", "id_course"),
        db.Index("idx_user_course_status", "status"), db.Index("idx_user_course_status_test", "status_test"),
        db.Index("idx_user_course_test_access", "test_dapat_diakses_lagi"),
    )
    id_user_course = db.Column(db.Integer().with_variant(BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)
    id_user = db.Column(INTEGER(unsigned=True), db.ForeignKey("users.id_user", name="fk_user_course_user", onupdate="CASCADE"), nullable=False)
    id_course = db.Column(INTEGER(unsigned=True), db.ForeignKey("course.id_course", name="fk_user_course_course", onupdate="CASCADE"), nullable=False)
    tanggal_mulai = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    tanggal_selesai = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum("belum_mulai", "berlangsung", "selesai"), nullable=False, server_default="belum_mulai")
    # Schema mapping only; Learning never writes assessment state.
    status_test = db.Column(db.Enum("aktif", "nonaktif", "lulus"), nullable=False, server_default="aktif")
    test_dapat_diakses_lagi = db.Column(db.DateTime, nullable=True)
    course = db.relationship("Course")

    def to_dict(self):
        return {"id_user_course": self.id_user_course, "id_user": self.id_user,
                "id_course": self.id_course, "status": self.status,
                "tanggal_mulai": self.tanggal_mulai.isoformat() if self.tanggal_mulai else None,
                "tanggal_selesai": self.tanggal_selesai.isoformat() if self.tanggal_selesai else None}
