"""Mappings of the existing learning tables; a course owns one final test."""
from datetime import datetime, timezone
from sqlalchemy.dialects.mysql import INTEGER, BIGINT
from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


ID = db.Integer().with_variant(INTEGER(unsigned=True), "mysql")
BIG_ID = db.Integer().with_variant(BIGINT(unsigned=True), "mysql")


# Reuse the complete Learning mappings so every API shares one ORM identity.
from .course import Course
from .materi import Materi as Material
from .user_course import UserCourse as Enrollment
from .user_materi import UserMateri as MaterialProgress


class Question(db.Model):
    __tablename__ = "soal"
    id_soal = db.Column(ID, primary_key=True)
    id_course = db.Column(ID, db.ForeignKey("course.id_course"), nullable=False)
    pertanyaan = db.Column(db.Text, nullable=False)
    urutan = db.Column(db.SmallInteger, nullable=False, default=1)
    status = db.Column(db.Enum("aktif", "nonaktif"), nullable=False, default="aktif")
    course = db.relationship("Course", back_populates="questions")
    options = db.relationship("Option", back_populates="question", order_by="Option.urutan")


class Option(db.Model):
    __tablename__ = "pilihan_soal"
    id_pilihan = db.Column(ID, primary_key=True)
    id_soal = db.Column(ID, db.ForeignKey("soal.id_soal"), nullable=False)
    teks_pilihan = db.Column(db.String(255), nullable=False)
    urutan = db.Column(db.SmallInteger, nullable=False, default=1)
    is_benar = db.Column(db.Boolean, nullable=False, default=False)
    question = db.relationship("Question", back_populates="options")


class TestAttempt(db.Model):
    __tablename__ = "penilaian"
    id_penilaian = db.Column(ID, primary_key=True)
    id_user = db.Column(ID, db.ForeignKey("users.id_user"), nullable=False)
    id_course = db.Column(ID, db.ForeignKey("course.id_course"), nullable=False)
    nilai = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    test_attempt = db.Column(db.SmallInteger, nullable=False)
    status = db.Column(db.Enum("lulus", "tidak_lulus"), nullable=False, default="tidak_lulus")
    waktu_mulai = db.Column(db.DateTime, nullable=False, default=utcnow)
    waktu_selesai = db.Column(db.DateTime)
    durasi = db.Column(ID)
    status_attempt = db.Column(db.Enum("in_progress", "completed"), nullable=False, default="in_progress")
    # Private snapshot freezes the test and grading policy at start, including keys.
    question_snapshot = db.Column(db.JSON)
    passing_grade = db.Column(db.SmallInteger)
    user = db.relationship("User")
    course = db.relationship("Course")
    answers = db.relationship("UserAnswer", back_populates="attempt")
    __table_args__ = (db.UniqueConstraint("id_user", "id_course", "test_attempt", name="uq_penilaian_attempt"),)


class UserAnswer(db.Model):
    __tablename__ = "jawaban"
    id_jawaban = db.Column(BIG_ID, primary_key=True)
    id_penilaian = db.Column(ID, db.ForeignKey("penilaian.id_penilaian"), nullable=False)
    id_user = db.Column(ID, db.ForeignKey("users.id_user"), nullable=False)
    id_soal = db.Column(ID, db.ForeignKey("soal.id_soal"), nullable=False)
    id_pilihan = db.Column(ID, db.ForeignKey("pilihan_soal.id_pilihan"), nullable=False)
    benar = db.Column(db.Boolean, nullable=False, default=False)
    waktu_jawab = db.Column(db.DateTime, nullable=False, default=utcnow)
    attempt = db.relationship("TestAttempt", back_populates="answers")
    question = db.relationship("Question")
    option = db.relationship("Option")
    __table_args__ = (db.UniqueConstraint("id_penilaian", "id_soal", name="uq_jawaban_soal"),)


class Discussion(db.Model):
    __tablename__ = "discussion"
    id_discussion = db.Column(ID, primary_key=True)
    id_user = db.Column(ID, db.ForeignKey("users.id_user"), nullable=False)
    id_course = db.Column(ID, db.ForeignKey("course.id_course"), nullable=False)
    id_materi = db.Column(ID, db.ForeignKey("materi.id_materi"))
    id_parent = db.Column(ID, db.ForeignKey("discussion.id_discussion"))
    isi_komentar = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum("tampil", "disembunyikan"), nullable=False, default="tampil")
    waktu = db.Column(db.DateTime, nullable=False, default=utcnow)
    context_type = db.Column(db.Enum("course", "material", "test"), nullable=False)
    tanggal_diperbarui = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    user = db.relationship("User")
    course = db.relationship("Course")
    material = db.relationship("Materi")
    parent = db.relationship("Discussion", remote_side=[id_discussion])
