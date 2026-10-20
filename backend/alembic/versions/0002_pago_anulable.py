"""Pago anulable: con 5 inasistencias se pierde el pago y el Paciente vuelve a pagar (DECISIONES D1).

Revision ID: 0002_pago_anulable
Revises: 0001_initial
Create Date: 2026-10-19
"""

from alembic import op

revision = "0002_pago_anulable"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pago ADD COLUMN anulado_at timestamptz")
    op.execute("ALTER TABLE pago DROP CONSTRAINT pago_presupuesto_id_key")
    op.execute("CREATE UNIQUE INDEX ux_pago_vigente ON pago (presupuesto_id) WHERE anulado_at IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX ux_pago_vigente")
    op.execute("ALTER TABLE pago ADD CONSTRAINT pago_presupuesto_id_key UNIQUE (presupuesto_id)")
    op.execute("ALTER TABLE pago DROP COLUMN anulado_at")
