"""Allow uploaded thumbnail data URLs without changing existing values."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0004_thumbnail_mediumtext'
down_revision = '0003_activity_tracking'
branch_labels = None
depends_on = None


def upgrade():
    for table, length in (('kategori', 255), ('course', 500)):
        op.alter_column(table, 'thumbnail', existing_type=sa.String(length),
                        type_=mysql.MEDIUMTEXT(), existing_nullable=True)


def downgrade():
    # Never silently truncate image data when reverting to the old URL columns.
    connection = op.get_bind()
    for table, length in (('kategori', 255), ('course', 500)):
        oversized = connection.scalar(sa.text(
            f'SELECT COUNT(*) FROM `{table}` WHERE CHAR_LENGTH(thumbnail) > :limit'), {'limit': length})
        if oversized:
            raise RuntimeError(f'Cannot downgrade: {table} has thumbnails longer than {length} characters')
    for table, length in (('kategori', 255), ('course', 500)):
        op.alter_column(table, 'thumbnail', existing_type=mysql.MEDIUMTEXT(),
                        type_=sa.String(length), existing_nullable=True)
