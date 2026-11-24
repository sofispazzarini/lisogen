"""API de familiograma: apellido y lado (materno/paterno) del familiar, y avisos del último Familiograma.

Revision ID: 0004_familiograma_api
Revises: 0003_solicitud_obra_social
Create Date: 2026-11-24
"""

from alembic import op

revision = "0004_familiograma_api"
down_revision = "0003_solicitud_obra_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE lado_familiar AS ENUM ('MATERNO', 'PATERNO')")
    op.execute("ALTER TABLE familiar ADD COLUMN apellido text")
    op.execute("ALTER TABLE familiar ADD COLUMN lado lado_familiar")
    op.execute("ALTER TABLE paciente ADD COLUMN familiograma_advertencias jsonb NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE paciente DROP COLUMN familiograma_advertencias")
    op.execute("ALTER TABLE familiar DROP COLUMN lado")
    op.execute("ALTER TABLE familiar DROP COLUMN apellido")
    op.execute("DROP TYPE lado_familiar")
