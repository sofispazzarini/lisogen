"""Número de familia del Paciente y re-extracción por mala calidad de la Muestra (DECISIONES D4).

- `paciente.familia_codigo` (FAM-000001…): agrupa Pacientes de la misma familia para que el Médico vea
  el historial familiar. Cada Paciente existente recibe un código propio.
- `MALA_CALIDAD` en `estado_muestra` y `motivo_reextraccion`: las Muestras de menos de 2 ml ya no vuelven
  solas; si llegan mal a Corea, el Administrativo pide la nueva extracción con este motivo.

Revision ID: 0006_familia_y_mala_calidad
Revises: 0005_lote_fedex_retiro
Create Date: 2026-11-24
"""

from alembic import op

revision = "0006_familia_y_mala_calidad"
down_revision = "0005_lote_fedex_retiro"
branch_labels = None
depends_on = None

_ESTADOS_MUESTRA = (
    "'LISTO_PARA_RETIRAR', 'EN_CAMINO_LAB_CENTRAL', 'EN_LAB_CENTRAL', "
    "'EN_LOTE', 'EN_VIAJE_COREA', 'PROCESADA', 'DESNATURALIZADA', 'VOLUMEN_INSUFICIENTE'"
)


def upgrade() -> None:
    op.execute("ALTER TYPE estado_muestra ADD VALUE IF NOT EXISTS 'MALA_CALIDAD'")
    op.execute("ALTER TYPE motivo_reextraccion ADD VALUE IF NOT EXISTS 'MALA_CALIDAD'")

    op.execute("CREATE SEQUENCE familia_seq")
    op.execute("ALTER TABLE paciente ADD COLUMN familia_codigo text")
    op.execute(
        "UPDATE paciente SET familia_codigo = 'FAM-' || lpad(nextval('familia_seq')::text, 6, '0') "
        "FROM (SELECT id FROM paciente ORDER BY id) AS orden WHERE paciente.id = orden.id"
    )
    op.execute("ALTER TABLE paciente ALTER COLUMN familia_codigo SET NOT NULL")
    op.execute(
        "ALTER TABLE paciente ALTER COLUMN familia_codigo "
        "SET DEFAULT 'FAM-' || lpad(nextval('familia_seq')::text, 6, '0')"
    )
    op.execute(
        "ALTER TABLE paciente ADD CONSTRAINT ck_paciente_familia_codigo "
        "CHECK (familia_codigo ~ '^FAM-[0-9]{6}$')"
    )
    op.execute("CREATE INDEX ix_paciente_familia ON paciente (familia_codigo)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_paciente_familia")
    op.execute("ALTER TABLE paciente DROP CONSTRAINT ck_paciente_familia_codigo")
    op.execute("ALTER TABLE paciente DROP COLUMN familia_codigo")  # quita también el DEFAULT
    op.execute("DROP SEQUENCE familia_seq")

    # Postgres no permite quitar un valor de un enum: se recrean los tipos (MALA_CALIDAD → DESNATURALIZADA)
    op.execute("UPDATE solicitud_reextraccion SET motivo = 'DESNATURALIZADA' WHERE motivo = 'MALA_CALIDAD'")
    op.execute("ALTER TYPE motivo_reextraccion RENAME TO motivo_reextraccion_viejo")
    op.execute("CREATE TYPE motivo_reextraccion AS ENUM ('DESNATURALIZADA', 'VOLUMEN_INSUFICIENTE')")
    op.execute(
        "ALTER TABLE solicitud_reextraccion ALTER COLUMN motivo TYPE motivo_reextraccion "
        "USING motivo::text::motivo_reextraccion"
    )
    op.execute("DROP TYPE motivo_reextraccion_viejo")

    op.execute("UPDATE muestra SET estado = 'DESNATURALIZADA' WHERE estado = 'MALA_CALIDAD'")
    op.execute("ALTER TABLE muestra ALTER COLUMN estado DROP DEFAULT")
    op.execute("ALTER TYPE estado_muestra RENAME TO estado_muestra_viejo")
    op.execute(f"CREATE TYPE estado_muestra AS ENUM ({_ESTADOS_MUESTRA})")
    op.execute(
        "ALTER TABLE muestra ALTER COLUMN estado TYPE estado_muestra USING estado::text::estado_muestra"
    )
    op.execute("ALTER TABLE muestra ALTER COLUMN estado SET DEFAULT 'LISTO_PARA_RETIRAR'")
    op.execute("DROP TYPE estado_muestra_viejo")
