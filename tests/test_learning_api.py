"""Real ORM/API integration in an isolated SQLite database (never the configured DB)."""
import unittest
from datetime import timedelta
from flask import Flask
import jwt
from werkzeug.security import generate_password_hash
from extensions import db
from models import (User, Kategori, Course, Material, Enrollment, MaterialProgress, Question,
                    Option, TestAttempt, UserAnswer, Discussion)
from models.learning import utcnow
from routes.auth import auth_bp
from routes.tests import tests_bp
from routes.discussions import discussions_bp
from routes.enrollment import enrollment_bp
from routes.progress import progress_bp
from routes.reporting import reporting_bp


class LearningApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://",
            JWT_SECRET_KEY="test-only-learning-key-at-least-32-bytes", SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(self.app)
        for bp in (auth_bp, tests_bp, discussions_bp, enrollment_bp, progress_bp, reporting_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.session.execute(db.text("PRAGMA foreign_keys = ON"))
        db.session.commit()
        db.create_all()
        db.session.add_all([User(id_user=i, nama=f"User {i}", email=f"user{i}@example.test",
            password=generate_password_hash("fixture-password"), role="user", status="aktif") for i in (1, 2, 3)])
        db.session.add(Kategori(id_kategori=1, nama_kategori="Assessment", status="aktif"))
        db.session.flush()
        db.session.add_all([Course(id_course=i, judul_course=f"Course {i}", id_kategori=1, masa_tunggu_test_hari=0) for i in (1, 2)])
        db.session.add_all([Material(id_materi=i, id_course=i, judul_materi=f"Material {i}", jenis_file="pdf", tautan_file="https://example.test/material.pdf") for i in (1, 2)])
        db.session.flush()
        for uid in (1, 2):
            db.session.add(Enrollment(id_user=uid, id_course=1))
            db.session.add(MaterialProgress(id_user=uid, id_materi=1, status="selesai"))
        for i in range(1, 11):
            q = Question(id_soal=i, id_course=1, pertanyaan=f"Question {i}", urutan=i)
            db.session.add(q)
            db.session.add_all([Option(id_pilihan=i * 10 + j, question=q,
                teks_pilihan=f"Option {j}", urutan=j, is_benar=j == 1) for j in (1, 2, 3)])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def headers(self, uid=1, expired=False):
        return {"Authorization": "Bearer " + jwt.encode({"id_user": uid,
            "exp": utcnow() + timedelta(hours=-1 if expired else 1)}, self.app.config["JWT_SECRET_KEY"], algorithm="HS256")}

    def start(self, uid=1):
        response = self.client.post("/api/courses/1/test-attempts", headers=self.headers(uid), json={})
        self.assertIn(response.status_code, (200, 201), response.json)
        return response.json["attempt"]["attempt_id"]

    def answers(self, correct=8):
        return [{"question_id": i, "selected_option_id": i * 10 + (1 if i <= correct else 2)} for i in range(1, 11)]

    def submit(self, attempt_id, correct=8, uid=1):
        return self.client.post(f"/api/test-attempts/{attempt_id}/submit", headers=self.headers(uid), json={"answers": self.answers(correct)})

    def test_identity_enrollment_progress_assessment_and_discussion_share_data(self):
        login = self.client.post("/api/auth/login", json={
            "email": "user3@example.test", "password": "fixture-password"})
        self.assertEqual(login.status_code, 200, login.json)
        headers = {"Authorization": "Bearer " + login.json["token"]}
        enrolled = self.client.post("/api/course/1/enrollment", headers=headers, json={})
        self.assertEqual(enrolled.status_code, 201, enrolled.json)
        blocked = self.client.post("/api/courses/1/test-attempts", headers=headers, json={})
        self.assertEqual(blocked.status_code, 403)
        progress = self.client.patch("/api/me/materi/1/progress", headers=headers,
                                     json={"status": "selesai"})
        self.assertEqual(progress.status_code, 200, progress.json)
        aid = self.start(uid=3)
        result = self.submit(aid, uid=3)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertTrue(result.json["passed"])
        enrollment = db.session.query(Enrollment).filter_by(id_user=3).one()
        self.assertEqual(enrollment.status_test, "lulus")
        self.assertEqual(enrollment.status, "selesai")
        comment = self.client.post("/api/discussions/material/1", headers=headers,
                                   json={"content": "Completed through the shared APIs"})
        self.assertEqual(comment.status_code, 201, comment.json)
        from models import Activity, Materi, UserCourse, UserMateri
        self.assertIs(Material, Materi)
        self.assertIs(Enrollment, UserCourse)
        self.assertIs(MaterialProgress, UserMateri)
        self.assertEqual(db.session.query(Activity).filter_by(id_user=3, jenis_aktivitas="login").count(), 1)

    def test_questions_and_detail_never_expose_keys(self):
        response = self.client.get("/api/courses/1/test", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["questions"]), 10)
        self.assertIsNone(response.json["active_attempt"])
        self.assertEqual(db.session.query(TestAttempt).count(), 0)
        for q in response.json["questions"]:
            for option in q["options"]:
                self.assertEqual(set(option), {"option_id", "text"})
        detail = self.client.get("/api/courses/1/questions/1", headers=self.headers())
        self.assertEqual(detail.json["question"], response.json["questions"][0])
        self.assertEqual(self.client.get("/api/courses/1/questions/999", headers=self.headers()).status_code, 404)

    def test_start_save_refresh_resume_without_duplicate(self):
        aid = self.start()
        self.assertEqual(db.session.get(TestAttempt, aid).status_attempt, "in_progress")
        response = self.client.post(f"/api/test-attempts/{aid}/answers", headers=self.headers(), json={"answers": self.answers()[:2]})
        self.assertEqual(response.status_code, 200)
        refreshed = self.client.get("/api/courses/1/test", headers=self.headers()).json
        self.assertEqual(refreshed["active_attempt"]["attempt_id"], aid)
        self.assertEqual(len(refreshed["active_attempt"]["answers"]), 2)
        self.assertNotIn("is_correct", str(refreshed))
        self.assertEqual(self.start(), aid)
        self.assertEqual(db.session.query(TestAttempt).count(), 1)
        self.assertEqual(self.client.get(f"/api/test-attempts/{aid}", headers=self.headers()).status_code, 200)
        self.assertEqual(self.client.get(f"/api/test-attempts/{aid}/result", headers=self.headers()).status_code, 409)

    def test_scoring_80_and_result_persisted(self):
        aid = self.start()
        response = self.submit(aid)
        self.assertEqual(response.status_code, 200, response.json)
        for field, value in {"total_questions": 10, "answered_questions": 10, "correct_answers": 8,
            "wrong_answers": 2, "score": 80, "passing_score": 70, "passed": True}.items():
            self.assertEqual(response.json[field], value)
        fetched = self.client.get(f"/api/test-attempts/{aid}/result", headers=self.headers())
        self.assertEqual(fetched.json, response.json)
        self.assertEqual(db.session.get(TestAttempt, aid).status_attempt, "completed")
        self.assertEqual(self.submit(aid).status_code, 409)
        self.assertEqual(self.client.post(f"/api/test-attempts/{aid}/answers", headers=self.headers(), json={"answers": self.answers()}).status_code, 409)

    def test_scoring_60_failed_and_unanswered_wrong(self):
        aid = self.start()
        result = self.submit(aid, 6).json
        self.assertEqual(result["score"], 60)
        self.assertFalse(result["passed"])
        aid = self.start()
        result = self.client.post(f"/api/test-attempts/{aid}/submit", headers=self.headers(), json={"answers": self.answers()[:2]}).json
        self.assertEqual(result["answered_questions"], 2)
        self.assertEqual(result["wrong_answers"], 8)
        self.assertEqual(result["score"], 20)

    def test_answer_upsert_and_invalid_answers_atomic(self):
        aid = self.start()
        url = f"/api/test-attempts/{aid}/answers"
        entry = {"question_id": 1, "selected_option_id": 11}
        self.assertEqual(self.client.post(url, headers=self.headers(), json={"answers": [entry]}).status_code, 200)
        entry["selected_option_id"] = 12
        self.assertEqual(self.client.post(url, headers=self.headers(), json={"answers": [entry]}).status_code, 200)
        self.assertEqual(db.session.query(UserAnswer).count(), 1)
        self.assertEqual(db.session.query(UserAnswer).one().id_pilihan, 12)
        for entries in ([entry, entry], [{"question_id": 1, "selected_option_id": 21}],
                        [{"question_id": 999, "selected_option_id": 11}],
                        [{"question_id": True, "selected_option_id": 11}], [], "invalid"):
            self.assertEqual(self.client.post(url, headers=self.headers(), json={"answers": entries}).status_code, 400)
        self.assertEqual(db.session.query(UserAnswer).count(), 1)

    def test_ownership_and_score_manipulation(self):
        aid = self.start()
        for suffix in ("", "/result"):
            self.assertEqual(self.client.get(f"/api/test-attempts/{aid}{suffix}", headers=self.headers(2)).status_code, 403)
        for suffix in ("answers", "submit"):
            self.assertEqual(self.client.post(f"/api/test-attempts/{aid}/{suffix}", headers=self.headers(2), json={"answers": self.answers()}).status_code, 403)
        for field in ("score", "correct_answers", "wrong_answers", "passed", "user_id", "id_user"):
            self.assertEqual(self.client.post(f"/api/test-attempts/{aid}/submit", headers=self.headers(), json={field: 100}).status_code, 400)
        self.assertEqual(db.session.get(TestAttempt, aid).status_attempt, "in_progress")

    def test_auth_login_missing_invalid_expired_inactive(self):
        login = self.client.post("/api/auth/login", json={"email": "user1@example.test", "password": "fixture-password"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/courses/1/test", headers={"Authorization": "Bearer " + login.json["token"]}).status_code, 200)
        for headers in ({}, {"Authorization": "Bearer invalid"}, self.headers(expired=True)):
            for url in ("/api/courses/1/test", "/api/discussions/course/1"):
                self.assertEqual(self.client.get(url, headers=headers).status_code, 401)
        db.session.get(User, 1).status = "nonaktif"
        db.session.commit()
        self.assertEqual(self.client.get("/api/courses/1/test", headers=self.headers()).status_code, 403)

    def test_access_missing_and_incomplete_materials(self):
        self.assertEqual(self.client.get("/api/courses/999/test", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.get("/api/courses/1/test", headers=self.headers(3)).status_code, 403)
        self.assertEqual(self.client.get("/api/courses/2/test", headers=self.headers()).status_code, 403)
        db.session.query(MaterialProgress).filter_by(id_user=1).one().status = "berlangsung"
        db.session.commit()
        self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json={}).status_code, 403)
        # Test discussion remains available before material completion or any attempt.
        self.assertEqual(self.client.get("/api/discussions/test/1", headers=self.headers()).status_code, 200)
        db.session.get(Course, 1).status = "nonaktif"
        db.session.commit()
        self.assertEqual(self.client.get("/api/discussions/course/1", headers=self.headers()).status_code, 403)

    def test_snapshot_freezes_questions_and_threshold(self):
        aid = self.start()
        db.session.get(Option, 11).is_benar = False
        db.session.get(Option, 12).is_benar = True
        db.session.get(Question, 10).status = "nonaktif"
        db.session.get(Course, 1).passing_grade = 90
        db.session.commit()
        result = self.submit(aid).json
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["passing_score"], 70)
        self.assertTrue(result["passed"])

    def test_submit_saved_answers_and_exact_threshold(self):
        aid = self.start()
        self.client.post(f"/api/test-attempts/{aid}/answers", headers=self.headers(), json={"answers": self.answers(7)})
        response = self.client.post(f"/api/test-attempts/{aid}/submit", headers=self.headers(), json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["score"], 70)
        self.assertTrue(response.json["passed"])
        enrollment = db.session.query(Enrollment).filter_by(id_user=1).one()
        self.assertEqual(enrollment.status, "selesai")
        self.assertIsNotNone(enrollment.tanggal_selesai)

    def test_missing_test_attempt_and_malformed_payloads(self):
        self.assertEqual(self.client.get("/api/test-attempts/999", headers=self.headers()).status_code, 404)
        db.session.add(Enrollment(id_user=1, id_course=2))
        db.session.commit()
        empty = self.client.get("/api/courses/2/test", headers=self.headers())
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json['questions'], [])
        self.assertEqual(self.client.get("/api/discussions/test/2", headers=self.headers()).status_code, 404)
        for data in (None, [], {"user_id": 2}, {"score": 100}):
            self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json=data).status_code, 400)
        aid = self.start()
        self.assertEqual(self.client.post(f"/api/test-attempts/{aid}/answers", headers=self.headers(), json={}).status_code, 400)
        response = self.client.post(f"/api/test-attempts/{aid}/submit", headers=self.headers(), json={})
        self.assertEqual(response.json["score"], 0)
        self.assertEqual(response.json["wrong_answers"], 10)

    def test_invalid_bulk_submit_rolls_back_all_changes(self):
        aid = self.start()
        response = self.client.post(f"/api/test-attempts/{aid}/submit", headers=self.headers(),
            json={"answers": [self.answers()[0], {"question_id": 2, "selected_option_id": 11}]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.session.query(UserAnswer).count(), 0)
        self.assertEqual(db.session.get(TestAttempt, aid).status_attempt, "in_progress")

    def test_retry_wait_limits_and_invalid_configuration(self):
        db.session.get(Course, 1).masa_tunggu_test_hari = 7
        db.session.commit()
        aid = self.start()
        self.assertFalse(self.submit(aid, 6).json["passed"])
        self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json={}).status_code, 403)
        enrollment = db.session.query(Enrollment).filter_by(id_user=1).one()
        enrollment.test_dapat_diakses_lagi = utcnow() - timedelta(days=1)
        db.session.get(Course, 1).maksimal_attempt = 1
        db.session.commit()
        self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(), json={}).status_code, 403)
        db.session.get(Option, 11).is_benar = False
        db.session.commit()
        self.assertEqual(self.client.post("/api/courses/1/test-attempts", headers=self.headers(2), json={}).status_code, 409)

    def test_discussion_all_contexts_isolated_and_identity(self):
        for context in ("course", "material", "test"):
            url = f"/api/discussions/{context}/1"
            self.assertEqual(self.client.get(url, headers=self.headers()).json, {"discussions": []})
            response = self.client.post(url, headers=self.headers(), json={"content": f"Hello {context}"})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["discussion"]["user_id"], 1)
            self.assertEqual(response.json["discussion"]["context_type"], context)
            listed = self.client.get(url, headers=self.headers(2)).json["discussions"]
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["content"], f"Hello {context}")
            self.assertEqual(listed[0]["user"]["nama"], "User 1")
            self.assertTrue(listed[0]["created_at"].endswith("Z"))
        self.assertEqual(db.session.query(TestAttempt).count(), 0)

    def test_discussion_reply_edit_delete_authorization(self):
        url = "/api/discussions/material/1"
        parent = self.client.post(url, headers=self.headers(), json={"content": "Parent"}).json["discussion"]["discussion_id"]
        reply = self.client.post(url, headers=self.headers(2), json={"content": "Reply", "parent_id": parent})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.json["discussion"]["parent_id"], parent)
        target = f"{url}/{parent}"
        self.assertEqual(self.client.patch(target, headers=self.headers(2), json={"content": "Hijack"}).status_code, 403)
        self.assertEqual(self.client.delete(target, headers=self.headers(2), json={}).status_code, 403)
        edited = self.client.patch(target, headers=self.headers(), json={"content": "Edited"})
        self.assertEqual(edited.status_code, 200)
        self.assertTrue(edited.json["discussion"]["updated_at"])
        self.assertEqual(self.client.post("/api/discussions/course/1", headers=self.headers(), json={"content": "Wrong context", "parent_id": parent}).status_code, 404)
        self.assertEqual(self.client.delete(target, headers=self.headers(), json={}).status_code, 200)
        listed = self.client.get(url, headers=self.headers()).json["discussions"]
        self.assertEqual(len(listed), 2)
        self.assertTrue(listed[0]["deleted"])
        self.assertEqual(listed[0]["content"], "")
        self.assertEqual(listed[1]["content"], "Reply")

    def test_discussion_validation_context_access_and_hidden_threads(self):
        for content in ("", "   ", None, 42, "x" * 2001):
            self.assertEqual(self.client.post("/api/discussions/course/1", headers=self.headers(), json={"content": content}).status_code, 400)
        self.assertEqual(self.client.post("/api/discussions/course/1", headers=self.headers(), json={"content": "spoof", "user_id": 2}).status_code, 400)
        for url, status in (("/api/discussions/invalid/1", 400), ("/api/discussions/material/999", 404),
                            ("/api/discussions/test/999", 404), ("/api/discussions/course/2", 403)):
            self.assertEqual(self.client.get(url, headers=self.headers()).status_code, status)
        self.assertEqual(self.client.get("/api/discussions/course/1", headers=self.headers(3)).status_code, 403)
        url = "/api/discussions/course/1"
        parent = self.client.post(url, headers=self.headers(), json={"content": "Hidden"}).json["discussion"]["discussion_id"]
        self.client.post(url, headers=self.headers(), json={"content": "Reply", "parent_id": parent})
        db.session.get(Discussion, parent).status = "disembunyikan"
        db.session.commit()
        self.assertEqual(self.client.get(url, headers=self.headers()).json["discussions"], [])
        self.assertEqual(self.client.post(url, headers=self.headers(), json={"content": "reply", "parent_id": parent}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
