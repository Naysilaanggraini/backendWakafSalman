from flask import Blueprint
from extensions import db
from models import Discussion
from models.learning import utcnow
from routes.auth import token_required
from routes.tests import iso
from routes.learning_access import (LearningError, discussion_context, install_errors, payload, positive_id)


discussions_bp = Blueprint("discussions", __name__, url_prefix="/api")
install_errors(discussions_bp)


def scoped(course_id, material_id, context_type):
    return db.select(Discussion).where(Discussion.id_course == course_id,
        Discussion.id_materi == material_id, Discussion.context_type == context_type,
        Discussion.status == "tampil")


def serialize(comment):
    return {"discussion_id": comment.id_discussion, "user_id": comment.id_user,
            "user": {"id_user": comment.user.id_user, "nama": comment.user.nama},
            "context_type": comment.context_type,
            "context_id": comment.id_materi if comment.context_type == "material" else comment.id_course,
            "parent_id": comment.id_parent, "content": "" if comment.deleted_at else comment.isi_komentar,
            "created_at": iso(comment.waktu), "updated_at": iso(comment.tanggal_diperbarui),
            "deleted": bool(comment.deleted_at)}


def context_ids(user, context_type, context_id):
    return discussion_context(user, context_type, context_id)


def comment_content(data):
    content = data.get("content")
    if not isinstance(content, str) or not content.strip() or len(content.strip()) > 2000:
        raise LearningError("Content wajib diisi dan maksimal 2000 karakter")
    return content.strip()


@discussions_bp.route("/discussions/<context_type>/<int:context_id>", methods=["GET", "POST"])
@token_required
def discussions(user, context_type, context_id):
    from flask import request
    course_id, material_id = context_ids(user, context_type, context_id)
    if request.method == "GET":
        comments = db.session.execute(scoped(course_id, material_id, context_type)
            .order_by(Discussion.waktu, Discussion.id_discussion)).scalars().all()
        # A hidden parent hides its subtree; soft-deleted parents remain as placeholders.
        visible = {c.id_discussion: c for c in comments}
        def has_visible_ancestors(c):
            seen = {c.id_discussion}
            while c.id_parent:
                if c.id_parent in seen or c.id_parent not in visible:
                    return False
                seen.add(c.id_parent)
                c = visible[c.id_parent]
            return True
        return {"discussions": [serialize(c) for c in comments if has_visible_ancestors(c)]}, 200
    data = payload({"content", "parent_id"}, {"content"})
    content = comment_content(data)
    parent_id = data.get("parent_id")
    if parent_id is not None:
        if not positive_id(parent_id):
            raise LearningError("Parent discussion tidak valid")
        parent = db.session.execute(scoped(course_id, material_id, context_type)
            .where(Discussion.id_discussion == parent_id).with_for_update()).scalar_one_or_none()
        if not parent or parent.deleted_at:
            raise LearningError("Parent discussion tidak tersedia dalam context ini", 404)
        # Prevent replies beneath a hidden ancestor, including nested threads.
        ancestor = parent
        seen = set()
        while ancestor.id_parent:
            if ancestor.id_parent in seen:
                raise LearningError("Thread discussion tidak valid", 409)
            seen.add(ancestor.id_parent)
            ancestor = db.session.execute(scoped(course_id, material_id, context_type)
                .where(Discussion.id_discussion == ancestor.id_parent)).scalar_one_or_none()
            if not ancestor:
                raise LearningError("Thread discussion tidak tersedia", 404)
    comment = Discussion(id_user=user.id_user, id_course=course_id, id_materi=material_id,
        context_type=context_type, id_parent=parent_id, isi_komentar=content)
    db.session.add(comment)
    db.session.commit()
    return {"discussion": serialize(comment)}, 201


@discussions_bp.route("/discussions/<context_type>/<int:context_id>/<int:discussion_id>", methods=["PATCH", "DELETE"])
@token_required
def change_discussion(user, context_type, context_id, discussion_id):
    from flask import request
    course_id, material_id = context_ids(user, context_type, context_id)
    comment = db.session.execute(scoped(course_id, material_id, context_type)
        .where(Discussion.id_discussion == discussion_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if not comment:
        raise LearningError("Discussion tidak ditemukan", 404)
    if comment.id_user != user.id_user:
        raise LearningError("Discussion bukan milik Anda", 403)
    if comment.deleted_at:
        raise LearningError("Discussion sudah dihapus", 409)
    if request.method == "PATCH":
        comment.isi_komentar = comment_content(payload({"content"}, {"content"}))
        comment.tanggal_diperbarui = utcnow()
    else:
        payload(())
        comment.deleted_at = utcnow()
        comment.isi_komentar = ""
    db.session.commit()
    return {"discussion": serialize(comment)}, 200
