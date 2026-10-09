"""Cross-role flows over a real, isolated database; no live account changes."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
import test_learning_api as learning
from extensions import db
from models import User, Activity, ActivityTracking, Question, Enrollment, Material, TestAttempt
from routes.admin_assessment import admin_assessment_bp
from routes.activity_tracking import tracking_bp
from routes.logout import logout_bp
from services.activity import record_activity


class LmsIntegrationTests(unittest.TestCase):
    tearDown = learning.LearningApiTests.tearDown
    headers = learning.LearningApiTests.headers
    start = learning.LearningApiTests.start
    submit = learning.LearningApiTests.submit
    answers = learning.LearningApiTests.answers

    def setUp(self):
        learning.LearningApiTests.setUp(self)
        for bp in (admin_assessment_bp, tracking_bp, logout_bp):
            self.app.register_blueprint(bp)
        db.session.get(User, 3).role = 'admin'
        db.session.add(Material(id_materi=3, id_course=1, judul_materi='Materi B', jenis_file='youtube',
                                tautan_file='https://youtu.be/abcdefghijk', status='aktif', urutan=2))
        db.session.commit()
        self.admin = self.headers(3)

    def question(self, text='Soal dari Admin'):
        return {'pertanyaan': text, 'urutan': 11, 'status': 'aktif', 'options': [
            {'text': 'Benar', 'urutan': 1, 'is_correct': True}, {'text': 'Salah', 'urutan': 2, 'is_correct': False}]}

    def pulse(self, kind='buka_materi', key=None, action='active', actor=1, **extra):
        body = {'request_id': key or str(uuid4()), 'kind': kind, 'action': action,
                **({'course_id': 1, 'material_id': 1} if kind == 'buka_materi' else {}), **extra}
        return self.client.post('/api/me/activity', headers=self.headers(actor), json=body)

    def test_admin_authoring_user_reads_course_isolation_and_empty(self):
        path = '/api/admin/courses/1/test/questions'
        self.assertEqual(self.client.post(path, headers=self.headers(), json=self.question()).status_code, 403)
        created = self.client.post(path, headers=self.admin, json=self.question())
        self.assertEqual(created.status_code, 201, created.json)
        qid = created.json['question']['question_id']
        db.session.expire_all()
        self.assertEqual(db.session.get(Question, qid).id_course, 1)
        user = self.client.get('/api/courses/1/test', headers=self.headers())
        self.assertTrue(any(q['question_id'] == qid for q in user.json['questions']))
        self.assertNotIn('is_correct', str(user.json['questions']))
        db.session.add(Enrollment(id_user=1, id_course=2)); db.session.commit()
        other = self.client.get('/api/courses/2/test', headers=self.headers())
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json['questions'], [])
        updated = self.client.patch(f'{path}/{qid}', headers=self.admin, json=self.question('Diubah'))
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(db.session.get(Question, qid).status, 'nonaktif')
        self.assertEqual(self.client.delete(f'/api/admin/courses/2/test/questions/{qid}', headers=self.admin).status_code, 404)
        self.assertEqual(self.client.delete(f"{path}/{updated.json['question']['question_id']}", headers=self.admin).status_code, 200)

    def test_admin_settings_and_input_validation(self):
        path = '/api/admin/courses/1/test'
        self.assertEqual(self.client.get(path, headers=self.admin).json['passing_grade'], 70)
        for values in ({'passing_grade': 101}, {'passing_grade': True}, {'maksimal_attempt': 0}, {'user_id': 1}):
            self.assertEqual(self.client.patch(path, headers=self.admin, json=values).status_code, 400)
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'passing_grade': 70, 'maksimal_attempt': 4, 'masa_tunggu_test_hari': 0}).status_code, 200)
        invalid = self.question(); invalid['options'][1]['is_correct'] = True
        self.assertEqual(self.client.post(path + '/questions', headers=self.admin, json=invalid).status_code, 400)

    def test_material_discussion_persists_admin_moderation_and_ownership(self):
        post = self.client.post('/api/discussions/material/1', headers=self.headers(), json={'content': 'Diskusi A'})
        self.assertEqual(post.status_code, 201)
        cid = post.json['discussion']['discussion_id']
        reply = self.client.post('/api/discussions/material/1', headers=self.headers(2), json={'content': 'Balasan', 'parent_id': cid})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(self.client.get('/api/discussions/material/3', headers=self.headers()).json['discussions'], [])
        listing = self.client.get('/api/admin/discussions?search=Diskusi&course_id=1', headers=self.admin)
        self.assertEqual(listing.status_code, 200, listing.json)
        self.assertEqual(listing.json['discussions'][0]['material_title'], 'Material 1')
        self.assertEqual(listing.json['discussions'][0]['user']['id_user'], 1)
        path = f'/api/admin/discussions/{cid}'
        self.assertEqual(self.client.patch(path, headers=self.headers(), json={'status': 'disembunyikan'}).status_code, 403)
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'status': 'disembunyikan'}).status_code, 200)
        db.session.expire_all()
        self.assertEqual(self.client.get('/api/discussions/material/1', headers=self.headers()).json['discussions'], [])
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'status': 'tampil'}).status_code, 200)
        self.assertEqual(len(self.client.get('/api/discussions/material/1', headers=self.headers()).json['discussions']), 2)
        self.assertEqual(self.client.patch('/api/discussions/material/1/' + str(cid), headers=self.headers(2), json={'content': 'Hijack'}).status_code, 403)
        events = db.session.query(Activity).filter_by(jenis_aktivitas='kirim_komentar').all()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.id_course == 1 and e.id_materi == 1 for e in events))

    def test_duration_dedup_pause_timeout_and_two_tabs(self):
        now = datetime(2026, 10, 9, 3)
        key, second = str(uuid4()), str(uuid4())
        with patch('routes.activity_tracking.utcnow', return_value=now):
            self.assertEqual(self.pulse(key=key).status_code, 200)
            self.assertEqual(self.pulse(key=key).status_code, 200)
            self.assertEqual(self.pulse(key=second).status_code, 200)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=20)):
            result = self.pulse(key=key, action='pause')
            self.assertEqual(result.json['activity']['durasi'], 20)
            self.pulse(key=second, action='pause')
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=100)):
            self.pulse(key=key)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=200)):
            self.assertEqual(self.pulse(key=key).json['activity']['durasi'], 20)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=210)):
            self.assertEqual(self.pulse(key=key, action='end').json['activity']['durasi'], 30)
            self.assertTrue(self.pulse(key=key, action='end').json['finished'])
        rows = db.session.query(Activity).filter_by(jenis_aktivitas='buka_materi').all()
        self.assertEqual(len(rows), 2)  # two real tab opens, only one credits time
        self.assertEqual(sum(r.durasi for r in rows), 30)
        self.assertEqual(self.pulse(key=key, actor=2).status_code, 403)
        self.assertEqual(self.pulse(course_id=2).status_code, 403)

    def test_login_session_heartbeat_logout_and_idempotency(self):
        login = self.client.post('/api/auth/login', json={'email': 'user1@example.test', 'password': 'fixture-password'})
        self.assertEqual(login.status_code, 200)
        headers = {'Authorization': 'Bearer ' + login.json['token']}
        key = str(uuid4())
        now = datetime(2026, 10, 9, 5)
        def send(action):
            return self.client.post('/api/me/activity', headers=headers, json={'request_id': key, 'kind': 'sesi', 'action': action})
        with patch('routes.activity_tracking.utcnow', return_value=now):
            self.assertEqual(send('active').status_code, 200)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=25)):
            self.assertEqual(send('active').status_code, 200)
        logout_key = str(uuid4())
        with patch('routes.logout.utcnow', return_value=now + timedelta(seconds=30)):
            for _ in range(2):
                self.assertEqual(self.client.post('/api/auth/logout', headers=headers, json={'request_id': logout_key}).status_code, 200)
        self.assertEqual(db.session.query(Activity).filter_by(jenis_aktivitas='logout').count(), 1)
        event = db.session.query(Activity).filter_by(jenis_aktivitas='login').one()
        self.assertEqual(event.durasi, 30)
        self.assertTrue(db.session.query(ActivityTracking).filter_by(request_id=key).one().finished)
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 401)

    def test_refresh_replaces_own_segment_without_a_stale_lease(self):
        key, refreshed = str(uuid4()), str(uuid4())
        now = datetime(2026, 10, 9, 5)
        with patch('routes.activity_tracking.utcnow', return_value=now):
            self.assertEqual(self.pulse(key=key).status_code, 200)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=10)):
            self.assertEqual(self.pulse(key=refreshed, previous_request_id=key).status_code, 200)
        with patch('routes.activity_tracking.utcnow', return_value=now + timedelta(seconds=20)):
            result = self.pulse(key=refreshed, action='end')
            self.assertEqual(result.json['activity']['durasi'], 10)
        first = db.session.query(ActivityTracking).filter_by(request_id=key).one()
        self.assertTrue(first.finished)
        self.assertEqual(first.activity.durasi, 10)
        self.assertEqual(self.pulse(actor=2, previous_request_id=key).status_code, 403)

    def test_filters_relations_wib_boundaries_combination_pagination(self):
        for hour, actor, course in ((16, 1, 1), (17, 1, 1), (23, 2, 2)):
            record_activity(actor, 'buka_course', id_course=course, waktu_dimulai=datetime(2026, 10, 8, hour))
        record_activity(1, 'login', waktu_dimulai=datetime(2026, 10, 9, 17))
        db.session.commit()
        path = '/api/activity?user=User%201&course=Course%201&date_from=2026-10-09&date_to=2026-10-09&per_page=1'
        response = self.client.get(path, headers=self.admin)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['pagination']['total'], 1)
        row = response.json['activities'][0]
        self.assertEqual(row['user_name'], 'User 1'); self.assertEqual(row['course_title'], 'Course 1')
        self.assertTrue(row['waktu_dimulai'].endswith('Z'))
        self.assertEqual(self.client.get('/api/activity?search=absent', headers=self.admin).json['pagination']['total'], 0)
        for query in ('date_from=2026-10-10&date_to=2026-10-09', 'date_to=wrong', 'date_to=9999-12-31'):
            self.assertEqual(self.client.get('/api/activity?' + query, headers=self.admin).status_code, 400)
        self.assertEqual(self.client.get('/api/activity', headers=self.headers()).status_code, 403)

    def test_test_events_server_validated_once_and_material_completion(self):
        # Finish real material B to make the course eligible.
        self.assertEqual(self.client.patch('/api/me/materi/3/progress', headers=self.headers(), json={'status': 'selesai'}).status_code, 200)
        self.client.patch('/api/me/materi/3/progress', headers=self.headers(), json={'status': 'selesai'})
        self.assertEqual(db.session.query(Activity).filter_by(jenis_aktivitas='selesai_materi').count(), 1)
        aid = self.start(); self.start()
        self.assertEqual(self.submit(aid).status_code, 200)
        self.assertEqual(self.submit(aid).status_code, 409)
        for kind in ('mulai_test', 'selesai_test', 'selesai_course'):
            event = db.session.query(Activity).filter_by(jenis_aktivitas=kind).one()
            self.assertEqual(event.id_course, 1)
        self.assertIsNotNone(db.session.get(TestAttempt, aid).durasi)
