from extensions import db
from sqlalchemy.dialects.mysql import BIGINT, INTEGER


class UserProfile(db.Model):
    """Mapping tabel existing; tidak membuat atau mengubah schema."""
    __tablename__ = "user_profile"

    id_profile = db.Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    id_user = db.Column(INTEGER(unsigned=True), db.ForeignKey("users.id_user"), nullable=False, unique=True)
    no_hp = db.Column(db.String(30), nullable=True)
    tanggal_diperbarui = db.Column(db.TIMESTAMP, nullable=False, server_default=db.func.current_timestamp(), server_onupdate=db.FetchedValue())
    user = db.relationship("User", back_populates="user_profile")
