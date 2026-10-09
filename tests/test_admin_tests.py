"""Admin authoring through real ORM transactions with historical attempt checks."""
from tests import test_learning_api
from routes.admin_tests import admin_tests_bp
from extensions import db
from models import User, Question, TestAttempt


class AdminTestTests(test_learning_api.LearningApiTests):
    def setUp(self):
        super().setUp()
        self.app.register_blueprint(admin_tests_bp)
        db.session.get(User, 3).role = "admin"
        db.session.commit()

    def author(self, method, suffix="", data=None):
        return getattr(self.client, method)("/api/admin/courses/1/test" + suffix,
            headers=self.headers(3), json=data)

    def question_payload(self, order=11):
        return {"pertanyaan": "Apa prinsip wakaf?", "urutan": order, "status": "aktif",
            "options": [{"text": "Menjaga pokok aset", "urutan": 1, "is_correct": True},
                        {"text": "Menghabiskan pokok aset", "urutan": 2, "is_correct": False}]}

    def test_admin_read_settings_create_update_deactivate(self):
        self.assertEqual(self.author("get").status_code, 200)
        settings = self.author("patch", data={"passing_grade": 80, "maksimal_attempt": 4, "masa_tunggu_test_hari": 2})
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json["maksimal_attempt"], 4)
        made = self.author("post", "/questions", self.question_payload())
        self.assertEqual(made.status_code, 201, made.json)
        qid = made.json["question"]["question_id"]
        changed = self.author("patch", f"/questions/{qid}", self.question_payload())
        self.assertEqual(changed.status_code, 200, changed.json)
        new_id = changed.json["question"]["question_id"]
        self.assertNotEqual(qid, new_id)
        self.assertEqual(db.session.get(Question, qid).status, "nonaktif")
        self.assertEqual(self.author("delete", f"/questions/{new_id}").status_code, 200)
        self.assertIsNotNone(db.session.get(Question, qid))

    def test_admin_denies_learner_and_invalid_payloads(self):
        for method, suffix in (("get", ""), ("patch", ""), ("post", "/questions"), ("patch", "/questions/1"), ("delete", "/questions/1")):
            response = getattr(self.client, method)("/api/admin/courses/1/test" + suffix, headers=self.headers(1), json={})
            self.assertEqual(response.status_code, 403)
        for values in ({"passing_grade": True}, {"maksimal_attempt": 0}, {"masa_tunggu_test_hari": -1}, {"score": 100}):
            self.assertEqual(self.author("patch", data=values).status_code, 400)
        data = self.question_payload()
        data["options"][1]["is_correct"] = True
        self.assertEqual(self.author("post", "/questions", data).status_code, 400)

    def test_authoring_preserves_snapshot_options_resume_scoring(self):
        aid = self.start()
        frozen = db.session.get(TestAttempt, aid).question_snapshot
        self.assertEqual(self.author("patch", data={"passing_grade": 90}).status_code, 200)
        changed = self.author("patch", "/questions/1", self.question_payload(1))
        self.assertEqual(changed.status_code, 200, changed.json)
        current = self.client.get("/api/courses/1/test", headers=self.headers())
        self.assertEqual(current.json["passing_score"], 70)
        self.assertEqual(current.json["questions"][0]["pertanyaan"], "Question 1")
        detail = self.client.get("/api/courses/1/questions/1", headers=self.headers())
        self.assertEqual(detail.json["question"]["pertanyaan"], "Question 1")
        self.assertNotIn("is_correct", str(detail.json))
        submitted = self.submit(aid, correct=8)
        self.assertEqual(submitted.status_code, 200, submitted.json)
        self.assertEqual(submitted.json["score"], 80)
        self.assertTrue(submitted.json["passed"])
        self.assertEqual(db.session.get(TestAttempt, aid).question_snapshot, frozen)
        other = self.start(2)
        newer = db.session.get(TestAttempt, other)
        self.assertEqual(newer.passing_grade, 90)
        self.assertEqual(newer.question_snapshot[0]["pertanyaan"], "Apa prinsip wakaf?")
        self.assertEqual(self.client.get(f"/api/test-attempts/{aid}", headers=self.headers(2)).status_code, 403)

    def test_three_attempts_limit_and_retry_expiry(self):
        from models import Course, Enrollment
        from models.learning import utcnow
        from datetime import timedelta
        course = db.session.get(Course, 1)
        course.maksimal_attempt, course.masa_tunggu_test_hari = 3, 7
        db.session.commit()
        for number in range(1, 4):
            aid = self.start()
            self.assertEqual(db.session.get(TestAttempt, aid).test_attempt, number)
            result = self.submit(aid, correct=6)
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.json["passed"])
            meta = self.client.get("/api/courses/1/test", headers=self.headers()).json
            self.assertFalse(meta["can_start"])
            self.assertIsNotNone(meta["retry_at"])
            self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json={}).status_code, 403)
            enrollment = db.session.query(Enrollment).filter_by(id_user=1, id_course=1).one()
            enrollment.test_dapat_diakses_lagi = utcnow() - timedelta(seconds=1)
            db.session.commit()
        self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json={}).status_code, 403)
        self.assertEqual(db.session.query(TestAttempt).filter_by(id_user=1).count(), 3)
