"""Admin authoring over the same course/soal tables used by learners."""
from flask import Blueprint, request
from extensions import db
from models import Course, Question, Option
from routes.auth import token_required, admin_required
from routes.learning_access import LearningError, install_errors, payload

admin_assessment_bp = Blueprint('admin_assessment', __name__, url_prefix='/api/admin')
install_errors(admin_assessment_bp)


def course_record(course_id):
    course = db.session.execute(db.select(Course).where(Course.id_course == course_id)
        .with_for_update()).scalar_one_or_none()
    if not course:
        raise LearningError('Course tidak ditemukan', 404)
    return course


def question_data(q):
    return {'question_id': q.id_soal, 'pertanyaan': q.pertanyaan, 'urutan': q.urutan,
            'status': q.status, 'options': [{'option_id': o.id_pilihan, 'text': o.teks_pilihan,
            'urutan': o.urutan, 'is_correct': bool(o.is_benar)} for o in q.options]}


@admin_assessment_bp.route('/courses/<int:course_id>/test', methods=['GET', 'PATCH'])
@token_required
@admin_required
def test_settings(user, course_id):
    course = course_record(course_id)
    if request.method == 'PATCH':
        data = payload({'passing_grade', 'maksimal_attempt', 'masa_tunggu_test_hari'})
        if not data:
            raise LearningError('Pengaturan wajib diisi')
        for key, value in data.items():
            low, high = (0, 100) if key == 'passing_grade' else (1 if key == 'maksimal_attempt' else 0, 65535)
            if type(value) is not int or not low <= value <= high:
                raise LearningError(f'{key} tidak valid')
        for key, value in data.items():
            setattr(course, key, value)
        db.session.commit()
    rows = db.session.execute(db.select(Question).where(Question.id_course == course_id)
        .order_by(Question.urutan, Question.id_soal)).scalars().all()
    return {'course': course.to_dict(), 'passing_grade': course.passing_grade,
            'maksimal_attempt': course.maksimal_attempt, 'masa_tunggu_test_hari': course.masa_tunggu_test_hari,
            'questions': [question_data(q) for q in rows]}


def validate_question(data):
    text, order, status, options = (data.get(k) for k in ('pertanyaan', 'urutan', 'status', 'options'))
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 10000:
        raise LearningError('Pertanyaan wajib diisi, maksimal 10000 karakter')
    if type(order) is not int or not 1 <= order <= 65535 or not isinstance(status, str) or status not in ('aktif', 'nonaktif'):
        raise LearningError('Urutan atau status tidak valid')
    if not isinstance(options, list) or not 2 <= len(options) <= 6:
        raise LearningError('Soal memerlukan 2 sampai 6 pilihan')
    for o in options:
        if not isinstance(o, dict) or set(o) != {'text', 'urutan', 'is_correct'}:
            raise LearningError('Field pilihan tidak valid')
        if not isinstance(o['text'], str) or not o['text'].strip() or len(o['text'].strip()) > 255:
            raise LearningError('Teks pilihan wajib diisi, maksimal 255 karakter')
        if type(o['urutan']) is not int or not 1 <= o['urutan'] <= 65535 or type(o['is_correct']) is not bool:
            raise LearningError('Urutan atau kunci pilihan tidak valid')
    if sum(o['is_correct'] for o in options) != 1 or len({o['text'].strip().casefold() for o in options}) != len(options) or len({o['urutan'] for o in options}) != len(options):
        raise LearningError('Pilihan dan urutan harus berbeda, dengan tepat satu jawaban benar')
    return text.strip(), order, status, options


@admin_assessment_bp.post('/courses/<int:course_id>/test/questions')
@token_required
@admin_required
def create_question(user, course_id):
    course_record(course_id)
    return write_question(course_id), 201


def write_question(course_id, previous=None):
    text, order, status, options = validate_question(payload(
        {'pertanyaan', 'urutan', 'status', 'options'}, {'pertanyaan', 'urutan', 'status', 'options'}))
    # Retain old IDs/options for saved answers and immutable attempt snapshots.
    if previous:
        previous.status = 'nonaktif'
    q = Question(id_course=course_id, pertanyaan=text, urutan=order, status=status)
    db.session.add(q)
    for o in options:
        db.session.add(Option(question=q, teks_pilihan=o['text'].strip(), urutan=o['urutan'], is_benar=o['is_correct']))
    db.session.commit()
    return {'question': question_data(q)}


@admin_assessment_bp.route('/courses/<int:course_id>/test/questions/<int:question_id>', methods=['PATCH', 'DELETE'])
@token_required
@admin_required
def change_question(user, course_id, question_id):
    course_record(course_id)
    q = db.session.get(Question, question_id)
    if not q or q.id_course != course_id:
        raise LearningError('Soal tidak ditemukan pada course ini', 404)
    if request.method == 'PATCH':
        return write_question(course_id, q)
    q.status = 'nonaktif'
    db.session.commit()
    return {'question': question_data(q)}
