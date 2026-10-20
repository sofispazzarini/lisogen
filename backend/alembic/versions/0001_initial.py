"""Esquema inicial: reproduce schema.sql 1:1 (enums, índices parciales y CHECKs).

El SQL vive en sql/0001_initial.sql, copia exacta de lisogen/schema.sql
(tests/integration/test_migraciones.py verifica que sean idénticos y que el esquema resultante coincida).

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-19
"""

from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

SQL = Path(__file__).with_name("sql") / "0001_initial.sql"


def upgrade() -> None:
    # Cursor DBAPI sin parámetros: psycopg no interpreta el '%' del CHECK de turno como placeholder.
    with op.get_bind().connection.cursor() as cur:
        cur.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Borra lo que crea schema.sql (tablas, tipos y extensión) sin tocar alembic_version.
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN SELECT tablename FROM pg_tables
                   WHERE schemaname = 'public' AND tablename <> 'alembic_version' LOOP
            EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
          END LOOP;
          FOR r IN SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'public' AND t.typtype = 'e' LOOP
            EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', r.typname);
          END LOOP;
        END $$;
        """
    )
    op.execute("DROP EXTENSION IF EXISTS citext")
