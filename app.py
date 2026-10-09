from flask import Flask
from flask_cors import CORS

from config import load_config
from commands import register_commands
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
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
from routes.reporting import reporting_bp
from routes.admin_assessment import admin_assessment_bp
from routes.activity_tracking import tracking_bp
from routes.logout import logout_bp


def create_app(test_config=None):
    app = Flask(__name__)

    # Load konfigurasi
    app.config.update(load_config())
    if test_config:
        app.config.update(test_config)
    if app.config["PROXY_HOPS"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config["PROXY_HOPS"],
                                x_proto=app.config["PROXY_HOPS"])

    register_commands(app)

    # Inisialisasi database dan migration
    db.init_app(app)
    migrate.init_app(app, db)

    # Izinkan frontend React
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(kategori_bp)
    app.register_blueprint(course_bp)
    app.register_blueprint(materi_bp)
    app.register_blueprint(enrollment_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(tests_bp)
    app.register_blueprint(discussions_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(admin_assessment_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(logout_bp)

    @app.route("/")
    def home():
        return {
            "message": "Backend LMS Wakaf Salman berjalan"
        }

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            db.session.execute(db.text("SELECT 1"))
            # Refuse readiness on a reachable but unmigrated database.
            revision = db.session.execute(db.text("SELECT version_num FROM alembic_version")).scalar()
            from alembic.config import Config as AlembicConfig
            from alembic.script import ScriptDirectory
            from pathlib import Path
            config = AlembicConfig()
            config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
            if revision != ScriptDirectory.from_config(config).get_current_head():
                return {"status": "not_ready"}, 503
        except SQLAlchemyError:
            db.session.rollback()
            return {"status": "not_ready"}, 503
        return {"status": "ok"}

    if app.config["ENABLE_DEV_ROUTES"]:
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
        debug=app.config["DEBUG"],
        host="0.0.0.0",
        port=5000
    )
