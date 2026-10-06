"""Kategori API contract tests with mocked database sessions."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
from flask import Flask
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects import mysql

from extensions import db
from models import User, Kategori
from routes.kategori import kategori_bp


class KategoriApiTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, JWT_SECRET_KEY="kategori-test-secret-at-least-32-characters")
        app.register_blueprint(kategori_bp)
        self.client = app.test_client()
        self.admin = User(id_user=1, role="admin", status="aktif")
        self.user = User(id_user=2, role="user", status="aktif")
        self.inactive = User(id_user=3, role="admin", status="nonaktif")
        self.items = [Kategori(id_kategori=1, nama_kategori="Wakaf", status="aktif",
                               tanggal_dibuat=datetime(2026, 1, 1), tanggal_diperbarui=datetime(2026, 1, 2)),
                      Kategori(id_kategori=2, nama_kategori="Arsip", status="nonaktif")]
        self.session = MagicMock()
        self.session.get.side_effect = self.get_record
        self.session.execute.side_effect = self.execute_query
        self.session.add.side_effect = self.add_record
        patcher = patch.object(db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_record(self, model, ident):
        records = [self.admin, self.user, self.inactive] if model is User else self.items
        key = "id_user" if model is User else "id_kategori"
        return next((item for item in records if getattr(item, key) == ident), None)

    def execute_query(self, query):
        result = MagicMock()
        active_only = "kategori.status =" in str(query)
        result.scalars.return_value.all.return_value = [
            item for item in self.items if not active_only or item.status == "aktif"
        ]
        return result

    def add_record(self, item):
        item.id_kategori = 3
        self.items.append(item)

    def headers(self, ident=1, **claims):
        payload = {"id_user": ident, "role": "admin",
                   "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        payload.update(claims)
        token = jwt.encode(payload, "kategori-test-secret-at-least-32-characters", algorithm="HS256")
        return {"Authorization": "Bearer " + token}

    def test_all_endpoints_require_authentication(self):
        for method, path in [("get", "/api/kategori"), ("get", "/api/kategori/1"),
                             ("post", "/api/kategori"), ("patch", "/api/kategori/1"),
                             ("delete", "/api/kategori/1")]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 401)
        self.session.commit.assert_not_called()

    def test_invalid_expired_and_inactive_tokens(self):
        for headers, expected in [({"Authorization": "Bearer invalid"}, 401),
                                  ({"Authorization": "invalid"}, 401),
                                  (self.headers(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), 401),
                                  (self.headers(3), 403)]:
            with self.subTest(expected=expected):
                self.assertEqual(self.client.get("/api/kategori", headers=headers).status_code, expected)

    def test_user_cannot_write_even_with_admin_claim(self):
        for method, path in [("post", "/api/kategori"), ("patch", "/api/kategori/1"),
                             ("delete", "/api/kategori/1")]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(path, headers=self.headers(2))
                self.assertEqual(response.status_code, 403)
        self.session.commit.assert_not_called()

    def test_list_and_detail_visibility_and_serialization(self):
        response = self.client.get("/api/kategori", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["kategori"]), 2)
        response = self.client.get("/api/kategori", headers=self.headers(2))
        self.assertEqual(len(response.json["kategori"]), 1)
        response = self.client.get("/api/kategori/1", headers=self.headers(2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["kategori"]["tanggal_dibuat"], "2026-01-01T00:00:00")
        self.assertIsNone(response.json["kategori"]["thumbnail"])
        self.assertEqual(self.client.get("/api/kategori/2", headers=self.headers(2)).status_code, 404)
        self.assertEqual(self.client.get("/api/kategori/2", headers=self.headers()).status_code, 200)
        self.items.clear()
        self.assertEqual(self.client.get("/api/kategori", headers=self.headers()).json, {"kategori": []})

    def test_missing_and_invalid_ids(self):
        for method in ("get", "patch", "delete"):
            for ident in ("999", "0", "-1", "abc"):
                with self.subTest(method=method, ident=ident):
                    response = getattr(self.client, method)("/api/kategori/" + ident,
                                                           headers=self.headers(), json={"nama_kategori": "Baru"})
                    self.assertEqual(response.status_code, 404)
        self.session.commit.assert_not_called()

    def test_create_defaults_and_update(self):
        response = self.client.post("/api/kategori", headers=self.headers(), json={"nama_kategori": " Baru "})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["kategori"]["nama_kategori"], "Baru")
        self.assertEqual(response.json["kategori"]["status"], "aktif")
        self.assertEqual(response.json["kategori"]["id_kategori"], 3)
        response = self.client.patch("/api/kategori/1", headers=self.headers(),
                                     json={"thumbnail": "https://example.com/a.png", "status": "nonaktif"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["kategori"]["nama_kategori"], "Wakaf")
        self.assertEqual(response.json["kategori"]["status"], "nonaktif")
        response = self.client.patch("/api/kategori/1", headers=self.headers(), json={"thumbnail": None})
        self.assertIsNone(response.json["kategori"]["thumbnail"])

    def test_invalid_input_for_create_and_update(self):
        invalid = [{}, [], "text", {"nama_kategori": " "}, {"nama_kategori": None},
                   {"nama_kategori": 12}, {"nama_kategori": "x" * 101},
                   {"status": "invalid"}, {"status": None}, {"thumbnail": 123},
                   {"thumbnail": "x" * 256}, {"id_kategori": 9},
                   {"tanggal_dibuat": "2026-01-01"}, {"tanggal_diperbarui": "2026-01-01"}]
        for method, path in [("post", "/api/kategori"), ("patch", "/api/kategori/1")]:
            for data in invalid:
                with self.subTest(method=method, data=data):
                    response = getattr(self.client, method)(path, headers=self.headers(), json=data)
                    self.assertEqual(response.status_code, 400)
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(),
                             data="{invalid", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/kategori", headers=self.headers(),
                                         json={"thumbnail": None}).status_code, 400)
        self.session.commit.assert_not_called()

    def test_valid_maximum_lengths(self):
        response = self.client.post("/api/kategori", headers=self.headers(),
                                    json={"nama_kategori": "x" * 100, "thumbnail": "x" * 255, "status": "nonaktif"})
        self.assertEqual(response.status_code, 201)

    def test_duplicate_name_create_and_update_roll_back(self):
        self.session.commit.side_effect = IntegrityError("write", {}, Exception(1062, "Duplicate entry"))
        for method, path in [("post", "/api/kategori"), ("patch", "/api/kategori/1")]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(path, headers=self.headers(), json={"nama_kategori": "WAKAF"})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json["message"], "Nama kategori sudah terdaftar")
        self.assertEqual(self.session.rollback.call_count, 2)

    def test_delete_and_foreign_key_conflict(self):
        response = self.client.delete("/api/kategori/1", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.session.delete.assert_called_once_with(self.items[0])
        self.session.commit.side_effect = IntegrityError("delete", {}, Exception(1451, "Referenced row"))
        response = self.client.delete("/api/kategori/1", headers=self.headers())
        self.assertEqual(response.status_code, 409)
        self.session.rollback.assert_called_once()

    def test_unexpected_integrity_error_is_not_reported_as_duplicate(self):
        self.session.commit.side_effect = IntegrityError("insert", {}, Exception(1048, "Unexpected null"))
        with self.assertRaises(IntegrityError):
            self.client.post("/api/kategori", headers=self.headers(), json={"nama_kategori": "Baru"})
        self.session.rollback.assert_called_once()

    def test_model_matches_schema(self):
        table = Kategori.__table__
        self.assertEqual(set(table.columns.keys()), {"id_kategori", "nama_kategori", "thumbnail", "status",
                                                    "tanggal_dibuat", "tanggal_diperbarui"})
        self.assertTrue(table.c.id_kategori.type.unsigned)
        self.assertEqual(table.c.id_kategori.type.compile(dialect=mysql.dialect()), "INTEGER UNSIGNED")
        self.assertTrue(any(constraint.name == "uq_kategori_nama" for constraint in table.constraints))
        self.assertEqual(table.c.nama_kategori.type.length, 100)
        self.assertEqual(table.c.thumbnail.type.length, 255)
        self.assertEqual(table.c.status.type.enums, ["aktif", "nonaktif"])
        self.assertIsNotNone(table.c.tanggal_diperbarui.server_onupdate)


if __name__ == "__main__":
    unittest.main()
