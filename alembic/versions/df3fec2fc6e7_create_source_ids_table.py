from alembic import op
import sqlalchemy as sa

"""create source_ids table"""

revision = 'df3fec2fc6e7'  # ← это должно совпадать с именем файла до _
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'source_ids',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.Text, nullable=False, unique=True),
        sa.Column('type', sa.Text, nullable=False),
    )
    op.create_check_constraint(
        "chk_source_type",
        "source_ids",
        "type IN ('channel', 'chat')"
    )


def downgrade():
    op.drop_table('source_ids')
