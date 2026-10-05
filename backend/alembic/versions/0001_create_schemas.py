"""create the seven logical schemas (core, booking, clinical, finance, content, edu, audit)

Revision ID: 0001
Revises:
Create Date: 2025-01-01
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ["core", "booking", "clinical", "finance", "content", "edu", "audit"]


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
