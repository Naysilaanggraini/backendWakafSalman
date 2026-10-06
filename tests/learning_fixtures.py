"""Shared Learning fixtures: real model objects, mocked database session."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import jwt
from flask import Flask
from extensions import db
from models import User, Kategori, Course, Materi


class LearningApiCase(unittest.TestCase):
    blueprints = ()

    def setUp(self):
        self.secret = "learning-test-secret-at-least-32-characters"
        app = Flask(__name__)
        app.config.update(TESTING=True, JWT_SECRET_KEY=self.secret)
        for blueprint in self.blueprints:
            app.register_blueprint(blueprint)
        self.client = app.test_client()
        self.users = [User(id_user=1, role="admin", status="aktif"), User(id_user=2, role="user", status="aktif"),
                      User(id_user=3, role="user", status="aktif"), User(id_user=4, role="user", status="nonaktif")]
        self.kategori = Kategori(id_kategori=1, nama_kategori="Wakaf", status="aktif")
        self.course = Course(id_course=1, id_kategori=1, kategori=self.kategori, judul_course="Dasar", status="aktif")
        self.materi = [Materi(id_materi=i, id_course=1, course=self.course, judul_materi=f"Materi {i}",
                             jenis_file="pdf", tautan_file="https://example.com/file.pdf", urutan=i,
                             status="aktif" if i <= 2 else "nonaktif") for i in (1, 2, 3)]
        self.records = {User: self.users, Kategori: [self.kategori], Course: [self.course], Materi: self.materi}
        self.session = MagicMock()
        self.session.get.side_effect = self.get_record
        self.session.add.side_effect = self.add_record
        patcher = patch.object(db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_record(self, model, ident):
        key = {User: "id_user", Kategori: "id_kategori", Course: "id_course", Materi: "id_materi"}.get(model)
        if key is None:
            key = "id_" + model.__tablename__
        return next((record for record in self.records.get(model, []) if getattr(record, key) == ident), None)

    def add_record(self, record):
        key = "id_" + record.__tablename__
        items = self.records.setdefault(type(record), [])
        if getattr(record, key) is None:
            setattr(record, key, len(items) + 10)
        items.append(record)

    def headers(self, ident=2):
        token = jwt.encode({"id_user": ident, "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           self.secret, algorithm="HS256")
        return {"Authorization": "Bearer " + token}
