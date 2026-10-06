from datetime import datetime
from unittest.mock import MagicMock
from sqlalchemy.exc import IntegrityError
from learning_fixtures import LearningApiCase
from models import UserCourse
from routes.enrollment import enrollment_bp


class EnrollmentApiTests(LearningApiCase):
    blueprints = (enrollment_bp,)

    def setUp(self):
        super().setUp()
        self.enrollments = [UserCourse(id_user_course=1, id_user=2, id_course=1, course=self.course,
                                      status="belum_mulai", tanggal_mulai=datetime(2026, 1, 1)),
                            UserCourse(id_user_course=2, id_user=3, id_course=1, course=self.course, status="selesai")]
        self.records[UserCourse] = self.enrollments
        self.session.execute.side_effect = self.query

    def query(self, query):
        result = MagicMock()
        params = query.compile().params
        ident = params.get("id_user_1")
        self.assertIsNotNone(ident, "Enrollment reads must be scoped by authenticated user")
        items = [e for e in self.enrollments if e.id_user == ident]
        if "id_user_course_1" in params:
            items = [e for e in items if e.id_user_course == params["id_user_course_1"]]
        if "id_course_1" in params:
            items = [e for e in items if e.id_course == params["id_course_1"]]
        result.scalar_one_or_none.return_value = items[0] if items else None
        result.scalars.return_value.all.return_value = items
        return result

    def test_enroll_self_with_server_defaults(self):
        response = self.client.post("/api/course/1/enrollment", headers=self.headers(1))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["enrollment"]["id_user"], 1)
        self.assertEqual(response.json["enrollment"]["status"], "belum_mulai")
        new = self.enrollments[-1]
        self.assertNotIn("tanggal_mulai", new.__dict__)
        self.assertNotIn("status_test", new.__dict__)
        self.assertNotIn("test_dapat_diakses_lagi", new.__dict__)
        self.session.commit.assert_called_once()

    def test_duplicate_precheck_and_database_race(self):
        self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers()).status_code, 409)
        self.session.add.assert_not_called()
        self.session.commit.side_effect = IntegrityError("insert", {}, Exception(1062, "duplicate"))
        self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers(1)).status_code, 409)
        self.session.rollback.assert_called_once()

    def test_missing_and_inactive_course(self):
        self.assertEqual(self.client.post("/api/course/999/enrollment", headers=self.headers()).status_code, 404)
        for parent in (self.course, self.kategori):
            parent.status = "nonaktif"
            self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers()).status_code, 403)
            parent.status = "aktif"
        self.session.commit.assert_not_called()

    def test_no_client_fields_or_malformed_body(self):
        for key in ("id_user", "id_course", "status", "status_test", "test_dapat_diakses_lagi",
                    "tanggal_mulai", "tanggal_selesai", "id_user_course"):
            self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers(1), json={key: 3}).status_code, 400)
        self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers(1),
            data="{bad", content_type="application/json").status_code, 400)
        self.session.commit.assert_not_called()

    def test_list_and_detail_only_owned_enrollments(self):
        response = self.client.get("/api/me/enrollments", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id_user"] for item in response.json["enrollments"]], [2])
        self.assertEqual(self.client.get("/api/me/enrollments/1", headers=self.headers()).status_code, 200)
        self.assertEqual(self.client.get("/api/me/enrollments/2", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.get("/api/me/enrollments/999", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.get("/api/me/enrollments", headers=self.headers(1)).json, {"enrollments": []})

    def test_authentication_and_inactive_user(self):
        for method, path in (("post", "/api/course/1/enrollment"), ("get", "/api/me/enrollments"),
                             ("get", "/api/me/enrollments/1")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 401)
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(4)).status_code, 403)

    def test_fk_conflict(self):
        self.session.commit.side_effect = IntegrityError("insert", {}, Exception(1452, "FK"))
        self.assertEqual(self.client.post("/api/course/1/enrollment", headers=self.headers(1)).status_code, 409)
        self.session.rollback.assert_called_once()

    def test_schema_and_no_mutation_endpoints(self):
        table = UserCourse.__table__
        self.assertTrue(table.c.id_user_course.type.unsigned)
        self.assertTrue(any(c.name == "uq_user_course" for c in table.constraints))
        self.assertEqual(table.c.status_test.type.enums, ["aktif", "nonaktif", "lulus"])
        self.assertIsNotNone(table.c.tanggal_mulai.server_default)
        for method in ("patch", "delete"):
            self.assertEqual(getattr(self.client, method)("/api/me/enrollments/1", headers=self.headers()).status_code, 405)

    def test_unexpected_constraint_returns_safe_message(self):
        self.session.commit.side_effect = IntegrityError("write", {}, Exception(1048, "PRIVATE_DATABASE_DETAIL"))
        response = self.client.post("/api/course/1/enrollment", headers=self.headers(1))
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("PRIVATE_DATABASE_DETAIL", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()
