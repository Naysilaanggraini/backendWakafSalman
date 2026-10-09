"""Opt-in API QA against existing development identities; never edits users/passwords.

Adds enrollment/completion and one failed attempt for existing user 1, preserves all
attempts, and authors new question versions through the admin API. Not unittest discovery.
"""
import os
import json
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from sqlalchemy import text
from app import create_app
from extensions import db
from tests.development_sessions import sessions


def main():
    if os.getenv("RUN_LIVE_TEST_QA") != "1":
        raise RuntimeError("Explicit development QA opt-in required")
    actors = sessions()

    def api(actor, path, method="GET", body=None):
        request = Request("http://127.0.0.1:5000/api" + path, method=method,
            headers={"Authorization": "Bearer " + actors[actor]["token"], "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        return response.status, json.load(response)

    app = create_app()
    with app.app_context():
        accounts_before = db.session.execute(text("SELECT * FROM users ORDER BY id_user")).all()
    status, enrollment = api("other", "/course/1/enrollment", "POST", {})
    assert status in (201, 409)
    before = api("other", "/me/course/1/progress")[1]["progress"]
    if before["progress"] < 100:
        assert api("other", "/courses/1/test-attempts", "POST", {})[0] == 403
        print("PASS incomplete materials blocked on live MariaDB")
    assert api("other", "/me/materi/1/progress", "PATCH", {"status": "selesai"})[0] == 200
    status, started = api("other", "/courses/1/test-attempts", "POST", {})
    assert status in (200, 201), "Existing user B blocked; no bypass performed"
    aid = started["attempt"]["attempt_id"]
    frozen = started["questions"]
    assert len(frozen) >= 2
    q = frozen[0]
    oid = q["options"][0]["option_id"]
    assert api("other", f"/test-attempts/{aid}/answers", "POST", {"answers": [{"question_id": q["question_id"], "selected_option_id": oid}]})[0] == 200
    current = api("other", "/courses/1/test")[1]
    assert current["active_attempt"]["attempt_id"] == aid
    assert current["active_attempt"]["answers"][0]["selected_option_id"] == oid
    assert api("other", "/courses/1/test-attempts", "POST", {})[1]["attempt"]["attempt_id"] == aid
    print("PASS live partial answer persistence and resume without new attempt")
    for suffix in ("", "/result"):
        assert api("learner", f"/test-attempts/{aid}{suffix}")[0] == 403
    assert api("learner", f"/test-attempts/{aid}/answers", "POST", {"answers": [{"question_id": q["question_id"], "selected_option_id": oid}]})[0] == 403
    assert api("learner", f"/test-attempts/{aid}/submit", "POST", {})[0] == 403
    print("PASS bidirectional two-user isolation read answers submit result")
    cfg = api("admin", "/admin/courses/1/test")[1]
    author_q = next(item for item in cfg["questions"] if item["question_id"] == q["question_id"])
    changed = {"pertanyaan": author_q["pertanyaan"] + " (revisi)", "urutan": author_q["urutan"], "status": "aktif",
        "options": [{"text": o["text"], "urutan": o["urutan"], "is_correct": o["is_correct"]} for o in author_q["options"]]}
    status, updated = api("admin", f"/admin/courses/1/test/questions/{q['question_id']}", "PATCH", changed)
    assert status == 200
    try:
        assert api("admin", "/admin/courses/1/test", "PATCH", {"passing_grade": 80})[0] == 200
        frozen_after = api("other", "/courses/1/test")[1]
        assert frozen_after["questions"] == frozen
        assert frozen_after["passing_score"] == 70
        assert api("other", f"/courses/1/questions/{q['question_id']}")[1]["question"] == q
        assert "is_correct" not in json.dumps(frozen_after)
        print("PASS live snapshot and passing grade unchanged after author edits")
        # Only the first answer saved: second question is unanswered, score must be 50.
        status, result = api("other", f"/test-attempts/{aid}/submit", "POST", {})
        assert status == 200 and result["score"] == 50 and not result["passed"]
        metadata = api("other", "/courses/1/test")[1]
        assert metadata["can_start"] is False and metadata["retry_at"]
        from datetime import datetime
        delta = datetime.fromisoformat(metadata["retry_at"].replace("Z", "+00:00")) - datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00"))
        assert delta == timedelta(days=7)
        assert api("other", "/courses/1/test-attempts", "POST", {})[0] == 403
        assert api("other", f"/test-attempts/{aid}/result")[1] == result
        print("PASS live backend score 50 failed persisted and exact 7-day retry blocked")
        latest = api("admin", "/admin/courses/1/test")[1]
        assert any(item["question_id"] == updated["question"]["question_id"] and item["status"] == "aktif" for item in latest["questions"])
    finally:
        assert api("admin", "/admin/courses/1/test", "PATCH", {"passing_grade": cfg["passing_grade"]})[0] == 200
    with app.app_context():
        assert db.session.execute(text("SELECT * FROM users ORDER BY id_user")).all() == accounts_before
        print("PASS existing account rows unchanged")
        print("attempt_ids", [row[0] for row in db.session.execute(text("SELECT id_penilaian FROM penilaian ORDER BY id_penilaian"))])


if __name__ == "__main__":
    main()
