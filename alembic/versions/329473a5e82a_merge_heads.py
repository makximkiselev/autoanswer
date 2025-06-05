"""merge heads

Revision ID: 329473a5e82a
Revises: e56852b3e83a, df3fec2fc6e7
Create Date: 2025-06-01 15:05:54.339029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '329473a5e82a'
down_revision: Union[str, None] = ('e56852b3e83a', 'df3fec2fc6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
