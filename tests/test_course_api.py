"""Course API contracts with mocked sessions; no database writes."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
from flask import Flask
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects import mysql

from extensions import db
from models import User, Kategori, Course
from routes.course import course_bp


class CourseApiTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        self.secret = "course-test-secret-at-least-32-characters"
        app.config.update(TESTING=True, JWT_SECRET_KEY=self.secret)
        app.register_blueprint(course_bp)
        self.client = app.test_client()
        self.users = [User(id_user=1, role="admin", status="aktif"),
                      User(id_user=2, role="user", status="aktif"),
                      User(id_user=3, role="admin", status="nonaktif")]
        self.categories = [Kategori(id_kategori=1, nama_kategori="Aktif", status="aktif"),
                           Kategori(id_kategori=2, nama_kategori="Arsip", status="nonaktif")]
        self.items = [Course(id_course=1, judul_course="Wakaf", id_kategori=1, kategori=self.categories[0],
                             status="aktif", tanggal_dibuat=datetime(2026, 1, 1)),
                      Course(id_course=2, judul_course="Arsip", id_kategori=1, kategori=self.categories[0], status="nonaktif"),
                      Course(id_course=3, judul_course="Tersembunyi", id_kategori=2, kategori=self.categories[1], status="aktif")]
        self.session = MagicMock()
        self.session.get.side_effect = self.get_record
        self.session.execute.side_effect = self.execute_query
        self.session.add.side_effect = self.add_record
        patcher = patch.object(db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_record(self, model, ident):
        records, key = {User: (self.users, "id_user"), Kategori: (self.categories, "id_kategori"),
                        Course: (self.items, "id_course")}[model]
        return next((item for item in records if getattr(item, key) == ident), None)

    def execute_query(self, query):
        sql = str(query)
        restricted = "course.status =" in sql
        if restricted:
            self.assertIn("kategori.status =", sql)
            self.assertIn("EXISTS", sql)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [item for item in self.items if not restricted or
            (item.status == "aktif" and item.kategori.status == "aktif")]
        return result

    def add_record(self, item):
        item.id_course = 4
        self.items.append(item)

    def headers(self, ident=1, **claims):
        payload = {"id_user": ident, "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        payload.update(claims)
        return {"Authorization": "Bearer " + jwt.encode(payload, self.secret, algorithm="HS256")}

    def test_all_endpoints_require_authentication(self):
        for method, path in [("get", "/api/course"), ("get", "/api/course/1"), ("post", "/api/course"),
                             ("patch", "/api/course/1"), ("delete", "/api/course/1")]:
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(path).status_code, 401)
        self.session.commit.assert_not_called()

    def test_user_cannot_write_with_forged_admin_claim(self):
        for method, path in [("post", "/api/course"), ("patch", "/api/course/1"), ("delete", "/api/course/1")]:
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(path, headers=self.headers(2)).status_code, 403)
        self.session.commit.assert_not_called()

    def test_invalid_expired_and_inactive_tokens(self):
        for headers, expected in [({"Authorization": "Bearer invalid"}, 401),
                                  (self.headers(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), 401),
                                  (self.headers(3), 403)]:
            self.assertEqual(self.client.get("/api/course", headers=headers).status_code, expected)

    def test_list_course_visibility_and_empty_list(self):
        response = self.client.get("/api/course", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["course"]), 3)
        response = self.client.get("/api/course", headers=self.headers(2))
        self.assertEqual([item["id_course"] for item in response.json["course"]], [1])
        self.items.clear()
        self.assertEqual(self.client.get("/api/course", headers=self.headers()).json, {"course": []})

    def test_detail_course_and_hidden_courses(self):
        response = self.client.get("/api/course/1", headers=self.headers(2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["course"]["tanggal_dibuat"], "2026-01-01T00:00:00")
        self.assertIsNone(response.json["course"]["deskripsi"])
        for ident in (2, 3):
            self.assertEqual(self.client.get(f"/api/course/{ident}", headers=self.headers(2)).status_code, 404)
            self.assertEqual(self.client.get(f"/api/course/{ident}", headers=self.headers()).status_code, 200)

    def test_missing_and_invalid_course_ids(self):
        for method in ("get", "patch", "delete"):
            for ident in ("999", "0", "-1", "abc"):
                with self.subTest(method=method, ident=ident):
                    self.assertEqual(getattr(self.client, method)("/api/course/" + ident,
                        headers=self.headers(), json={"judul_course": "Baru"}).status_code, 404)
        self.session.commit.assert_not_called()

    def test_create_course_defaults_and_relationship(self):
        response = self.client.post("/api/course", headers=self.headers(),
            json={"judul_course": " Baru ", "id_kategori": 1, "deskripsi": " Isi "})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["course"]["judul_course"], "Baru")
        self.assertEqual(response.json["course"]["status"], "aktif")
        self.assertEqual(response.json["course"]["deskripsi"], "Isi")
        self.assertEqual(response.json["course"]["id_course"], 4)
        self.assertIs(self.items[-1].kategori, self.categories[0])
        self.assertNotIn("passing_grade", response.json["course"])

    def test_update_course_and_category(self):
        response = self.client.patch("/api/course/1", headers=self.headers(),
            json={"judul_course": "Diubah", "id_kategori": 2, "status": "nonaktif", "credit": "Salman"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["course"]["id_kategori"], 2)
        self.assertIs(self.items[0].kategori, self.categories[1])
        response = self.client.patch("/api/course/1", headers=self.headers(),
            json={"deskripsi": None, "key_point": None, "credit": None, "thumbnail": None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["course"]["judul_course"], "Diubah")
        self.assertIsNone(response.json["course"]["credit"])

    def test_missing_category_does_not_write(self):
        for method, path, payload in [("post", "/api/course", {"judul_course": "Baru", "id_kategori": 999}),
                                      ("patch", "/api/course/1", {"judul_course": "Diubah", "id_kategori": 999})]:
            response = getattr(self.client, method)(path, headers=self.headers(), json=payload)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json["message"], "Kategori tidak ditemukan")
        self.assertEqual(self.items[0].judul_course, "Wakaf")
        self.session.add.assert_not_called()
        self.session.commit.assert_not_called()

    def test_invalid_inputs_and_protected_fields(self):
        invalid = [{}, [], "text", {"judul_course": " "}, {"judul_course": None},
            {"judul_course": 7}, {"judul_course": "x" * 151}, {"credit": "x" * 151},
            {"thumbnail": "x" * 501}, {"deskripsi": 1}, {"key_point": []}, {"status": "invalid"},
            {"status": None}, {"deskripsi": "x" * 65536}, {"key_point": "界" * 21846}]
        invalid += [{"id_kategori": value} for value in (0, -1, True, 1.5, "1", None, 4294967296)]
        invalid += [{key: 1} for key in ("id_course", "tanggal_dibuat", "tanggal_diperbarui", "passing_grade",
                   "maksimal_attempt", "masa_tunggu_test_hari", "status_test", "test_dapat_diakses_lagi")]
        for method, path in [("post", "/api/course"), ("patch", "/api/course/1")]:
            for payload in invalid:
                with self.subTest(method=method, payload=str(payload)[:80]):
                    self.assertEqual(getattr(self.client, method)(path, headers=self.headers(), json=payload).status_code, 400)
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(),
                data="{invalid", content_type="application/json").status_code, 400)
        for payload in ({"judul_course": "Baru"}, {"id_kategori": 1}):
            self.assertEqual(self.client.post("/api/course", headers=self.headers(), json=payload).status_code, 400)
        self.session.commit.assert_not_called()

    def test_valid_length_boundaries(self):
        response = self.client.post("/api/course", headers=self.headers(), json={"judul_course": "x" * 150,
            "id_kategori": 1, "credit": "x" * 150, "thumbnail": "x" * 500,
            "deskripsi": "x" * 65535, "key_point": "界" * 21845})
        self.assertEqual(response.status_code, 201)

    def test_delete_course_only(self):
        response = self.client.delete("/api/course/1", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.session.delete.assert_called_once_with(self.items[0])
        self.session.commit.assert_called_once()
        self.session.execute.assert_not_called()

    def test_foreign_key_conflicts_rollback(self):
        for method, path, payload, code in [("post", "/api/course", {"judul_course": "Baru", "id_kategori": 1}, 1452),
            ("patch", "/api/course/1", {"id_kategori": 2}, 1452), ("delete", "/api/course/1", None, 1451)]:
            with self.subTest(method=method):
                self.session.commit.side_effect = IntegrityError("write", {}, Exception(code, "FK conflict"))
                response = getattr(self.client, method)(path, headers=self.headers(), json=payload)
                self.assertEqual(response.status_code, 409)
        self.assertEqual(self.session.rollback.call_count, 3)

    def test_unexpected_integrity_error_is_not_fk_conflict(self):
        self.session.commit.side_effect = IntegrityError("write", {}, Exception(1048, "Unexpected null"))
        with self.assertRaises(IntegrityError):
            self.client.post("/api/course", headers=self.headers(), json={"judul_course": "Baru", "id_kategori": 1})
        self.session.rollback.assert_called_once()

    def test_model_matches_schema_without_delete_cascade(self):
        table = Course.__table__
        self.assertEqual(set(table.columns.keys()), {"id_course", "judul_course", "deskripsi", "id_kategori",
            "key_point", "credit", "thumbnail", "passing_grade", "maksimal_attempt", "masa_tunggu_test_hari",
            "status", "tanggal_dibuat", "tanggal_diperbarui"})
        self.assertEqual(table.c.id_course.type.compile(dialect=mysql.dialect()), "INTEGER UNSIGNED")
        fk = next(iter(table.c.id_kategori.foreign_keys))
        self.assertEqual(fk.target_fullname, "kategori.id_kategori")
        self.assertEqual(fk.onupdate, "CASCADE")
        self.assertIsNone(fk.ondelete)
        self.assertEqual(table.c.passing_grade.server_default.arg, "70")
        self.assertEqual(table.c.maksimal_attempt.server_default.arg, "3")
        self.assertEqual(table.c.masa_tunggu_test_hari.server_default.arg, "7")
        self.assertNotIn("delete", Course.kategori.property.cascade)
        self.assertIsNotNone(table.c.tanggal_diperbarui.server_onupdate)


if __name__ == "__main__":
    unittest.main()
