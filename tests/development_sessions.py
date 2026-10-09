"""Local QA helper, consumed privately by the browser runner; never an HTTP route."""
import json
from datetime import timedelta
import jwt
from app import create_app
from extensions import db
from models import User
from models.learning import utcnow


def sessions():
    app = create_app()
    if app.config["APP_ENV"] != "development":
        raise RuntimeError("Development database required")
    with app.app_context():
        records = {}
        for label, uid, role in (("learner", 3, "user"), ("admin", 2, "admin"), ("other", 1, "user")):
            user = db.session.get(User, uid)
            if not user or user.role != role or user.status != "aktif":
                raise RuntimeError("Existing QA identity unavailable")
            records[label] = {"token": jwt.encode({"id_user": uid, "exp": utcnow() + timedelta(minutes=20)},
                app.config["JWT_SECRET_KEY"], algorithm="HS256"), "user": user.to_dict()}
        return records


if __name__ == "__main__":
    # stdout must be captured by the runner, never printed into terminal/report logs.
    print(json.dumps(sessions()))
