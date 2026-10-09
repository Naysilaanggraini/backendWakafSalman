"""Real ORM transactions against disposable SQLite memory only, never .env DB.

Explicit fixture DDL and create_all are restricted to SQLite memory only.
MariaDB enum/FK/locking behavior still requires a separate integration check.
"""
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jwt
from flask import Flask
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User, Activity
from routes.auth import auth_bp
from routes.users import users_bp
from routes.reporting import reporting_bp
from services.activity import record_activity


class IdentityReportingTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.photos = TemporaryDirectory(prefix="identity-reporting-test-")
        self.addCleanup(self.photos.cleanup)
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                               JWT_SECRET_KEY="identity-tests-only-key-at-least-32-characters",
                               PROFILE_PHOTO_DIR=self.photos.name)
        db.init_app(self.app)
        for blueprint in (auth_bp, users_bp, reporting_bp):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.session.execute(text("PRAGMA foreign_keys = ON"))
        # The IDs use SQLite's integer primary key for auto-increment in tests.
        for statement in (
            "CREATE TABLE users (id_user INTEGER PRIMARY KEY, nama VARCHAR(150) NOT NULL, email VARCHAR(150) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, divisi VARCHAR(100), jabatan VARCHAR(100), role VARCHAR(10) NOT NULL, status VARCHAR(10) NOT NULL, foto_profil VARCHAR(500), tanggal_dibuat DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, terakhir_login DATETIME)",
            "CREATE TABLE user_profile (id_profile INTEGER PRIMARY KEY, id_user INTEGER UNIQUE NOT NULL REFERENCES users(id_user), no_hp VARCHAR(30), tanggal_diperbarui DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)",
            "CREATE TABLE activity (id_activity INTEGER PRIMARY KEY, id_user INTEGER NOT NULL REFERENCES users(id_user), id_course INTEGER, id_materi INTEGER, id_penilaian INTEGER, jenis_aktivitas VARCHAR(30) NOT NULL, durasi INTEGER, waktu_dimulai DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, waktu_selesai DATETIME)",
        ):
            db.session.execute(text(statement))
        db.session.execute(text('ALTER TABLE activity ADD COLUMN time_basis VARCHAR(10)'))
        # Reporting now joins real course/material relations; create missing fixture tables.
        db.create_all()
        password_hash = generate_password_hash("test-password")
        db.session.add_all([
            User(id_user=1, nama="Admin", email="admin@example.test", password=password_hash, role="admin", status="aktif"),
            User(id_user=2, nama="User", email="user@example.test", password=password_hash, role="user", status="aktif"),
            User(id_user=3, nama="Inactive", email="inactive@example.test", password=password_hash, role="user", status="nonaktif"),
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def headers(self, actor=1, **claims):
        payload = {"id_user": actor, "exp": datetime.now(timezone.utc) + timedelta(minutes=5), **claims}
        return {"Authorization": "Bearer " + jwt.encode(payload, self.app.config["JWT_SECRET_KEY"], algorithm="HS256")}

    def test_registration_and_duplicate(self):
        body = {"nama": " New ", "email": " new@example.test ", "password": "test-password", "role": "admin", "status": "nonaktif"}
        self.assertEqual(self.client.post("/api/auth/register", json=body).status_code, 201)
        user = db.session.execute(db.select(User).where(User.email == "new@example.test")).scalar_one()
        self.assertEqual((user.nama, user.role, user.status), ("New", "user", "aktif"))
        self.assertTrue(check_password_hash(user.password, "test-password"))
        self.assertEqual(self.client.post("/api/auth/register", json=body).status_code, 409)

    def test_invalid_auth_inputs(self):
        for endpoint in ("register", "login"):
            for body in ([], "bad", {"email": 123, "password": []}, {}):
                self.assertEqual(self.client.post("/api/auth/" + endpoint, json=body).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/register", json={"nama": "x", "email": "invalid", "password": "x"}).status_code, 400)

    def test_login_logs_only_success_and_preserves_contract(self):
        for email, password, status in (("inactive@example.test", "test-password", 403), ("user@example.test", "wrong", 401)):
            self.assertEqual(self.client.post("/api/auth/login", json={"email": email, "password": password}).status_code, status)
        self.assertEqual(db.session.query(Activity).count(), 0)
        result = self.client.post("/api/auth/login", json={"email": "user@example.test", "password": "test-password"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.json), {"token", "user", "message"})
        self.assertNotIn("password", result.json["user"])
        event = db.session.execute(db.select(Activity)).scalar_one()
        self.assertEqual((event.id_user, event.jenis_aktivitas), (2, "login"))
        self.assertIsNotNone(db.session.get(User, 2).terakhir_login)
        headers = {"Authorization": "Bearer " + result.json["token"]}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/admin-test", headers=headers).status_code, 403)

    def test_login_transaction_failure_rolls_back(self):
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("test failure")):
            response = self.client.post("/api/auth/login", json={"email": "user@example.test", "password": "test-password"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("token", response.json)
        self.assertEqual(db.session.query(Activity).count(), 0)
        self.assertIsNone(db.session.get(User, 2).terakhir_login)

    def test_invalid_tokens_and_database_role(self):
        for payload in ({"id_user": 2}, {"exp": 9999999999}, {"id_user": "2", "exp": 9999999999}, {"id_user": True, "exp": 9999999999}, {"id_user": 2, "exp": 1}):
            token = jwt.encode(payload, self.app.config["JWT_SECRET_KEY"], algorithm="HS256")
            self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/admin-test", headers=self.headers(2, role="admin")).status_code, 403)

    def test_admin_phone_and_profile_persistence(self):
        response = self.client.post("/api/users", headers=self.headers(), json={"nama": "New", "email": "new@example.test", "password": "test-password", "no_hp": "081234567890"})
        self.assertEqual(response.status_code, 201)
        actor = response.json["user"]["id_user"]
        db.session.remove()
        self.assertEqual(db.session.get(User, actor).user_profile.no_hp, "081234567890")
        response = self.client.patch(f"/api/users/{actor}", headers=self.headers(), json={"no_hp": "+6281234567890"})
        self.assertEqual(response.status_code, 200)
        db.session.remove()
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(actor)).json["user_profile"]["no_hp"], "+6281234567890")
        self.assertEqual(self.client.patch("/api/auth/me", headers=self.headers(actor), json={"id_user": 1, "no_hp": "123"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/auth/me", headers=self.headers(actor), json={"no_hp": ""}).status_code, 200)
        db.session.remove()
        self.assertIsNone(db.session.get(User, actor).user_profile.no_hp)

    def test_photo_only_upload(self):
        image = BytesIO()
        Image.new("RGB", (8, 8)).save(image, format="PNG")
        image.seek(0)
        response = self.client.patch("/api/auth/me", headers=self.headers(2), data={"foto": (image, "photo.png")})
        self.assertEqual(response.status_code, 200)
        db.session.remove()
        self.assertTrue(db.session.get(User, 2).foto_profil.startswith("/api/auth/profile-photos/"))

    def test_reporting_access_counts_and_dependencies(self):
        for path in ("/api/activity", "/api/dashboard"):
            self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.client.get(path, headers=self.headers(2)).status_code, 403)
            self.assertEqual(self.client.get(path, headers=self.headers(3)).status_code, 403)
        response = self.client.get("/api/dashboard", headers=self.headers())
        self.assertEqual(response.json["identity"], {"total_users": 3, "active_users": 2, "inactive_users": 1, "admins": 1, "regular_users": 2})
        self.assertIsNone(response.json["learning"])
        self.assertIsNone(response.json["assessment"])
        self.assertEqual(self.client.get("/api/leaderboard").status_code, 401)
        response = self.client.get("/api/leaderboard", headers=self.headers(2))
        self.assertEqual(response.status_code, 501)
        self.assertNotIn("rankings", response.json)

    def test_activity_filter_pagination_and_rollback(self):
        record_activity(2, "login")
        db.session.rollback()
        self.assertEqual(db.session.query(Activity).count(), 0)
        for actor in (1, 2, 2):
            record_activity(actor, "login")
        db.session.commit()
        response = self.client.get("/api/activity?id_user=2&jenis_aktivitas=login&per_page=1&page=2", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["pagination"], {"total": 2, "pages": 2, "page": 2, "per_page": 1})
        self.assertEqual(len(response.json["activities"]), 1)
        self.assertEqual(response.json["activities"][0]["id_user"], 2)
        for query in ("page=0", "per_page=101", "page=x", "id_user=-1", "jenis_aktivitas=register"):
            self.assertEqual(self.client.get("/api/activity?" + query, headers=self.headers()).status_code, 400)
        with self.assertRaises(ValueError):
            record_activity(1, "register")
        self.assertEqual(self.client.post("/api/activity", headers=self.headers(), json={}).status_code, 405)
