import base64
import unittest
from routes.kategori import validate_kategori_data
from routes.course import validate_course_data


class ThumbnailValidationTests(unittest.TestCase):
    def test_full_size_uploaded_data_url_accepted_in_both_forms(self):
        image = 'data:image/png;base64,' + base64.b64encode(b'x' * (512 * 1024)).decode('ascii')
        for validator in (validate_kategori_data, validate_course_data):
            values, error = validator({'thumbnail': image})
            self.assertIsNone(error)
            self.assertEqual(values['thumbnail'], image)

    def test_utf8_bytes_limit_and_nullable_values(self):
        for validator in (validate_kategori_data, validate_course_data):
            self.assertIsNone(validator({'thumbnail': 'x' * 700000})[1])
            self.assertIsNotNone(validator({'thumbnail': 'x' * 700001})[1])
            self.assertIsNotNone(validator({'thumbnail': '\u00e9' * 350001})[1])
            self.assertEqual(validator({'thumbnail': None})[0], {'thumbnail': None})
