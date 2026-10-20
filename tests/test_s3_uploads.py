"""Real API/database integration; S3 calls are mocked, never production writes."""
from io import BytesIO
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
from PIL import Image

from extensions import db
from models import User, Material, Course, Kategori
from routes.materi import materi_bp
from routes.course import course_bp
from routes.kategori import kategori_bp
from routes.storage_files import storage_files_bp
from services.object_storage import public_object_url
from tests import test_learning_api as fixtures


class S3UploadTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LearningApiTests()
        self.fixture.setUp()
        self.app = self.fixture.app
        for bp in (materi_bp, course_bp, kategori_bp, storage_files_bp):
            self.app.register_blueprint(bp)
        self.app.config.update(FILE_STORAGE='s3', S3_ENDPOINT_URL='https://account.r2.cloudflarestorage.com',
            S3_PUBLIC_URL='https://cdn.example.test/', S3_BUCKET='dev', S3_ACCESS_KEY_ID='test-key',
            S3_SECRET_ACCESS_KEY='test-secret', S3_REGION='auto', S3_KEY_PREFIX='data')
        db.session.get(User, 3).role = 'admin'
        db.session.commit()
        self.client = self.fixture.client
        self.headers = self.fixture.headers(3)
        self.mock = patch('services.object_storage.boto3.client')
        self.factory = self.mock.start()
        self.addCleanup(self.mock.stop)
        self.storage = self.factory.return_value

    def tearDown(self):
        self.fixture.tearDown()

    def png(self):
        output = BytesIO()
        Image.new('RGB', (16, 16), 'gold').save(output, 'PNG')
        output.seek(0)
        return output

    def pdf(self, headers=None):
        return self.client.post('/api/course/1/materi/pdf', headers=headers or self.headers,
            data={'file': (BytesIO(b'%PDF-1.4\n%%EOF'), 'lesson.pdf')})

    def test_pdf_upload_and_database_store_complete_public_url(self):
        response = self.pdf()
        self.assertEqual(response.status_code, 201, response.json)
        args = self.storage.put_object.call_args.kwargs
        self.assertEqual(args['Bucket'], 'dev')
        self.assertEqual(args['ContentType'], 'application/pdf')
        self.assertEqual(args['Body'], b'%PDF-1.4\n%%EOF')
        self.assertRegex(args['Key'], r'^data/\d{4}/\d{2}/materials/[a-f0-9]{32}\.pdf$')
        self.assertEqual(response.json['url'], 'https://cdn.example.test/' + args['Key'])
        self.assertNotIn('/dev/', response.json['url'])
        saved = self.client.patch('/api/materi/1', headers=self.headers,
            json={'tautan_file': response.json['url']})
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(db.session.get(Material, 1).tautan_file, response.json['url'])
        self.assertEqual(self.factory.call_args.kwargs['region_name'], 'auto')
        self.assertEqual(self.factory.call_args.kwargs['aws_access_key_id'], 'test-key')

    def test_thumbnail_upload_is_url_and_persists_in_course_and_category(self):
        response = self.client.post('/api/course/thumbnail', headers=self.headers,
            data={'file': (self.png(), 'image.png')})
        self.assertEqual(response.status_code, 201, response.json)
        url = response.json['url']
        self.assertIn('/thumbnails/', url)
        self.assertEqual(self.storage.put_object.call_args.kwargs['ContentType'], 'image/png')
        for path in ('/api/course/1', '/api/kategori/1'):
            saved = self.client.patch(path, headers=self.headers, json={'thumbnail': url})
            self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(db.session.get(Course, 1).thumbnail, url)
        self.assertEqual(db.session.get(Kategori, 1).thumbnail, url)

    def test_profile_upload_persists_public_url(self):
        response = self.client.patch('/api/auth/me', headers=self.headers,
            data={'foto': (self.png(), 'photo.png')})
        self.assertEqual(response.status_code, 200, response.json)
        url = response.json['user']['foto_profil']
        self.assertTrue(url.startswith('https://cdn.example.test/data/'))
        self.assertIn('/profile-photos/', url)
        self.assertEqual(db.session.get(User, 3).foto_profil, url)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.headers).json['foto_profil'], url)

    def test_failed_profile_commit_cleans_only_its_new_object(self):
        response = self.client.patch('/api/auth/me', headers=self.headers,
            data={'email': 'user1@example.test', 'foto': (self.png(), 'photo.png')})
        self.assertEqual(response.status_code, 409, response.json)
        self.storage.delete_object.assert_called_once_with(Bucket='dev', Key=self.storage.put_object.call_args.kwargs['Key'])
        self.assertFalse(db.session.get(User, 3).foto_profil)

    def test_storage_failures_do_not_save_urls_or_expose_provider_errors(self):
        self.storage.put_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'internal secret details'}}, 'PutObject')
        self.assertEqual(self.pdf().status_code, 503)
        response = self.client.patch('/api/auth/me', headers=self.headers,
            data={'foto': (self.png(), 'photo.png')})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('internal secret', str(response.json))
        self.assertFalse(db.session.get(User, 3).foto_profil)
        self.storage.put_object.assert_called()

    def test_upload_permissions_invalid_images_and_missing_config(self):
        self.assertEqual(self.pdf(self.fixture.headers(1)).status_code, 403)
        self.assertEqual(self.client.post('/api/course/thumbnail', data={'file': (self.png(), 'a.png')}).status_code, 401)
        self.assertEqual(self.client.post('/api/course/thumbnail', headers=self.fixture.headers(1), data={'file': (self.png(), 'a.png')}).status_code, 403)
        self.assertEqual(self.client.post('/api/course/thumbnail', headers=self.headers, data={'file': (BytesIO(b'bad'), 'a.png')}).status_code, 400)
        self.assertEqual(self.client.post('/api/course/thumbnail', headers=self.headers, data={'file': (BytesIO(b'x' * (512 * 1024 + 1)), 'a.png')}).status_code, 413)
        self.storage.put_object.assert_not_called()
        self.app.config['S3_SECRET_ACCESS_KEY'] = ''
        self.assertEqual(self.pdf().status_code, 503)
        self.storage.put_object.assert_not_called()

    def test_public_url_normalizes_slashes_and_encodes_path(self):
        self.assertEqual(public_object_url('/data/2026/my file.pdf'), 'https://cdn.example.test/data/2026/my%20file.pdf')

    def test_managed_pdf_read_uses_signed_s3_and_supports_browser_ranges(self):
        key = 'data/2026/10/materials/' + 'a' * 32 + '.pdf'
        contents = b'%PDF-1.4\nreadable PDF\n%%EOF'
        self.storage.get_object.side_effect = lambda **kwargs: {'Body': BytesIO(contents), 'ETag': '"test-etag"'}
        response = self.client.get('/api/files/storage', query_string={'url': public_object_url(key)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, contents)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        response.close()
        partial = self.client.get('/api/files/storage', query_string={'url': public_object_url(key)}, headers={'Range': 'bytes=0-4'})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.data, b'%PDF-')
        partial.close()
        self.storage.get_object.assert_called_with(Bucket='dev', Key=key)

    def test_managed_images_read_without_exposing_credentials(self):
        for folder in ('thumbnails', 'profile-photos'):
            contents = self.png().getvalue()
            self.storage.get_object.return_value = {'Body': BytesIO(contents)}
            key = f'data/2026/10/{folder}/' + 'a' * 32 + '.png'
            response = self.client.get('/api/files/storage', query_string={'url': public_object_url(key)})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'image/png')
            self.assertEqual(response.data, contents)
            response.close()

    def test_read_endpoint_rejects_other_hosts_traversal_and_non_generated_objects(self):
        for url in ('https://evil.test/data/a.png', 'https://cdn.example.test.evil.test/a.png',
                    'https://cdn.example.test/../secret', 'https://cdn.example.test/%2e%2e/secret',
                    'https://cdn.example.test/data/2026/10/thumbnails/' + 'a' * 32 + '.pdf',
                    'https://cdn.example.test/data/2026/10/materials/' + 'a' * 32 + '.pdf?other=1'):
            self.assertEqual(self.client.get('/api/files/storage', query_string={'url': url}).status_code, 404)
        self.storage.get_object.assert_not_called()

    def test_read_errors_are_safe_and_blank_region_uses_auto(self):
        self.app.config['S3_REGION'] = ' '
        self.storage.get_object.side_effect = ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        url = public_object_url('data/2026/10/materials/' + 'a' * 32 + '.pdf')
        self.assertEqual(self.client.get('/api/files/storage', query_string={'url': url}).status_code, 404)
        self.assertEqual(self.factory.call_args.kwargs['region_name'], 'auto')
        self.storage.get_object.side_effect = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'secret'}}, 'GetObject')
        response = self.client.get('/api/files/storage', query_string={'url': url})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', str(response.json))

    def test_r2_always_uses_auto_even_if_an_old_environment_region_is_set(self):
        self.app.config['S3_REGION'] = 'us-east-1'
        self.assertEqual(self.pdf().status_code, 201)
        self.assertEqual(self.factory.call_args.kwargs['region_name'], 'auto')
