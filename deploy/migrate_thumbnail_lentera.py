"""Apply the thumbnail migration to lentera with a local column-data backup."""
import json
from datetime import datetime, timezone
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import text
from app import app
from extensions import db


def snapshot():
    return {table: [dict(row) for row in db.session.execute(text(
        f'SELECT id_{table}, thumbnail FROM `{table}` ORDER BY id_{table}')).mappings()]
        for table in ('kategori', 'course')}


with app.app_context():
    if db.engine.url.database != 'lentera':
        raise RuntimeError('This migration runner requires database lentera')
    revision = db.session.scalar(text('SELECT version_num FROM alembic_version'))
    if revision not in ('0003_activity_tracking', '0004_thumbnail_mediumtext'):
        raise RuntimeError('Unexpected migration revision; refusing unrelated upgrades')
    before = snapshot()
    folder = Path('backups')
    folder.mkdir(exist_ok=True)
    backup = folder / ('lentera-thumbnail-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    backup.write_text(json.dumps(before, ensure_ascii=False), encoding='utf-8')
    db.session.remove()
    upgrade(revision='0004_thumbnail_mediumtext')
    if snapshot() != before:
        raise RuntimeError('Thumbnail verification failed; inspect backup before continuing')
    types = db.session.execute(text("SELECT TABLE_NAME, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='thumbnail'")).all()
    if {name: kind.lower() for name, kind in types} != {'kategori': 'mediumtext', 'course': 'mediumtext'}:
        raise RuntimeError('Unexpected thumbnail column types')
    print('Database: lentera; thumbnail values preserved; column types:', types)
    print('Backup:', backup)
