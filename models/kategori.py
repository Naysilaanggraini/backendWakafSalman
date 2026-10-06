from extensions import db
from sqlalchemy.dialects.mysql import INTEGER


class Kategori(db.Model):
    __tablename__ = "kategori"
    __table_args__ = (db.UniqueConstraint("nama_kategori", name="uq_kategori_nama"),)

    id_kategori = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    nama_kategori = db.Column(db.String(100), nullable=False)
    thumbnail = db.Column(db.String(255), nullable=True)
    status = db.Column(db.Enum("aktif", "nonaktif"), nullable=False, server_default="aktif")
    tanggal_dibuat = db.Column(db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp())
    tanggal_diperbarui = db.Column(
        db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp(),
        server_onupdate=db.FetchedValue(),
    )

    courses = db.relationship("Course", back_populates="kategori", passive_deletes="all")

    def to_dict(self):
        return {
            "id_kategori": self.id_kategori,
            "nama_kategori": self.nama_kategori,
            "thumbnail": self.thumbnail,
            "status": self.status,
            "tanggal_dibuat": self.tanggal_dibuat.isoformat() if self.tanggal_dibuat else None,
            "tanggal_diperbarui": self.tanggal_diperbarui.isoformat() if self.tanggal_diperbarui else None,
        }
