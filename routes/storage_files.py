"""Read managed public uploads through S3 when the public CDN is unreachable."""
from io import BytesIO
import re
from urllib.parse import unquote, urlsplit

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, current_app, request, send_file
from services.object_storage import storage_client, StorageError

storage_files_bp = Blueprint('storage_files', __name__, url_prefix='/api/files')


@storage_files_bp.get('/storage')
def read_storage_file():
    # These files already have public URLs. Do not accept arbitrary buckets/keys
    # or fetch the supplied URL: read only this application's generated uploads.
    value = request.args.get('url', '')
    base = current_app.config.get('S3_PUBLIC_URL', '').rstrip('/')
    if not base or len(value) > 500 or not value.startswith(base + '/'):
        return {'message': 'File tidak ditemukan'}, 404
    try:
        parsed = urlsplit(value)
        key = unquote(value[len(base) + 1:])
        prefix = current_app.config.get('S3_KEY_PREFIX', 'data').strip('/')
        pattern = (re.escape(prefix) + '/' if prefix else '') + r'\d{4}/\d{2}/(materials|thumbnails|profile-photos)/[a-f0-9]{32}\.(pdf|png)'
        match = re.fullmatch(pattern, key)
        if parsed.query or parsed.fragment or not match or (match[1] == 'materials') != (match[2] == 'pdf'):
            return {'message': 'File tidak ditemukan'}, 404
        stored = storage_client().get_object(Bucket=current_app.config['S3_BUCKET'], Key=key)
        body = stored['Body']
        try:
            content = body.read(10 * 1024 * 1024 + 1)
        finally:
            body.close()
        if len(content) > 10 * 1024 * 1024:
            return {'message': 'File terlalu besar'}, 413
        response = send_file(BytesIO(content), mimetype='application/pdf' if match[2] == 'pdf' else 'image/png',
                             download_name=key.rsplit('/', 1)[-1], conditional=True, max_age=3600,
                             etag=stored.get('ETag', '').strip('"') or None)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') in ('NoSuchKey', 'NotFound', '404'):
            return {'message': 'File tidak ditemukan'}, 404
        return {'message': 'File belum dapat dibuka dari penyimpanan. Coba lagi.'}, 503
    except (BotoCoreError, StorageError, ValueError):
        return {'message': 'File belum dapat dibuka dari penyimpanan. Coba lagi.'}, 503
