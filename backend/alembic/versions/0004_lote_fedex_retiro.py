"""Id del retiro en FedEx: la API no tiene webhook y el estado se consulta por id (DECISIONES D2).

Revision ID: 0004_lote_fedex_retiro
Revises: 0003_solicitud_obra_social
Create Date: 2026-11-03
"""

from alembic import op

revision = "0004_lote_fedex_retiro"
down_revision = "0003_solicitud_obra_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lote ADD COLUMN fedex_retiro_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE lote DROP COLUMN fedex_retiro_id")
