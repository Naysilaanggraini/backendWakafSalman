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
        self.assertEqual(qid, new_id)
        self.assertEqual(db.session.get(Question, qid).status, "aktif")
        self.assertEqual(self.author("delete", f"/questions/{new_id}").status_code, 200)
        self.assertIsNone(db.session.get(Question, qid))

    def test_delete_used_question_preserves_running_attempt(self):
        aid = self.start()
        response = self.author('delete', '/questions/1')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(db.session.get(Question, 1).status, "nonaktif")
        visible = self.author('get').json['questions']
        self.assertNotIn(1, [q['question_id'] for q in visible])
        self.assertEqual(self.submit(aid, correct=8).status_code, 200)

    def test_delete_unused_question_removes_options(self):
        from models import Option
        self.assertEqual(self.author('delete', '/questions/1').status_code, 200)
        self.assertIsNone(db.session.get(Question, 1))
        self.assertEqual(db.session.query(Option).filter_by(id_soal=1).count(), 0)

    def test_admin_delete_tree_does_not_change_participant_progress(self):
        from models import Material, MaterialProgress, Course
        from services.deletion import delete_course_tree, DeleteConflict
        with self.assertRaises(DeleteConflict):
            delete_course_tree(db.session.get(Course, 1))
        db.session.rollback()
        self.assertIsNotNone(db.session.get(Material, 1))
        progress = db.session.query(MaterialProgress).filter_by(id_user=1, id_materi=1).one()
        self.assertEqual(progress.status, 'selesai')

    def test_delete_unused_course_tree(self):
        from models import Course, Material, Option
        from services.deletion import delete_course_tree
        q = Question(id_course=2, pertanyaan='Unused', urutan=1)
        q.options = [Option(teks_pilihan='Yes', urutan=1, is_benar=True)]
        db.session.add(q)
        db.session.commit()
        qid = q.id_soal
        delete_course_tree(db.session.get(Course, 2))
        db.session.commit()
        self.assertIsNone(db.session.get(Course, 2))
        self.assertIsNone(db.session.get(Material, 2))
        self.assertIsNone(db.session.get(Question, qid))
        self.assertEqual(db.session.query(Option).filter_by(id_soal=qid).count(), 0)

    def test_category_delete_preserves_used_course_and_deletes_unused_course(self):
        from models import Kategori, Course, Material
        from routes.kategori import kategori_bp
        self.app.register_blueprint(kategori_bp)
        response = self.client.delete('/api/kategori/1', headers=self.headers(3))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(db.session.get(Kategori, 1).status, 'nonaktif')
        self.assertEqual(db.session.get(Course, 1).status, 'nonaktif')
        self.assertIsNotNone(db.session.get(Kategori, 1))
        self.assertIsNone(db.session.get(Course, 2))
        self.assertIsNone(db.session.get(Material, 2))
        self.assertNotIn(1, [item['id_kategori'] for item in self.client.get('/api/kategori', headers=self.headers(3)).json['kategori']])

    def test_delete_used_course_hides_it_without_deleting_participant_history(self):
        from models import Course, Material, Enrollment, MaterialProgress, UserAnswer
        from routes.course import course_bp
        self.app.register_blueprint(course_bp)
        aid = self.start()
        self.assertEqual(self.submit(aid, correct=8).status_code, 200)
        snapshot = db.session.get(TestAttempt, aid).question_snapshot
        answer_count = db.session.query(UserAnswer).filter_by(id_penilaian=aid).count()
        response = self.client.delete('/api/course/1', headers=self.headers(3))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(db.session.get(Course, 1).status, 'nonaktif')
        self.assertIsNotNone(db.session.get(Material, 1))
        self.assertEqual(db.session.query(Enrollment).filter_by(id_course=1).count(), 2)
        self.assertEqual(db.session.query(MaterialProgress).filter_by(id_materi=1).count(), 2)
        self.assertEqual(db.session.get(TestAttempt, aid).question_snapshot, snapshot)
        self.assertEqual(db.session.query(UserAnswer).filter_by(id_penilaian=aid).count(), answer_count)
        visible = self.client.get('/api/course', headers=self.headers(3)).json['course']
        self.assertNotIn(1, [item['id_course'] for item in visible])
        self.assertEqual(self.client.delete('/api/course/1', headers=self.headers(3)).status_code, 200)

    def test_category_delete_removes_unused_descendants(self):
        from models import Kategori, Course, Material
        from routes.kategori import kategori_bp
        self.app.register_blueprint(kategori_bp)
        category = Kategori(nama_kategori='Unused')
        db.session.add(category)
        db.session.flush()
        cid = category.id_kategori
        course = db.session.get(Course, 2)
        course.id_kategori = cid
        db.session.commit()
        response = self.client.delete(f'/api/kategori/{cid}', headers=self.headers(3))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNone(db.session.get(Kategori, cid))
        self.assertIsNone(db.session.get(Course, 2))
        self.assertIsNone(db.session.get(Material, 2))

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
