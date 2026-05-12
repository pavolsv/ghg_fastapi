"""add_fuel_type_to_utilitybill_and_heat_value_to_emissionrecord

Revision ID: a3f8e2d91c04
Revises: 1dc932b095c9
Create Date: 2026-03-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3f8e2d91c04'
down_revision: Union[str, Sequence[str], None] = '1dc932b095c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('utilitybill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fuel_type', sa.String(), nullable=True))

    with op.batch_alter_table('emissionrecord', schema=None) as batch_op:
        batch_op.add_column(sa.Column('heat_value', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('emissionrecord', schema=None) as batch_op:
        batch_op.drop_column('heat_value')

    with op.batch_alter_table('utilitybill', schema=None) as batch_op:
        batch_op.drop_column('fuel_type')
