from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint
from extensions import db
from models import Material, MaterialProgress, Question, Option, TestAttempt, UserAnswer
from models.learning import utcnow
from routes.auth import token_required
from routes.learning_access import LearningError, course_access, install_errors, payload, positive_id


tests_bp = Blueprint("tests", __name__, url_prefix="/api")
install_errors(tests_bp)


def iso(value):
    return value.isoformat() + "Z" if value else None


def questions_for(course_id):
    return db.session.execute(db.select(Question).where(Question.id_course == course_id,
        Question.status == "aktif").order_by(Question.urutan, Question.id_soal)).scalars().all()


def snapshot_question(question):
    return {"question_id": question.id_soal, "number": question.urutan, "pertanyaan": question.pertanyaan,
            "options": [{"option_id": o.id_pilihan, "text": o.teks_pilihan, "is_correct": bool(o.is_benar)} for o in question.options]}


def public_questions(snapshot):
    return [{"question_id": q["question_id"], "number": q["number"], "pertanyaan": q["pertanyaan"],
             "options": [{"option_id": o["option_id"], "text": o["text"]} for o in q["options"]]} for q in snapshot]


def attempt_data(attempt):
    return {"attempt_id": attempt.id_penilaian, "course_id": attempt.id_course,
            "test_id": attempt.id_course, "attempt_number": attempt.test_attempt,
            "status": attempt.status_attempt, "started_at": iso(attempt.waktu_mulai),
            "completed_at": iso(attempt.waktu_selesai),
            "answers": [{"question_id": a.id_soal, "selected_option_id": a.id_pilihan} for a in attempt.answers]}


def result_data(attempt):
    if attempt.status_attempt != "completed":
        raise LearningError("Attempt belum selesai", 409)
    # Old records never had a frozen question set; do not invent historical counts.
    total = len(attempt.question_snapshot) if attempt.question_snapshot is not None else None
    correct = sum(a.benar for a in attempt.answers) if total is not None else None
    return {"attempt_id": attempt.id_penilaian, "course_id": attempt.id_course, "test_id": attempt.id_course,
            "total_questions": total, "answered_questions": len(attempt.answers) if total is not None else None,
            "correct_answers": correct, "wrong_answers": total - correct if total is not None else None,
            "score": float(attempt.nilai), "passing_score": attempt.passing_grade,
            "passed": attempt.status == "lulus", "completed_at": iso(attempt.waktu_selesai)}


def owned_attempt(user, attempt_id, active=False):
    attempt = db.session.execute(db.select(TestAttempt).where(
        TestAttempt.id_penilaian == attempt_id)).scalar_one_or_none()
    if not attempt:
        raise LearningError("Attempt tidak ditemukan", 404)
    if attempt.id_user != user.id_user:
        raise LearningError("Attempt bukan milik Anda", 403)
    course_access(user, attempt.id_course, lock=active)
    if active:
        # Every mutation locks enrollment THEN attempt, matching start_test.
        attempt = db.session.execute(db.select(TestAttempt).where(TestAttempt.id_penilaian == attempt_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one()
    if active and attempt.status_attempt != "in_progress":
        raise LearningError("Attempt sudah selesai", 409)
    return attempt


def ready(course, enrollment):
    ids = db.session.execute(db.select(Material.id_materi).where(Material.id_course == course.id_course,
        Material.status == "aktif")).scalars().all()
    completed = set(db.session.execute(db.select(MaterialProgress.id_materi).where(
        MaterialProgress.id_user == enrollment.id_user, MaterialProgress.id_materi.in_(ids),
        MaterialProgress.status == "selesai")).scalars().all())
    return bool(ids) and set(ids) <= completed


@tests_bp.get("/courses/<int:course_id>/test")
@token_required
def get_test(user, course_id):
    course, enrollment = course_access(user, course_id)
    questions = questions_for(course_id)
    attempts = db.session.execute(db.select(TestAttempt).where(TestAttempt.id_user == user.id_user,
        TestAttempt.id_course == course_id).order_by(TestAttempt.test_attempt.desc())).scalars().all()
    active = next((a for a in attempts if a.status_attempt == "in_progress"), None)
    latest = next((a for a in attempts if a.status_attempt == "completed"), None)
    if not questions and not active and not latest:
        raise LearningError("Test tidak ditemukan", 404)
    return {"course_id": course_id, "test_id": course_id, "passing_score": course.passing_grade,
            "max_attempts": course.maksimal_attempt, "attempts_used": len(attempts),
            "materials_completed": ready(course, enrollment), "test_access_status": enrollment.status_test,
            "retry_at": iso(enrollment.test_dapat_diakses_lagi),
            "questions": public_questions(active.question_snapshot if active else [snapshot_question(q) for q in questions]),
            "active_attempt": attempt_data(active) if active else None,
            "latest_result": result_data(latest) if latest else None}, 200


@tests_bp.get("/courses/<int:course_id>/questions/<int:question_id>")
@token_required
def get_question(user, course_id, question_id):
    course_access(user, course_id)
    question = db.session.get(Question, question_id)
    if not question or question.id_course != course_id or question.status != "aktif":
        raise LearningError("Soal tidak ditemukan", 404)
    return {"question": public_questions([snapshot_question(question)])[0]}, 200


@tests_bp.post("/courses/<int:course_id>/test-attempts")
@token_required
def start_test(user, course_id):
    payload(())
    # Enrollment is the shared per-user/course mutex, including the first attempt.
    course, enrollment = course_access(user, course_id, lock=True)
    attempts = db.session.execute(db.select(TestAttempt).where(TestAttempt.id_user == user.id_user,
        TestAttempt.id_course == course_id).order_by(TestAttempt.test_attempt.desc())
        .with_for_update().execution_options(populate_existing=True)).scalars().all()
    active = next((a for a in attempts if a.status_attempt == "in_progress"), None)
    if active:
        return {"attempt": attempt_data(active), "questions": public_questions(active.question_snapshot)}, 200
    if len(attempts) >= course.maksimal_attempt or any(a.status == "lulus" for a in attempts):
        raise LearningError("Test sudah lulus atau batas attempt tercapai", 403)
    if enrollment.status_test == "lulus" or (enrollment.status_test == "nonaktif" and
        (not enrollment.test_dapat_diakses_lagi or enrollment.test_dapat_diakses_lagi > utcnow())):
        raise LearningError("Test belum dapat diakses kembali", 403)
    if enrollment.test_dapat_diakses_lagi and enrollment.test_dapat_diakses_lagi > utcnow():
        raise LearningError("Masa tunggu test belum selesai", 403)
    if not ready(course, enrollment):
        raise LearningError("Selesaikan seluruh materi terlebih dahulu", 403)
    snapshot = [snapshot_question(q) for q in questions_for(course_id)]
    if not snapshot:
        raise LearningError("Test tidak ditemukan", 404)
    if any(len(q["options"]) < 2 or sum(o["is_correct"] for o in q["options"]) != 1 for q in snapshot):
        raise LearningError("Konfigurasi soal belum valid", 409)
    if not 0 <= course.passing_grade <= 100:
        raise LearningError("Passing score tidak valid", 409)
    attempt = TestAttempt(id_user=user.id_user, id_course=course_id,
        test_attempt=max((a.test_attempt for a in attempts), default=0) + 1,
        question_snapshot=snapshot, passing_grade=course.passing_grade)
    enrollment.status_test = "aktif"
    db.session.add(attempt)
    db.session.commit()
    return {"attempt": attempt_data(attempt), "questions": public_questions(snapshot)}, 201


def save_answers(attempt, entries):
    if not isinstance(entries, list) or not entries or len(entries) > len(attempt.question_snapshot):
        raise LearningError("Daftar answers tidak valid")
    questions = {q["question_id"]: q for q in attempt.question_snapshot}
    seen = set()
    validated = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"question_id", "selected_option_id"}:
            raise LearningError("Field jawaban tidak valid")
        qid, oid = entry["question_id"], entry["selected_option_id"]
        if not positive_id(qid) or not positive_id(oid) or qid in seen:
            raise LearningError("ID jawaban tidak valid atau soal duplikat")
        seen.add(qid)
        question = questions.get(qid)
        if not question:
            raise LearningError("Soal bukan bagian dari test")
        if not any(o["option_id"] == oid for o in question["options"]):
            raise LearningError("Pilihan bukan bagian dari soal")
        option = db.session.get(Option, oid)
        if not option or option.id_soal != qid:
            raise LearningError("Soal atau pilihan tidak ditemukan", 404)
        validated.append((qid, oid))
    existing = {a.id_soal: a for a in attempt.answers}
    for qid, oid in validated:
        answer = existing.get(qid)
        if not answer:
            answer = UserAnswer(attempt=attempt, id_user=attempt.id_user, id_soal=qid, id_pilihan=oid)
            db.session.add(answer)
        answer.id_pilihan, answer.waktu_jawab = oid, utcnow()


@tests_bp.get("/test-attempts/<int:attempt_id>")
@token_required
def get_attempt(user, attempt_id):
    attempt = owned_attempt(user, attempt_id)
    return {"attempt": attempt_data(attempt)}, 200


@tests_bp.post("/test-attempts/<int:attempt_id>/answers")
@token_required
def answer_test(user, attempt_id):
    data = payload({"answers"}, {"answers"})
    attempt = owned_attempt(user, attempt_id, active=True)
    save_answers(attempt, data["answers"])
    db.session.commit()
    return {"attempt": attempt_data(attempt)}, 200


@tests_bp.post("/test-attempts/<int:attempt_id>/submit")
@token_required
def submit_test(user, attempt_id):
    data = payload({"answers"})
    attempt = owned_attempt(user, attempt_id, active=True)
    if "answers" in data:
        save_answers(attempt, data["answers"])
    db.session.flush()
    answers = {a.id_soal: a for a in attempt.answers}
    correct = 0
    for q in attempt.question_snapshot:
        answer = answers.get(q["question_id"])
        if answer:
            answer.benar = any(o["option_id"] == answer.id_pilihan and o["is_correct"] for o in q["options"])
            correct += int(answer.benar)
    total = len(attempt.question_snapshot)
    # Compare the unrounded ratio to the threshold; rounding cannot turn failure into a pass.
    raw_score = Decimal(correct) * 100 / Decimal(total)
    attempt.nilai = raw_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    passed = raw_score >= attempt.passing_grade
    attempt.status = "lulus" if passed else "tidak_lulus"
    attempt.status_attempt, attempt.waktu_selesai = "completed", utcnow()
    attempt.durasi = max(0, int((attempt.waktu_selesai - attempt.waktu_mulai).total_seconds()))
    course, enrollment = course_access(user, attempt.id_course, lock=True)
    if passed:
        enrollment.status_test = "lulus"
        enrollment.test_dapat_diakses_lagi = None
        enrollment.status = "selesai"
        enrollment.tanggal_selesai = attempt.waktu_selesai
    elif course.masa_tunggu_test_hari:
        enrollment.status_test = "nonaktif"
        enrollment.test_dapat_diakses_lagi = attempt.waktu_selesai + timedelta(days=course.masa_tunggu_test_hari)
    db.session.commit()
    return result_data(attempt), 200


@tests_bp.get("/test-attempts/<int:attempt_id>/result")
@token_required
def get_result(user, attempt_id):
    return result_data(owned_attempt(user, attempt_id)), 200
