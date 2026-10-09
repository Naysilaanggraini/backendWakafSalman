import os
import unittest
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from app import create_app
from config import load_config
from extensions import db


class ProductionConfigTests(unittest.TestCase):
    def environment(self, **changes):
        return {"APP_ENV": "production", "JWT_SECRET_KEY": "a" * 64,
                "DB_PASSWORD": "p@ss:/%word", "DB_USER": "user@name",
                "CORS_ORIGINS": "https://learn.example.test", **changes}

    def test_raw_database_credentials_are_encoded_by_sqlalchemy(self):
        with patch.dict(os.environ, self.environment(), clear=True):
            config = load_config()
        self.assertEqual(config["SQLALCHEMY_DATABASE_URI"].password, "p@ss:/%word")
        self.assertEqual(config["SQLALCHEMY_DATABASE_URI"].username, "user@name")

    def test_production_rejects_missing_secrets_and_wildcard_origins(self):
        for invalid in ({"JWT_SECRET_KEY": "short"}, {"DB_PASSWORD": ""},
                        {"CORS_ORIGINS": "*"}, {"CORS_ORIGINS": "http://example.test"}):
            with self.subTest(invalid=invalid), patch.dict(os.environ, self.environment(**invalid), clear=True):
                with self.assertRaises(ValueError):
                    load_config()

    def test_production_routes_cors_readiness_and_upload_limit(self):
        with patch.dict(os.environ, self.environment(ENABLE_DEV_ROUTES="true", FLASK_DEBUG="true"), clear=True):
            app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                              "SQLALCHEMY_ENGINE_OPTIONS": {}})
        client = app.test_client()
        self.assertFalse(app.debug)
        self.assertEqual(client.get("/db-test").status_code, 404)
        self.assertEqual(client.get("/user-test").status_code, 404)
        self.assertEqual(client.get("/health/live").status_code, 200)
        self.assertEqual(client.get("/health/ready").status_code, 503)
        allowed = client.get("/api/auth/me", headers={"Origin": "https://learn.example.test"})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], "https://learn.example.test")
        denied = client.get("/api/auth/me", headers={"Origin": "https://evil.example.test"})
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)
        self.assertEqual(client.post("/api/auth/login", data=b"x" * (3 * 1024 * 1024 + 1),
                                     content_type="application/json").status_code, 413)
        with app.app_context():
            db.session.execute(db.text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            db.session.execute(db.text("INSERT INTO alembic_version VALUES ('0001_baseline')"))
            db.session.commit()
        self.assertEqual(client.get("/health/ready").status_code, 503)
        with app.app_context():
            db.session.execute(db.text("UPDATE alembic_version SET version_num='0003_activity_tracking'"))
            db.session.commit()
        self.assertEqual(client.get("/health/ready").status_code, 200)
        with patch.object(db, "session") as session:
            session.execute.side_effect = OperationalError("secret connection info", {}, Exception("password"))
            response = client.get("/health/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json, {"status": "not_ready"})
            session.rollback.assert_called_once()
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
