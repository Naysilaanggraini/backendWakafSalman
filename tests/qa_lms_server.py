"""Opt-in, additive MariaDB/browser QA in a NEW uniquely named database.

Never imports data into .env's database; never drops a database or resets tables.
Fixture accounts/content are confined to the generated *_test database.
JSON stdout is private handoff to the browser runner, not an application log.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if os.getenv('RUN_LMS_ISOLATED_QA') != '1':
        raise RuntimeError('Explicit isolated QA opt-in required')
    from config import load_config
    from sqlalchemy import create_engine, text
    if '--prepare' in sys.argv:
        name = 'wakaf_qa_' + uuid4().hex[:12] + '_test'
        engine = create_engine(load_config()['SQLALCHEMY_DATABASE_URI'].set(database=None))
        with engine.begin() as connection:
            connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
        engine.dispose()
        os.environ['DB_NAME'] = name
        secret, password = secrets.token_hex(32), secrets.token_urlsafe(24)
        os.environ['JWT_SECRET_KEY'] = secret
        result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', 'upgrade'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, env=os.environ)
        if result.returncode:
            # No connection URLs or credentials in caller-visible failure output.
            raise RuntimeError('Isolated migration failed: inspect database schema in dedicated QA database')
        from app import create_app
        from extensions import db
        from models import User
        from werkzeug.security import generate_password_hash
        app = create_app()
        with app.app_context():
            for role in ('admin', 'user'):
                db.session.add(User(nama=f'QA {role}', email=f'{role}@lms-qa.example.test',
                    password=generate_password_hash(password), role=role, status='aktif'))
            db.session.commit()
        print(json.dumps({'database': name, 'secret': secret, 'password': password,
            'admin_email': 'admin@lms-qa.example.test', 'user_email': 'user@lms-qa.example.test'}))
    elif '--serve' in sys.argv:
        name = os.getenv('DB_NAME', '')
        if not name.startswith('wakaf_qa_') or not name.endswith('_test'):
            raise RuntimeError('Refusing to serve QA against an existing application database')
        from app import create_app
        create_app().run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
