-- Apply ONCE to the existing schema.sql database using your MySQL/MariaDB client.
-- No unrelated tables are changed. DDL implicitly commits in MySQL/MariaDB.
-- Back up before applying; do not use Flask autogenerate (models map partial tables).
-- Old penilaian records are preserved as completed; historical counts remain unknown.
ALTER TABLE penilaian
  ADD COLUMN status_attempt ENUM('in_progress','completed') NOT NULL DEFAULT 'completed',
  ADD COLUMN question_snapshot JSON NULL,
  ADD COLUMN passing_grade SMALLINT UNSIGNED NULL;
ALTER TABLE penilaian ALTER COLUMN status_attempt SET DEFAULT 'in_progress';

ALTER TABLE discussion
  ADD COLUMN context_type ENUM('course','material','test') NOT NULL DEFAULT 'course',
  ADD COLUMN tanggal_diperbarui DATETIME NULL,
  ADD COLUMN deleted_at DATETIME NULL;
UPDATE discussion SET context_type = 'material' WHERE id_materi IS NOT NULL;
ALTER TABLE discussion
  ADD INDEX idx_discussion_context (id_course, context_type, id_materi, status, waktu),
  ADD CONSTRAINT ck_discussion_context CHECK (
    (context_type = 'material' AND id_materi IS NOT NULL) OR
    (context_type IN ('course','test') AND id_materi IS NULL)
  );
-- Existing discussion.id_materi has no FK in schema.sql. API validates its course
-- and existence; adding a FK here could invalidate legacy rows, so it is omitted.
