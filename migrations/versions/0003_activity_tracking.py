"""Add supported events and heartbeat state without rewriting historic logs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0003_activity_tracking'
down_revision = '0002_assessment'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('activity', sa.Column('time_basis', sa.String(10), nullable=True))
    op.alter_column('activity', 'jenis_aktivitas', existing_nullable=False,
        type_=mysql.ENUM('login', 'buka_course', 'buka_materi', 'selesai_materi',
                        'selesai_course', 'mulai_test', 'selesai_test', 'logout',
                        'buka_dashboard', 'putar_video', 'kirim_komentar', 'sesi'))
    op.create_table('activity_tracking',
        sa.Column('id_activity', mysql.BIGINT(unsigned=True), sa.ForeignKey('activity.id_activity'), primary_key=True),
        sa.Column('request_id', sa.String(36), nullable=False, unique=True),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('id_login_activity', mysql.BIGINT(unsigned=True), sa.ForeignKey('activity.id_activity'), nullable=True),
        sa.Column('running', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('finished', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('credited_ms', sa.BigInteger(), nullable=False, server_default='0'))


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled. Restore a verified backup.')
