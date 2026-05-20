"""add_lower_heating_value_and_lhv_unit_to_activity_data

Revision ID: 26b883258402
Revises: e32b8d3f9a65
Create Date: 2026-05-13 05:52:52.544593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '26b883258402'
down_revision: Union[str, Sequence[str], None] = 'e32b8d3f9a65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('activity_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lower_heating_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('lhv_unit', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('activity_data', schema=None) as batch_op:
        batch_op.drop_column('lhv_unit')
        batch_op.drop_column('lower_heating_value')