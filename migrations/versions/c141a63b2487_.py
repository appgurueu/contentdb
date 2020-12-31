"""empty message

Revision ID: c141a63b2487
Revises: cb6ab141c522
Create Date: 2020-07-09 00:05:39.845465

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c141a63b2487'
down_revision = 'cb6ab141c522'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column('package', sa.Column('downloads', sa.Integer(), nullable=False, server_default="0"))


def downgrade():
	# ### commands auto generated by Alembic - please adjust! ###
	op.drop_column('package', 'downloads')
	# ### end Alembic commands ###