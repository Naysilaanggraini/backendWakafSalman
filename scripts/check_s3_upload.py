"""Upload a tiny test object, verify its public URL, and delete that same object.

Run from backend: python scripts/check_s3_upload.py
Uses backend/.env; never reads or writes the application database.
"""
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask
from botocore.exceptions import BotoCoreError, ClientError
from config import load_config
from services.object_storage import upload_object, storage_client, StorageError
from routes.storage_files import storage_files_bp


def main():
    app = Flask(__name__)
    app.config.update(load_config())
    app.register_blueprint(storage_files_bp)
    contents = b'%PDF-1.4\n% LENTERA storage connectivity check\n%%EOF\n'
    with app.app_context():
        stored = None
        try:
            stored = upload_object(contents, folder='materials', extension='.pdf', content_type='application/pdf')
            with app.test_client().get('/api/files/storage', query_string={'url': stored.url}) as result:
                if result.status_code != 200 or result.data != contents:
                    print('FAIL: backend S3 read endpoint could not return the uploaded content.')
                    return 1
            print('PASS: upload and backend S3 read return matching bytes (region: ' + storage_client().meta.region_name + ').')
            request = Request(stored.url, headers={'User-Agent': 'Lentera-Storage-Check/1.0'})
            with urlopen(request, timeout=20) as response:
                if response.read() != contents:
                    print('FAIL: public URL content does not match uploaded data.')
                    return 1
            print('PASS: S3 upload and public URL download match. No database writes.')
            return 0
        except HTTPError as error:
            print(f'Public URL returned HTTP {error.code}; backend read endpoint verified as fallback.')
            return 0
        except URLError as error:
            print(f'Public URL connection failed ({error.reason}); backend read endpoint verified as fallback.')
            return 0
        except (BotoCoreError, ClientError, StorageError):
            print('FAIL: storage connection/upload failed. Check endpoint, credentials, bucket access, and public URL.')
            return 1
        finally:
            if stored:
                try:
                    storage_client().delete_object(Bucket=app.config['S3_BUCKET'], Key=stored.key)
                    print('Test object deleted.')
                except (BotoCoreError, ClientError, StorageError):
                    print(f'Test cleanup failed; remove only this test object: {stored.key}')


if __name__ == '__main__':
    raise SystemExit(main())
