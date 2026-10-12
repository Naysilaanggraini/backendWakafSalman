import unittest
from flask import Flask
from extensions import db
from models import Course, Kategori
from routes.course import course_bp


class PublicCoursesTests(unittest.TestCase):
    def test_only_active_catalog_metadata_is_public(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(app)
        app.register_blueprint(course_bp)
        with app.app_context():
            db.create_all()
            try:
                db.session.add_all([Kategori(id_kategori=1, nama_kategori="Published", status="aktif"), Kategori(id_kategori=2, nama_kategori="Hidden", status="nonaktif")])
                db.session.flush()
                db.session.add_all([Course(id_course=i, id_kategori=1, judul_course=f"Course {i}", status="aktif") for i in range(1, 9)])
                db.session.add_all([Course(id_course=9, id_kategori=1, judul_course="Draft", status="nonaktif"), Course(id_course=10, id_kategori=2, judul_course="Hidden", status="aktif")])
                db.session.commit()
                response = app.test_client().get('/api/course/public')
                self.assertEqual(response.status_code, 200)
                rows = response.json['course']
                self.assertEqual([row['id'] for row in rows], [8, 7, 6, 5, 4, 3])
                self.assertEqual(set(rows[0]), {'id', 'judul', 'thumbnail', 'category'})
                self.assertEqual(rows[0]['category'], 'Published')
            finally:
                db.session.remove()
                db.drop_all()
                db.engine.dispose()
