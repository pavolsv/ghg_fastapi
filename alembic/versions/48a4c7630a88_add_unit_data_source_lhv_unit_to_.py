"""add_unit_data_source_lhv_unit_to_emission_record

Revision ID: 48a4c7630a88
Revises: 26b883258402
Create Date: 2026-05-13 06:21:16.243382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '48a4c7630a88'
down_revision: Union[str, Sequence[str], None] = '26b883258402'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('emissionrecord', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unit', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('data_source', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('lhv_unit', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('emissionrecord', schema=None) as batch_op:
        batch_op.drop_column('lhv_unit')
        batch_op.drop_column('data_source')
        batch_op.drop_column('unit')