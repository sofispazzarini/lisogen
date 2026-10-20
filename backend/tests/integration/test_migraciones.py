"""La migración inicial reproduce schema.sql 1:1 y la 0002 aplica sólo el cambio documentado (D1)."""

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command

from tests.conftest import BACKEND, alembic_config, borrar_base, crear_base, url_libpq

SCHEMA_SQL = BACKEND.parent / "schema.sql"
SQL_0001 = BACKEND / "alembic" / "versions" / "sql" / "0001_initial.sql"


def test_sql_de_la_migracion_es_copia_exacta_de_schema_sql() -> None:
    assert SQL_0001.read_bytes() == SCHEMA_SQL.read_bytes()


def _dump(nombre_db: str) -> str:
    salida = subprocess.run(
        ["pg_dump", "--schema-only", "--no-owner", "--no-privileges", url_libpq(nombre_db)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # Se ignoran comentarios, líneas vacías, \restrict (pg_dump ≥ 16.10) y la tabla de Alembic.
    salida = re.sub(r"--.*\n", "", salida)
    salida = re.sub(r"^\\(un)?restrict .*$", "", salida, flags=re.M)
    salida = re.sub(r"CREATE TABLE public\.alembic_version \(.*?\);\n", "", salida, flags=re.S)
    salida = re.sub(
        r"ALTER TABLE ONLY public\.alembic_version\s+ADD CONSTRAINT .*?;\n", "", salida, flags=re.S
    )
    return "\n".join(line for line in salida.splitlines() if line.strip())


@pytest.fixture(scope="module")
def bases() -> Iterator[tuple[str, str]]:
    sufijo = os.getpid()
    ref, mig = f"lisogen_ref_{sufijo}", f"lisogen_mig_{sufijo}"
    crear_base(ref)
    crear_base(mig)
    with psycopg.connect(url_libpq(ref), autocommit=True) as c:
        c.execute(SCHEMA_SQL.read_text(encoding="utf-8"))  # type: ignore[arg-type]
    yield ref, mig
    borrar_base(ref)
    borrar_base(mig)


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump no está instalado")
def test_migracion_0001_reproduce_schema_sql(bases: tuple[str, str]) -> None:
    ref, mig = bases
    command.upgrade(alembic_config(mig), "0001_initial")
    assert _dump(mig) == _dump(ref)


def _scalar(nombre_db: str, sql: str) -> object:
    with psycopg.connect(url_libpq(nombre_db)) as c:
        fila = c.execute(sql).fetchone()  # type: ignore[arg-type]
        return fila[0] if fila else None


def test_migracion_0002_pago_anulable_ida_y_vuelta(bases: tuple[str, str]) -> None:
    _, mig = bases
    cfg = alembic_config(mig)
    command.upgrade(cfg, "head")
    assert (
        _scalar(
            mig,
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='pago' AND column_name='anulado_at'",
        )
        == "timestamp with time zone"
    )
    indice = str(_scalar(mig, "SELECT indexdef FROM pg_indexes WHERE indexname='ux_pago_vigente'"))
    assert "WHERE (anulado_at IS NULL)" in indice
    assert _scalar(mig, "SELECT count(*) FROM pg_constraint WHERE conname='pago_presupuesto_id_key'") == 0

    command.downgrade(cfg, "0001_initial")
    assert _scalar(mig, "SELECT count(*) FROM pg_constraint WHERE conname='pago_presupuesto_id_key'") == 1
    command.downgrade(cfg, "base")
    assert _scalar(mig, "SELECT count(*) FROM pg_tables WHERE schemaname='public'") == 1  # alembic_version
    command.upgrade(cfg, "head")
    assert _scalar(mig, "SELECT version_num FROM alembic_version") == "0002_pago_anulable"


def test_schema_tiene_todas_las_tablas_del_contrato(bases: tuple[str, str]) -> None:
    ref, _ = bases
    esperadas = set(re.findall(r"CREATE TABLE (\w+)", SCHEMA_SQL.read_text(encoding="utf-8")))
    with psycopg.connect(url_libpq(ref)) as c:
        reales = {r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    assert reales == esperadas
    assert len(esperadas) == 46


def test_modelos_orm_cubren_todas_las_tablas() -> None:
    from app.models import Base

    esperadas = set(re.findall(r"CREATE TABLE (\w+)", Path(SCHEMA_SQL).read_text(encoding="utf-8")))
    assert set(Base.metadata.tables) == esperadas
