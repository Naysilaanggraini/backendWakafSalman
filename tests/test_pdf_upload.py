import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from tests import test_learning_api as fixtures
from routes.materi import materi_bp, PDF_LIMIT
from extensions import db
from models import User, Material


class PdfUploadTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LearningApiTests()
        self.fixture.setUp()
        self.app = self.fixture.app
        self.app.register_blueprint(materi_bp)
        self.directory = TemporaryDirectory(prefix="lentera-pdf-test-")
        self.app.config['MATERIAL_PDF_DIR'] = self.directory.name
        self.client = self.fixture.client
        db.session.get(User, 3).role = 'admin'
        db.session.commit()

    def tearDown(self):
        self.fixture.tearDown()
        self.directory.cleanup()

    def upload(self, contents, name='lesson.pdf', uid=3):
        return self.client.post('/api/course/1/materi/pdf', headers=self.fixture.headers(uid),
            data={'file': (BytesIO(contents), name)}, content_type='multipart/form-data')

    def test_upload_url_save_and_read_active_material(self):
        contents = b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF'
        result = self.upload(contents)
        self.assertEqual(result.status_code, 201, result.json)
        link = result.json['url']
        self.assertLess(len(link), 500)
        path = urlsplit(link).path
        self.assertEqual(self.client.get(path).status_code, 404)
        saved = self.client.patch('/api/materi/1', headers=self.fixture.headers(3),
            json={'tautan_file': link, 'jenis_file': 'pdf'})
        self.assertEqual(saved.status_code, 200, saved.json)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, contents)
        self.assertEqual(response.mimetype, 'application/pdf')
        response.close()
        db.session.get(Material, 1).status = 'nonaktif'
        db.session.commit()
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_reject_user_invalid_and_oversized_files(self):
        self.assertEqual(self.upload(b'%PDF-1.4\n%%EOF', uid=1).status_code, 403)
        self.assertEqual(self.upload(b'not a PDF').status_code, 400)
        self.assertEqual(self.upload(b'%PDF-1.4\n%%EOF', name='file.exe').status_code, 400)
        self.assertEqual(self.upload(b'%PDF-' + b'x' * PDF_LIMIT).status_code, 413)
