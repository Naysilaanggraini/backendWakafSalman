"""Server-side S3-compatible storage. Database values are permanent public URLs."""
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class StorageError(OSError):
    pass


def uses_s3():
    return current_app.config.get('FILE_STORAGE', 'local') == 's3'


def storage_client():
    config = current_app.config
    required = ('S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY', 'S3_ENDPOINT_URL', 'S3_BUCKET', 'S3_PUBLIC_URL')
    if any(not config.get(key) for key in required):
        raise StorageError('Konfigurasi penyimpanan S3 belum lengkap')
    for key in ('S3_ENDPOINT_URL', 'S3_PUBLIC_URL'):
        try:
            url = urlsplit(config[key])
            valid = url.scheme == 'https' and url.hostname and not url.username and not url.password and not url.query and not url.fragment
        except ValueError:
            valid = False
        if not valid:
            raise StorageError('Konfigurasi URL penyimpanan S3 tidak valid')
    region = (config.get('S3_REGION') or 'auto').strip() or 'auto'
    if urlsplit(config['S3_ENDPOINT_URL']).hostname.endswith('.r2.cloudflarestorage.com'):
        region = 'auto'
    return boto3.client('s3', endpoint_url=config['S3_ENDPOINT_URL'].rstrip('/'),
        aws_access_key_id=config['S3_ACCESS_KEY_ID'], aws_secret_access_key=config['S3_SECRET_ACCESS_KEY'],
        region_name=region,
        config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=30,
                      retries={'max_attempts': 2, 'mode': 'standard'},
                      request_checksum_calculation='when_required', response_checksum_validation='when_required',
                      s3={'addressing_style': 'path'}))


def public_object_url(key):
    return current_app.config['S3_PUBLIC_URL'].rstrip('/') + '/' + quote(key.lstrip('/'), safe='/')


@dataclass
class StoredObject:
    key: str
    url: str

    @property
    def name(self):
        return self.key.rsplit('/', 1)[-1]

    def unlink(self, missing_ok=True):
        # Only called for an object created by this request if its DB commit fails.
        try:
            storage_client().delete_object(Bucket=current_app.config['S3_BUCKET'], Key=self.key)
        except (BotoCoreError, ClientError, StorageError):
            current_app.logger.warning('Could not clean up uncommitted upload')


def upload_object(contents, *, folder, extension, content_type):
    try:
        client = storage_client()
        prefix = current_app.config.get('S3_KEY_PREFIX', 'data').strip('/')
        date = datetime.now(timezone.utc).strftime('%Y/%m')
        key = '/'.join(part for part in (prefix, date, folder, uuid4().hex + extension) if part)
        url = public_object_url(key)
        if len(url) > 500:
            raise StorageError('URL publik file terlalu panjang')
        client.put_object(Bucket=current_app.config['S3_BUCKET'], Key=key, Body=contents,
                          ContentType=content_type, ContentDisposition='inline')
        return StoredObject(key=key, url=url)
    except (BotoCoreError, ClientError) as error:
        # Provider errors may contain internal endpoint/request information.
        raise StorageError('File belum dapat disimpan ke penyimpanan S3. Coba lagi.') from error
