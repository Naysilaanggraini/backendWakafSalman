"""Database-backed test authoring; revisions preserve historical answer references."""
from flask import Blueprint
from extensions import db
from models import Course, Question, Option
from routes.auth import token_required, admin_required
from routes.learning_access import LearningError, install_errors, payload

admin_tests_bp = Blueprint("admin_tests", __name__, url_prefix="/api/admin/courses")
install_errors(admin_tests_bp)


def course_record(course_id):
    course = db.session.execute(db.select(Course).where(Course.id_course == course_id)
        .with_for_update()).scalar_one_or_none()
    if not course:
        raise LearningError("Course tidak ditemukan", 404)
    return course


def question_data(q):
    return {"question_id": q.id_soal, "pertanyaan": q.pertanyaan, "urutan": q.urutan,
            "status": q.status, "options": [{"option_id": o.id_pilihan,
            "text": o.teks_pilihan, "urutan": o.urutan, "is_correct": bool(o.is_benar)} for o in q.options]}


def config_data(course):
    questions = db.session.execute(db.select(Question).where(Question.id_course == course.id_course)
        .order_by(Question.urutan, Question.id_soal)).scalars().all()
    return {"course": course.to_dict(), "passing_grade": course.passing_grade,
            "maksimal_attempt": course.maksimal_attempt, "masa_tunggu_test_hari": course.masa_tunggu_test_hari,
            "questions": [question_data(q) for q in questions]}


@admin_tests_bp.get("/<int:course_id>/test")
@token_required
@admin_required
def get_config(user, course_id):
    return config_data(course_record(course_id))


@admin_tests_bp.patch("/<int:course_id>/test")
@token_required
@admin_required
def save_settings(user, course_id):
    fields = {"passing_grade": (0, 100), "maksimal_attempt": (1, 65535),
              "masa_tunggu_test_hari": (0, 65535)}
    data = payload(fields)
    if not data:
        raise LearningError("Settings tidak boleh kosong")
    for key, value in data.items():
        low, high = fields[key]
        if type(value) is not int or not low <= value <= high:
            raise LearningError(f"{key} harus integer antara {low} dan {high}")
    course = course_record(course_id)
    for key, value in data.items():
        setattr(course, key, value)
    db.session.commit()
    return config_data(course)


def validate_question():
    data = payload({"pertanyaan", "urutan", "status", "options"}, {"pertanyaan", "urutan", "status", "options"})
    if not isinstance(data["pertanyaan"], str) or not data["pertanyaan"].strip() or len(data["pertanyaan"]) > 16000:
        raise LearningError("Pertanyaan harus diisi (maksimal 16000 karakter)")
    if type(data["urutan"]) is not int or not 1 <= data["urutan"] <= 65535:
        raise LearningError("Urutan soal harus antara 1 dan 65535")
    if data["status"] not in ("aktif", "nonaktif"):
        raise LearningError("Status soal tidak valid")
    options = data["options"]
    if not isinstance(options, list) or not 2 <= len(options) <= 6:
        raise LearningError("Soal membutuhkan 2–6 pilihan")
    for o in options:
        if not isinstance(o, dict) or set(o) != {"text", "urutan", "is_correct"}:
            raise LearningError("Field pilihan tidak valid")
        if not isinstance(o["text"], str) or not o["text"].strip() or len(o["text"].strip()) > 255:
            raise LearningError("Pilihan harus diisi (maksimal 255 karakter)")
        if type(o["urutan"]) is not int or not 1 <= o["urutan"] <= 65535 or type(o["is_correct"]) is not bool:
            raise LearningError("Urutan atau kunci pilihan tidak valid")
    if len({o["urutan"] for o in options}) != len(options) or len({o["text"].strip().casefold() for o in options}) != len(options):
        raise LearningError("Urutan dan teks pilihan harus berbeda")
    if sum(o["is_correct"] for o in options) != 1:
        raise LearningError("Pilih tepat satu jawaban benar")
    return data


def write_question(course_id, data, old=None):
    all_questions = db.session.execute(db.select(Question).where(Question.id_course == course_id)).scalars().all()
    occupied = next((q for q in all_questions if q != old and q.urutan == data["urutan"]), None)
    # Inactive historical versions can be moved to an unused order; snapshots keep their original number.
    to_archive = [q for q in (old, occupied) if q is not None]
    if occupied and occupied.status == "aktif":
        raise LearningError("Urutan soal sudah digunakan", 409)
    next_order = max([q.urutan for q in all_questions] + [data["urutan"]]) + 1
    if next_order + len(to_archive) > 65535:
        raise LearningError("Urutan arsip sudah mencapai batas", 409)
    for q in to_archive:
        q.status, q.urutan = "nonaktif", next_order
        next_order += 1
    db.session.flush()
    q = Question(id_course=course_id, pertanyaan=data["pertanyaan"].strip(), urutan=data["urutan"], status=data["status"])
    q.options = [Option(teks_pilihan=o["text"].strip(), urutan=o["urutan"], is_benar=o["is_correct"]) for o in data["options"]]
    db.session.add(q)
    db.session.commit()
    return {"question": question_data(q)}


@admin_tests_bp.post("/<int:course_id>/test/questions")
@token_required
@admin_required
def create_question(user, course_id):
    data = validate_question()
    course_record(course_id)
    return write_question(course_id, data), 201


def existing_question(course_id, question_id):
    q = db.session.get(Question, question_id)
    if not q or q.id_course != course_id:
        raise LearningError("Soal tidak ditemukan", 404)
    return q


@admin_tests_bp.patch("/<int:course_id>/test/questions/<int:question_id>")
@token_required
@admin_required
def update_question(user, course_id, question_id):
    data = validate_question()
    course_record(course_id)
    return write_question(course_id, data, existing_question(course_id, question_id))


@admin_tests_bp.delete("/<int:course_id>/test/questions/<int:question_id>")
@token_required
@admin_required
def deactivate_question(user, course_id, question_id):
    course_record(course_id)
    q = existing_question(course_id, question_id)
    q.status = "nonaktif"
    db.session.commit()
    return {"question": question_data(q), "message": "Soal dinonaktifkan; attempt lama tetap tersimpan."}
