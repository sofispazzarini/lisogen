"""Id del retiro en FedEx: la API no tiene webhook y el estado se consulta por id (DECISIONES D3).

Revision ID: 0005_lote_fedex_retiro
Revises: 0004_familiograma_api
Create Date: 2026-11-03
"""

from alembic import op

revision = "0005_lote_fedex_retiro"
down_revision = "0004_familiograma_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lote ADD COLUMN fedex_retiro_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE lote DROP COLUMN fedex_retiro_id")
