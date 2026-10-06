from datetime import datetime
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import IntegrityError, OperationalError
from learning_fixtures import LearningApiCase
from models import Materi, UserCourse, UserMateri
from routes.progress import progress_bp


class ProgressApiTests(LearningApiCase):
    blueprints = (progress_bp,)

    def setUp(self):
        super().setUp()
        self.enrollment = UserCourse(id_user_course=1, id_user=2, id_course=1, course=self.course,
            status="belum_mulai", status_test="lulus", test_dapat_diakses_lagi=datetime(2027, 1, 1))
        self.enrollments = [self.enrollment]
        self.progress = [UserMateri(id_user_materi=1, id_user=3, id_materi=1, materi=self.materi[0], status="selesai")]
        self.records[UserCourse] = self.enrollments
        self.records[UserMateri] = self.progress
        self.session.execute.side_effect = self.query
        self.now = datetime(2026, 10, 5, 12, 30)
        self.clock = patch("routes.progress.datetime")
        clock = self.clock.start()
        clock.now.return_value = self.now
        self.addCleanup(self.clock.stop)

    def query(self, query):
        result = MagicMock()
        entity = query.column_descriptions[0]["entity"]
        params = query.compile().params
        ident = params.get("id_user_1")
        self.assertIsNotNone(ident, "Progress queries must be scoped to token user")
        if entity is UserCourse:
            items = [e for e in self.enrollments if e.id_user == ident and e.id_course == params["id_course_1"]]
            result.scalar_one_or_none.return_value = items[0] if items else None
        elif entity is UserMateri:
            items = [p for p in self.progress if p.id_user == ident and p.id_materi == params["id_materi_1"]]
            result.scalar_one_or_none.return_value = items[0] if items else None
        elif entity is Materi:
            self.assertIn("LEFT OUTER JOIN user_materi", str(query))
            self.assertIn("materi.status =", str(query))
            rows = [(m, next((p for p in self.progress if p.id_user == ident and p.id_materi == m.id_materi), None))
                for m in self.materi if m.id_course == params["id_course_1"] and m.status == "aktif"]
            result.all.return_value = rows
        else:
            self.fail("Unexpected query")
        return result

    def update(self, ident=1, **values):
        return self.client.patch(f"/api/me/materi/{ident}/progress", headers=self.headers(), json=values)

    def own_progress(self, ident=1):
        return next(p for p in self.progress if p.id_user == 2 and p.id_materi == ident)

    def test_get_virtual_state_without_writes_and_other_user_progress(self):
        response = self.client.get("/api/me/materi/1/progress", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["status"], "belum_mulai")
        self.assertEqual(response.json["progress"]["id_user"], 2)
        self.assertIsNone(response.json["progress"]["id_user_materi"])
        self.session.add.assert_not_called()
        self.session.commit.assert_not_called()

    def test_start_progress_and_enrollment(self):
        response = self.update(status="berlangsung", durasi=20)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["waktu_mulai"], self.now.isoformat())
        self.assertIsNone(response.json["progress"]["waktu_selesai"])
        self.assertEqual(self.enrollment.status, "berlangsung")
        self.assertIsNone(self.enrollment.tanggal_selesai)
        self.assertEqual(self.own_progress().durasi, 20)
        self.session.flush.assert_called_once()
        self.session.commit.assert_called_once()
        locking = [str(call.args[0]) for call in self.session.execute.call_args_list]
        self.assertIn("FOR UPDATE", locking[0])
        self.assertIn("FOR UPDATE", locking[1])

    def test_completion_and_all_active_materials_complete(self):
        response = self.update(status="selesai")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["course_progress"]["progress"], 50)
        self.assertEqual(self.enrollment.status, "berlangsung")
        response = self.update(2, status="selesai")
        self.assertEqual(response.json["course_progress"]["progress"], 100)
        self.assertEqual(self.enrollment.status, "selesai")
        self.assertEqual(self.enrollment.tanggal_selesai, self.now)
        self.assertEqual(self.own_progress().waktu_mulai, self.now)
        self.assertEqual(self.own_progress().waktu_selesai, self.now)
        self.assertEqual(self.enrollment.status_test, "lulus")
        self.assertEqual(self.enrollment.test_dapat_diakses_lagi, datetime(2027, 1, 1))

    def test_repeated_completion_preserves_record_and_timestamps(self):
        self.update(status="selesai")
        self.update(2, status="selesai")
        completed = self.enrollment.tanggal_selesai
        self.now = datetime(2026, 10, 6)
        with patch("routes.progress.datetime") as clock:
            clock.now.return_value = self.now
            response = self.update(status="selesai")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session.add.call_count, 2)
        self.assertEqual(self.own_progress().waktu_selesai, completed)
        self.assertEqual(self.enrollment.tanggal_selesai, completed)

    def test_reset_and_reopen_progress(self):
        self.update(status="selesai")
        self.update(2, status="selesai")
        self.update(status="berlangsung")
        self.assertEqual(self.enrollment.status, "berlangsung")
        self.assertIsNone(self.enrollment.tanggal_selesai)
        self.assertIsNone(self.own_progress().waktu_selesai)
        self.update(status="belum_mulai")
        self.update(2, status="belum_mulai")
        self.assertEqual(self.enrollment.status, "belum_mulai")
        self.assertIsNone(self.own_progress().waktu_mulai)
        self.assertIsNone(self.own_progress().waktu_selesai)

    def test_durasi_only_update_preserves_status(self):
        self.update(status="berlangsung")
        response = self.update(durasi=100)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.own_progress().status, "berlangsung")
        self.assertEqual(self.own_progress().durasi, 100)
        self.update(durasi=None)
        self.assertIsNone(self.own_progress().durasi)

    def test_get_existing_progress_is_owned(self):
        self.update(status="berlangsung")
        response = self.client.get("/api/me/materi/1/progress", headers=self.headers())
        self.assertEqual(response.json["progress"]["status"], "berlangsung")
        self.assertEqual(response.json["progress"]["id_user"], 2)
        self.assertEqual(self.progress[0].status, "selesai")

    def test_not_enrolled_does_not_use_other_enrollment(self):
        self.enrollment.id_user = 3
        for method, path in (("get", "/api/me/materi/1/progress"), ("patch", "/api/me/materi/1/progress"),
                             ("get", "/api/me/course/1/progress")):
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(), json={"status": "selesai"}).status_code, 403)
        self.session.add.assert_not_called()
        self.session.commit.assert_not_called()

    def test_missing_materi_and_course(self):
        for method, path in (("get", "/api/me/materi/999/progress"), ("patch", "/api/me/materi/999/progress"),
                             ("get", "/api/me/course/999/progress")):
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(), json={"status": "selesai"}).status_code, 404)

    def test_inactive_content_access(self):
        self.assertEqual(self.update(3, status="selesai").status_code, 404)
        for parent in (self.course, self.kategori):
            parent.status = "nonaktif"
            self.assertEqual(self.update(status="selesai").status_code, 404)
            self.assertEqual(self.client.get("/api/me/course/1/progress", headers=self.headers()).status_code, 404)
            parent.status = "aktif"

    def test_authentication_and_inactive_users(self):
        for method, path in (("get", "/api/me/materi/1/progress"), ("patch", "/api/me/materi/1/progress"),
                             ("get", "/api/me/course/1/progress")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 401)
            self.assertEqual(getattr(self.client, method)(path, headers=self.headers(4)).status_code, 403)

    def test_invalid_and_forbidden_fields(self):
        invalid = [{}, [], {"status": "lulus"}, {"status": []}, {"status": None}, {"durasi": -1},
                   {"durasi": True}, {"durasi": 4294967296}, {"durasi": "10"}]
        invalid += [{key: 3} for key in ("id_user", "id_materi", "id_user_materi", "waktu_mulai", "waktu_selesai",
                    "tanggal_selesai", "status_test", "test_dapat_diakses_lagi")]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch("/api/me/materi/1/progress", headers=self.headers(), json=payload).status_code, 400)
        self.session.commit.assert_not_called()
        self.session.add.assert_not_called()

    def test_course_progress_70_percent_and_inactive_exclusion(self):
        self.materi[:] = [Materi(id_materi=i, id_course=1, course=self.course, urutan=i, judul_materi=str(i),
                                status="aktif") for i in range(1, 11)]
        self.materi.append(Materi(id_materi=11, id_course=1, course=self.course, urutan=11, status="nonaktif"))
        self.progress[:] = [UserMateri(id_user_materi=i, id_user=2, id_materi=i, status="selesai") for i in range(1, 8)]
        response = self.client.get("/api/me/course/1/progress", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["progress"], 70)
        self.assertEqual(response.json["progress"]["total_materi"], 10)
        self.assertEqual(response.json["progress"]["materi_selesai"], 7)
        self.assertEqual(response.json["progress"]["status"], "berlangsung")
        self.assertEqual(len(response.json["progress"]["materi"]), 10)
        self.session.commit.assert_not_called()

    def test_course_without_active_materials_zero(self):
        for materi in self.materi:
            materi.status = "nonaktif"
        response = self.client.get("/api/me/course/1/progress", headers=self.headers())
        self.assertEqual(response.json["progress"]["progress"], 0)
        self.assertEqual(response.json["progress"]["status"], "belum_mulai")

    def test_course_progress_ignores_other_user_and_course(self):
        self.materi.append(Materi(id_materi=9, id_course=2, status="aktif", urutan=1))
        self.progress.append(UserMateri(id_user_materi=9, id_user=2, id_materi=9, status="selesai"))
        response = self.client.get("/api/me/course/1/progress", headers=self.headers())
        self.assertEqual(response.json["progress"]["progress"], 0)
        self.assertEqual(response.json["progress"]["total_materi"], 2)

    def test_constraint_conflict_at_flush_rolls_back(self):
        self.session.flush.side_effect = IntegrityError("insert", {}, Exception(1062, "duplicate"))
        self.assertEqual(self.update(status="selesai").status_code, 409)
        self.session.rollback.assert_called_once()
        self.session.commit.assert_not_called()

    def test_fk_conflict_at_commit_rolls_back(self):
        self.session.commit.side_effect = IntegrityError("write", {}, Exception(1452, "FK"))
        self.assertEqual(self.update(status="selesai").status_code, 409)
        self.session.rollback.assert_called_once()

    def test_concurrent_deadlock_returns_retry_conflict(self):
        self.session.flush.side_effect = OperationalError("write", {}, Exception(1213, "deadlock"))
        self.assertEqual(self.update(status="berlangsung").status_code, 409)
        self.session.rollback.assert_called_once()

    def test_unique_constraint_and_cascade_match_schema(self):
        table = UserMateri.__table__
        self.assertTrue(any(c.name == "uq_user_materi" for c in table.constraints))
        self.assertTrue(table.c.id_user_materi.type.unsigned)
        for name in ("id_user", "id_materi"):
            fk = next(iter(table.c[name].foreign_keys))
            self.assertEqual(fk.ondelete, "CASCADE")
            self.assertEqual(fk.onupdate, "CASCADE")
        self.assertNotIn("delete", UserMateri.materi.property.cascade)
        self.assertNotIn("progress", UserCourse.__table__.columns)

    def test_unexpected_database_failure_returns_safe_message(self):
        for error, expected in ((IntegrityError("write", {}, Exception(1048, "PRIVATE_DATABASE_DETAIL")), 409),
                               (OperationalError("write", {}, Exception(2006, "PRIVATE_DATABASE_DETAIL")), 503)):
            self.session.flush.side_effect = error
            response = self.update(status="berlangsung")
            self.assertEqual(response.status_code, expected)
            self.assertNotIn("PRIVATE_DATABASE_DETAIL", response.get_data(as_text=True))
        self.assertEqual(self.session.rollback.call_count, 2)
