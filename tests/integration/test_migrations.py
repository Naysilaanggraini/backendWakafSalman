"""Destructive migration tests, ONLY in an explicitly disposable *_test database.

Example (use a disposable external database and a separate Compose project/env file):
  docker compose -p lentera-production-check --env-file /tmp/test.env run --rm \
    -e RUN_MARIADB_INTEGRATION=1 api python -m unittest discover -s tests/integration -v
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from sqlalchemy import create_engine, inspect, text
from config import load_config


@unittest.skipUnless(os.getenv("RUN_MARIADB_INTEGRATION") == "1", "Disposable MariaDB opt-in required")
class MigrationTests(unittest.TestCase):
    def setUp(self):
        config = load_config()
        url = config["SQLALCHEMY_DATABASE_URI"]
        if not url.database or not url.database.endswith("_test"):
            self.fail("Refusing destructive tests: DB_NAME must end with _test")
        self.engine = create_engine(url)
        self.addCleanup(self.engine.dispose)
        with self.engine.connect() as connection:
            connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in inspect(connection).get_table_names():
                connection.execute(text("DROP TABLE " + self.engine.dialect.identifier_preparer.quote(table)))
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            connection.commit()

    def cli(self, *args, succeeds=True):
        result = subprocess.run([sys.executable, "-m", "flask", "--app", "app", "db", *args],
                                capture_output=True, text=True)
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def sql_file(self, name):
        sql = "\n".join(line for line in Path(name).read_text().splitlines()
                        if not line.lstrip().startswith("--"))
        with self.engine.begin() as connection:
            for statement in sql.split(";"):
                if statement.strip():
                    connection.execute(text(statement))

    def test_fresh_upgrade_and_repeat(self):
        self.cli("upgrade")
        self.cli("upgrade")
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "0003_activity_tracking")
            self.assertEqual(len(inspect(connection).get_table_names()), 15)
            columns = {c["name"] for c in inspect(connection).get_columns("penilaian")}
            self.assertTrue({"status_attempt", "question_snapshot", "passing_grade"} <= columns)
        result = self.cli("downgrade", "0001_baseline", succeeds=False)
        self.assertIn("Destructive downgrade is disabled", result.stderr)

    def test_existing_baseline_requires_adoption_and_preserves_data(self):
        self.sql_file("schema.sql")
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (nama,email,password) VALUES ('Legacy','legacy@example.test','fixture')"))
            connection.execute(text("INSERT INTO kategori (nama_kategori) VALUES ('Legacy')"))
            connection.execute(text("INSERT INTO course (judul_course,id_kategori) VALUES ('Legacy',1)"))
            connection.execute(text("INSERT INTO penilaian (id_user,id_course,status,waktu_mulai,nilai) VALUES (1,1,'lulus',NOW(),80)"))
            connection.execute(text("INSERT INTO discussion (id_user,id_course,id_materi,isi_komentar) VALUES (1,1,1,'Legacy material discussion')"))
        result = self.cli("upgrade", succeeds=False)
        self.assertIn("Database is not empty", result.stderr)
        self.cli("stamp", "0001_baseline")
        self.cli("upgrade")
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT nilai,status_attempt FROM penilaian")).one()
            self.assertEqual(float(row.nilai), 80)
            self.assertEqual(row.status_attempt, "completed")
            self.assertEqual(connection.execute(text("SELECT context_type FROM discussion")).scalar(), "material")
            connection.execute(text("INSERT INTO penilaian (id_user,id_course,status,waktu_mulai,test_attempt) VALUES (1,1,'tidak_lulus',NOW(),2)"))
            self.assertEqual(connection.execute(text("SELECT status_attempt FROM penilaian WHERE test_attempt=2")).scalar(), "in_progress")

    def test_already_applied_manual_sql_can_be_stamped(self):
        self.sql_file("schema.sql")
        self.sql_file("migrations_sql/001_test_discussion.sql")
        self.cli("stamp", "0002_assessment")
        self.cli("upgrade")
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "0003_activity_tracking")

    def test_partial_manual_migration_is_rejected(self):
        self.sql_file("schema.sql")
        self.cli("stamp", "0001_baseline")
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE penilaian ADD COLUMN status_attempt VARCHAR(20)"))
        result = self.cli("upgrade", succeeds=False)
        self.assertIn("Assessment columns already exist", result.stderr)
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "0001_baseline")

    def test_production_admin_login_and_readiness(self):
        self.cli("upgrade")
        from app import create_app
        from extensions import db
        from models import User
        from werkzeug.security import check_password_hash
        app = create_app()
        runner = app.test_cli_runner()
        password = "disposable-admin-test-password"
        result = runner.invoke(args=["create-admin", "--email", "admin@example.test", "--name", "Admin"],
                               input=password + "\n" + password + "\n")
        self.assertEqual(result.exit_code, 0, result.output)
        duplicate = runner.invoke(args=["create-admin", "--email", "admin@example.test", "--name", "Admin"],
                                  input=password + "\n" + password + "\n")
        self.assertNotEqual(duplicate.exit_code, 0)
        with app.app_context():
            admin = db.session.execute(db.select(User).where(User.email == "admin@example.test")).scalar_one()
            self.assertEqual(admin.role, "admin")
            self.assertTrue(check_password_hash(admin.password, password))
        client = app.test_client()
        response = client.post("/api/auth/login", json={"email": "admin@example.test", "password": password})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(client.get("/health/ready").status_code, 200)
        self.assertEqual(client.get("/user-test").status_code, 404)
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
