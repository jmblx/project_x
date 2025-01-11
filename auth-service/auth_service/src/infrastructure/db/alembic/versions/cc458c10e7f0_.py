"""empty message

Revision ID: cc458c10e7f0
Revises: 6bc3bf95afc7
Create Date: 2024-12-30 21:29:27.218383

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc458c10e7f0"
down_revision: Union[str, None] = "6bc3bf95afc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("user", sa.Column("avatar_path", sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("user", "avatar_path")
    # ### end Alembic commands ###