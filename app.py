from flask import Flask
from flask_cors import CORS

from config import Config
from extensions import db, migrate
from models import User
from routes.auth import auth_bp
from routes.users import users_bp
from routes.kategori import kategori_bp
from routes.course import course_bp
from routes.materi import materi_bp
from routes.enrollment import enrollment_bp
from routes.progress import progress_bp
from routes.tests import tests_bp
from routes.discussions import discussions_bp


def create_app():
    app = Flask(__name__)

    # Load konfigurasi
    app.config.from_object(Config)

    # Inisialisasi database dan migration
    db.init_app(app)
    migrate.init_app(app, db)

    # Izinkan frontend React
    CORS(app, origins=["http://localhost:5173"])

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(kategori_bp)
    app.register_blueprint(course_bp)
    app.register_blueprint(materi_bp)
    app.register_blueprint(enrollment_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(tests_bp)
    app.register_blueprint(discussions_bp)

    @app.route("/")
    def home():
        return {
            "message": "Backend LMS Wakaf Salman berjalan"
        }

    @app.route("/db-test")
    def db_test():
        try:
            db.session.execute(db.text("SELECT 1"))

            return {
                "status": "success",
                "message": "Koneksi database berhasil"
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }, 500

    @app.route("/user-test")
    def user_test():
        try:
            user = db.session.execute(
                db.select(User).limit(1)
            ).scalar_one_or_none()

            if user is None:
                return {
                    "status": "success",
                    "message": "Model User berhasil terhubung, tetapi tabel users masih kosong"
                }

            return {
                "status": "success",
                "user": {
                    "id_user": user.id_user,
                    "nama": user.nama,
                    "email": user.email,
                    "role": user.role,
                    "status": user.status
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }, 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )
