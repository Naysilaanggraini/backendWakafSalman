"""API contract and permission tests with a mocked session; no database writes."""
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
from flask import Flask
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from extensions import db
from models import User
from routes.auth import auth_bp
from routes.users import users_bp


class UsersApiTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, JWT_SECRET_KEY="test-only-secret-for-users-api-fixtures")
        self.photos = TemporaryDirectory(prefix="wakaf-profile-test-")
        self.addCleanup(self.photos.cleanup)
        app.config["PROFILE_PHOTO_DIR"] = self.photos.name
        app.register_blueprint(auth_bp)
        app.register_blueprint(users_bp)
        self.client = app.test_client()
        self.admin = User(id_user=1, nama="Admin Test", email="admin@example.com", password="secret-hash", role="admin", status="aktif")
        self.user = User(id_user=2, nama="User Test", email="user@example.com", password="secret-hash", role="user", status="aktif")
        self.accounts = [self.admin, self.user]
        self.session = MagicMock()
        self.session.get.side_effect = lambda model, ident: next((user for user in self.accounts if user.id_user == ident), None)
        self.session.execute.return_value.scalars.return_value.all.side_effect = lambda: self.accounts
        self.session.add.side_effect = self.add_user
        self.patcher = patch.object(db, "session", self.session)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def add_user(self, user):
        user.id_user = 3
        self.accounts.append(user)

    def headers(self, ident=1):
        token = jwt.encode({"id_user": ident, "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "test-only-secret-for-users-api-fixtures", algorithm="HS256")
        return {"Authorization": "Bearer " + token}

    def test_list_requires_admin_and_omits_password(self):
        self.assertEqual(self.client.get("/api/users").status_code, 401)
        self.assertEqual(self.client.get("/api/users", headers=self.headers(2)).status_code, 403)
        response = self.client.get("/api/users", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["users"]), 2)
        self.assertNotIn("password", response.json["users"][0])
        self.assertEqual(response.json["users"][0]["id_user"], 1)

    def test_create_hashes_password_and_returns_actual_account(self):
        response = self.client.post("/api/users", headers=self.headers(), json={"nama": "New User", "email": "new@example.com", "password": "test-password", "divisi": "Program", "jabatan": "Staff"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["user"]["role"], "user")
        self.assertEqual(response.json["user"]["status"], "aktif")
        self.assertNotIn("password", response.json["user"])
        self.assertTrue(check_password_hash(self.accounts[-1].password, "test-password"))
        self.session.commit.assert_called_once()

    def test_validation_and_duplicate_email(self):
        self.assertEqual(self.client.post("/api/users", headers=self.headers(), json={"nama": "New", "email": "new@example.com"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/users/2", headers=self.headers(), json={"status": "active"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/users/2", headers=self.headers(), json={"foto_profil": "data:image/png;base64,abc"}).status_code, 400)
        self.session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
        response = self.client.patch("/api/users/2", headers=self.headers(), json={"email": "admin@example.com"})
        self.assertEqual(response.status_code, 409)
        self.session.rollback.assert_called()

    def test_profile_updates_only_own_allowed_fields(self):
        response = self.client.patch("/api/auth/me", headers=self.headers(2), json={"nama": "Updated", "divisi": "IT", "jabatan": "Staff", "foto_profil": "https://example.com/avatar.png"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.nama, "Updated")
        self.assertEqual(self.admin.nama, "Admin Test")
        profile = self.client.get("/api/auth/me", headers=self.headers(2)).json
        self.assertEqual(profile["jabatan"], "Staff")
        self.assertNotIn("password", profile)
        self.assertEqual(self.client.patch("/api/auth/me", headers=self.headers(2), json={"role": "admin"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/auth/me", headers=self.headers(2), json={"id_user": 1}).status_code, 400)

    def test_status_update_blocks_existing_token_and_can_reactivate(self):
        self.assertEqual(self.client.patch("/api/users/2", headers=self.headers(), json={"status": "nonaktif"}).status_code, 200)
        self.assertEqual(self.user.status, "nonaktif")
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(2)).status_code, 403)
        self.assertEqual(self.client.patch("/api/users/2", headers=self.headers(), json={"status": "aktif"}).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(2)).status_code, 200)

    def test_phone_create_update_clear_for_both_roles(self):
        for account in (self.user, self.admin):
            with self.subTest(role=account.role):
                headers = self.headers(account.id_user)
                self.assertEqual(self.client.get("/api/auth/me", headers=headers).json["user_profile"], {"no_hp": None})
                response = self.client.patch("/api/auth/me", headers=headers, json={"no_hp": "081234567890"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["user"]["user_profile"]["no_hp"], "081234567890")
                original = account.user_profile
                self.assertIs(original.user, account)
                response = self.client.patch("/api/auth/me", headers=headers, json={"no_hp": "+62 812-3456-7890"})
                self.assertEqual(response.status_code, 200)
                self.assertIs(account.user_profile, original)
                self.client.patch("/api/auth/me", headers=headers, json={"jabatan": "Staff"})
                self.assertEqual(self.client.get("/api/auth/me", headers=headers).json["user_profile"]["no_hp"], "+62 812-3456-7890")
                response = self.client.patch("/api/auth/me", headers=headers, json={"no_hp": ""})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(account.user_profile.no_hp)

    def test_phone_validation_and_account_isolation(self):
        for value in (12345, None, "1" * 31, "abc", "+()", "12+34"):
            response = self.client.patch("/api/auth/me", headers=self.headers(2), json={"no_hp": value})
            self.assertEqual(response.status_code, 400)
        self.session.commit.assert_not_called()
        self.assertEqual(self.client.patch("/api/auth/me", json={"no_hp": "081234567890"}).status_code, 401)
        self.assertEqual(self.client.patch("/api/auth/me", headers=self.headers(2), json={"no_hp": "081234567890", "id_user": 1}).status_code, 400)
        response = self.client.patch("/api/auth/me", headers=self.headers(2), data={"no_hp": "+6281234567890", "foto": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["user"]["user_profile"]["no_hp"], "+6281234567890")
        self.assertIsNone(self.admin.user_profile)

    def test_failed_phone_save_rolls_back(self):
        self.session.commit.side_effect = IntegrityError("update", {}, Exception("duplicate"))
        response = self.client.patch("/api/auth/me", headers=self.headers(2), json={"no_hp": "081234567890", "email": "admin@example.com"})
        self.assertEqual(response.status_code, 409)
        self.session.rollback.assert_called_once()

    def test_admin_cannot_demote_or_deactivate_self(self):
        for values in [{"role": "user"}, {"status": "nonaktif"}]:
            self.assertEqual(self.client.patch("/api/users/1", headers=self.headers(), json=values).status_code, 400)
        self.assertEqual(self.admin.status, "aktif")
        self.assertEqual(self.admin.role, "admin")
        self.session.commit.assert_not_called()

    def test_non_admin_cannot_write_and_missing_user_is_404(self):
        self.assertEqual(self.client.post("/api/users", headers=self.headers(2), json={"nama": "No"}).status_code, 403)
        self.assertEqual(self.client.patch("/api/users/1", headers=self.headers(2), json={"nama": "No"}).status_code, 403)
        self.assertEqual(self.client.patch("/api/users/999", headers=self.headers(), json={"nama": "Missing"}).status_code, 404)
        self.session.commit.assert_not_called()

    def test_inactive_admin_is_denied(self):
        self.admin.status = "nonaktif"
        self.assertEqual(self.client.get("/api/users", headers=self.headers()).status_code, 403)
        self.assertEqual(self.client.get("/api/auth/admin-test", headers=self.headers()).status_code, 403)

    def photo(self):
        data = BytesIO()
        Image.new("RGB", (32, 32), "blue").save(data, "PNG")
        data.seek(0)
        return data, "device-photo.png"

    def test_upload_and_serve_device_photo(self):
        response = self.client.patch("/api/auth/me", headers=self.headers(), data={"nama": "Admin Photo", "foto": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["user"]["foto_profil"].startswith("http://localhost/api/auth/profile-photos/"))
        self.assertTrue(self.admin.foto_profil.startswith("/api/auth/profile-photos/"))
        stored = list(Path(self.photos.name).glob("*.png"))
        self.assertEqual(len(stored), 1)
        image_response = self.client.get(self.admin.foto_profil)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/png")
        image_response.close()
        with Image.open(stored[0]) as photo:
            self.assertEqual(photo.size, (32, 32))

    def test_invalid_large_and_unauthenticated_uploads_are_rejected(self):
        self.assertEqual(self.client.patch("/api/auth/me", data={"nama": "Test", "foto": self.photo()}).status_code, 401)
        invalid = self.client.patch("/api/auth/me", headers=self.headers(), data={"nama": "Test", "foto": (BytesIO(b"not an image"), "fake.png")})
        self.assertEqual(invalid.status_code, 400)
        oversized = self.client.patch("/api/auth/me", headers=self.headers(), data={"nama": "Test", "foto": (BytesIO(b"x" * (3 * 1024 * 1024)), "large.png")})
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(list(Path(self.photos.name).iterdir()), [])
        self.session.commit.assert_not_called()

    def test_failed_save_removes_new_file_and_remove_photo_clears_field(self):
        self.session.commit.side_effect = IntegrityError("update", {}, Exception("duplicate"))
        response = self.client.patch("/api/auth/me", headers=self.headers(), data={"email": "taken@example.com", "foto": self.photo()})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(list(Path(self.photos.name).iterdir()), [])
        self.session.commit.side_effect = None
        response = self.client.patch("/api/auth/me", headers=self.headers(), json={"foto_profil": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["user"]["foto_profil"], "")


if __name__ == "__main__":
    unittest.main()
