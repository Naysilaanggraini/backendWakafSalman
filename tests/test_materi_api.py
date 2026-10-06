from sqlalchemy.exc import IntegrityError
from learning_fixtures import LearningApiCase
from models import Materi
from routes.materi import materi_bp


class MateriApiTests(LearningApiCase):
    blueprints = (materi_bp,)

    def setUp(self):
        super().setUp()
        self.session.execute.side_effect = self.query

    def query(self, query):
        from unittest.mock import MagicMock
        result = MagicMock()
        self.assertIn("ORDER BY materi.urutan", str(query))
        result.scalars.return_value.all.return_value = [m for m in self.materi if
            "materi.status =" not in str(query) or m.status == "aktif"]
        return result

    def test_list_sorted_and_active_filter(self):
        for ident, total in ((1, 3), (2, 2)):
            response = self.client.get("/api/course/1/materi", headers=self.headers(ident))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["materi"]), total)
            self.assertEqual([m["urutan"] for m in response.json["materi"]], list(range(1, total + 1)))

    def test_detail_and_visibility_of_parent(self):
        self.assertEqual(self.client.get("/api/materi/1", headers=self.headers()).status_code, 200)
        self.assertEqual(self.client.get("/api/materi/3", headers=self.headers()).status_code, 404)
        for parent in (self.course, self.kategori):
            parent.status = "nonaktif"
            self.assertEqual(self.client.get("/api/materi/1", headers=self.headers()).status_code, 404)
            self.assertEqual(self.client.get("/api/course/1/materi", headers=self.headers()).status_code, 404)
            self.assertEqual(self.client.get("/api/materi/1", headers=self.headers(1)).status_code, 200)
            parent.status = "aktif"

    def test_create_update_delete(self):
        response = self.client.post("/api/course/1/materi", headers=self.headers(1), json={
            "judul_materi": " Baru ", "jenis_file": "youtube", "tautan_file": "https://example.com/video"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["materi"]["judul_materi"], "Baru")
        self.assertEqual(response.json["materi"]["id_course"], 1)
        self.assertEqual(response.json["materi"]["urutan"], 1)
        response = self.client.patch("/api/materi/1", headers=self.headers(1), json={"urutan": 8, "durasi": 100, "status": "nonaktif"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["materi"]["durasi"], 100)
        self.assertEqual(self.client.delete("/api/materi/1", headers=self.headers(1)).status_code, 200)
        self.session.delete.assert_called_once_with(self.materi[0])

    def test_authentication_and_admin_authorization(self):
        for method, path in (("get", "/api/course/1/materi"), ("get", "/api/materi/1"),
                             ("post", "/api/course/1/materi"), ("patch", "/api/materi/1"), ("delete", "/api/materi/1")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 401)
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(4)).status_code, 403)
            if method != "get":
                self.assertEqual(getattr(self.client, method)(path, headers=self.headers()).status_code, 403)
        self.session.commit.assert_not_called()

    def test_not_found(self):
        for method, path in (("get", "/api/course/999/materi"), ("post", "/api/course/999/materi"),
                             ("get", "/api/materi/999"), ("patch", "/api/materi/999"), ("delete", "/api/materi/999")):
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(1), json={
                "judul_materi": "A", "jenis_file": "pdf", "tautan_file": "file.pdf"}).status_code, 404)

    def test_invalid_inputs_and_protected_fields(self):
        invalid = [{}, [], {"judul_materi": " "}, {"judul_materi": "x" * 151}, {"judul_materi": None},
                   {"jenis_file": "doc"}, {"tautan_file": ""}, {"tautan_file": "x" * 501}, {"status": "bad"},
                   {"durasi": -1}, {"durasi": True}, {"durasi": 4294967296}, {"urutan": 65536}, {"urutan": None},
                   {"id_course": 2}, {"id_materi": 2}, {"tanggal_dibuat": "x"}, {"tanggal_diperbarui": "x"}]
        for method, path in (("post", "/api/course/1/materi"), ("patch", "/api/materi/1")):
            for data in invalid:
                with self.subTest(method=method, data=data):
                    self.assertEqual(getattr(self.client, method)(path, headers=self.headers(1), json=data).status_code, 400)
        self.session.commit.assert_not_called()

    def test_duplicate_and_fk_conflict(self):
        for method, path, code in (("post", "/api/course/1/materi", 1062), ("patch", "/api/materi/1", 1062),
                                   ("delete", "/api/materi/1", 1451)):
            self.session.commit.side_effect = IntegrityError("write", {}, Exception(code, "constraint"))
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(1), json={
                "judul_materi": "A", "jenis_file": "drive", "tautan_file": "file"}).status_code, 409)
        self.assertEqual(self.session.rollback.call_count, 3)

    def test_schema_and_numeric_boundaries(self):
        fk = next(iter(Materi.__table__.c.id_course.foreign_keys))
        self.assertIsNone(fk.ondelete)
        self.assertEqual(fk.onupdate, "CASCADE")
        self.assertTrue(any(c.name == "uq_materi_urutan" for c in Materi.__table__.constraints))
        response = self.client.patch("/api/materi/1", headers=self.headers(1), json={"durasi": 4294967295, "urutan": 65535})
        self.assertEqual(response.status_code, 200)

    def test_unexpected_constraint_returns_safe_message(self):
        self.session.commit.side_effect = IntegrityError("write", {}, Exception(1048, "PRIVATE_DATABASE_DETAIL"))
        response = self.client.patch("/api/materi/1", headers=self.headers(1), json={"judul_materi": "Baru"})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("PRIVATE_DATABASE_DETAIL", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()
