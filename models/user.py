from extensions import db
from flask import has_request_context, request


class User(db.Model):
    __tablename__ = "users"

    def to_dict(self):
        """Public account fields; never expose the password hash."""
        return {
            "id_user": self.id_user,
            "nama": self.nama,
            "email": self.email,
            "divisi": self.divisi,
            "jabatan": self.jabatan,
            "role": self.role,
            "status": self.status,
            "foto_profil": (request.host_url.rstrip("/") + self.foto_profil
                            if self.foto_profil and self.foto_profil.startswith("/api/auth/profile-photos/") and has_request_context()
                            else self.foto_profil),
            "tanggal_dibuat": self.tanggal_dibuat.isoformat() if self.tanggal_dibuat else None,
            "terakhir_login": self.terakhir_login.isoformat() if self.terakhir_login else None,
        }

    id_user = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    nama = db.Column(
        db.String(150),
        nullable=False
    )

    email = db.Column(
        db.String(150),
        nullable=False,
        unique=True
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    divisi = db.Column(
        db.String(100),
        nullable=True
    )

    jabatan = db.Column(
        db.String(100),
        nullable=True
    )

    role = db.Column(
        db.Enum("admin", "user"),
        nullable=False,
        default="user"
    )

    status = db.Column(
        db.Enum("aktif", "nonaktif"),
        nullable=False,
        default="aktif"
    )

    foto_profil = db.Column(
        db.String(500),
        nullable=True
    )

    tanggal_dibuat = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    terakhir_login = db.Column(
        db.DateTime,
        nullable=True
    )
