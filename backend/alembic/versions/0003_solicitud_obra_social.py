"""Solicitud de cobertura en la API de Obras Sociales: id y URLs de simulación en el Presupuesto.

Revision ID: 0003_solicitud_obra_social
Revises: 0002_pago_anulable
Create Date: 2026-11-14
"""

from alembic import op

revision = "0003_solicitud_obra_social"
down_revision = "0002_pago_anulable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE presupuesto ADD COLUMN os_solicitud_id text")
    op.execute("ALTER TABLE presupuesto ADD COLUMN os_url_autorizar text")
    op.execute("ALTER TABLE presupuesto ADD COLUMN os_url_rechazar text")


def downgrade() -> None:
    op.execute("ALTER TABLE presupuesto DROP COLUMN os_url_rechazar")
    op.execute("ALTER TABLE presupuesto DROP COLUMN os_url_autorizar")
    op.execute("ALTER TABLE presupuesto DROP COLUMN os_solicitud_id")
