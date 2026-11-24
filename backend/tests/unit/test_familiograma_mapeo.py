"""Mapeo del modelo interno al payload de la API de familiograma y validaciones previas a la llamada."""

from datetime import date

import pytest

from app.domain.enums import LadoFamiliar, Parentesco
from app.integrations import familiograma_mapeo as m
from app.integrations.ports import CodigoNombre, PersonaFamiliograma

HOY = date(2026, 11, 24)
PACIENTE = m.PacienteInterno("Lucía", "Rivas", date(1992, 7, 1))


def _f(
    parentesco: Parentesco,
    nombre: str = "Ana",
    apellido: str | None = "Rivas",
    lado: LadoFamiliar | None = None,
    patologia: str | None = None,
) -> m.FamiliarInterno:
    return m.FamiliarInterno(parentesco, nombre, apellido, lado, patologia)


@pytest.mark.parametrize(
    ("parentesco", "lado", "codigo"),
    [
        (Parentesco.PADRE, None, 1),
        (Parentesco.MADRE, None, 1),
        (Parentesco.HERMANO, None, 2),
        (Parentesco.HERMANA, None, 2),
        (Parentesco.HIJO, None, 9),
        (Parentesco.HIJA, None, 9),
        (Parentesco.ABUELO, LadoFamiliar.MATERNO, 3),
        (Parentesco.ABUELA, LadoFamiliar.PATERNO, 4),
        (Parentesco.TIO, LadoFamiliar.MATERNO, 5),
        (Parentesco.TIA, LadoFamiliar.PATERNO, 6),
        (Parentesco.PRIMO, LadoFamiliar.MATERNO, 7),
        (Parentesco.PRIMA, LadoFamiliar.PATERNO, 8),
        (Parentesco.ABUELO, None, None),  # falta el lado: no se adivina
        (Parentesco.OTRO, None, None),  # no existe en el catálogo
    ],
)
def test_codigo_parentesco(parentesco: Parentesco, lado: LadoFamiliar | None, codigo: int | None) -> None:
    assert m.codigo_parentesco(parentesco, lado) == codigo


def test_todos_los_codigos_usados_estan_en_el_catalogo() -> None:
    usados = {m.codigo_parentesco(p, lado) for p in Parentesco for lado in (*LadoFamiliar, None)}
    assert usados - {None} <= set(m.CATALOGO)
    assert len(m.CATALOGO) == 16


@pytest.mark.parametrize(
    ("parentesco", "sexo"),
    [(Parentesco.PADRE, "hombre"), (Parentesco.TIA, "mujer"), (Parentesco.OTRO, "no_identificado")],
)
def test_sexo_sale_del_parentesco(parentesco: Parentesco, sexo: str) -> None:
    assert m.sexo_de(parentesco) == sexo


@pytest.mark.parametrize(
    ("nacimiento", "edad"),
    [
        (date(1992, 7, 1), 34.0),
        (date(1992, 11, 25), 33.0),
        (date(2026, 5, 24), 0.5),
        (date(2026, 11, 24), 0.0),
    ],
)
def test_edad_en_anios_con_fraccion_para_lactantes(nacimiento: date, edad: float) -> None:
    assert m.edad_en_anios(nacimiento, HOY) == edad


def test_arma_el_paciente_y_los_familiares_con_defaults() -> None:
    r = m.armar_personas(
        PACIENTE,
        [
            _f(Parentesco.MADRE, "Marta", patologia="Fabry"),
            _f(Parentesco.TIO, "Juan", "Gómez", LadoFamiliar.MATERNO),
        ],
        hoy=HOY,
    )
    assert r.advertencias == []
    paciente, madre, tio = r.personas
    assert paciente == PersonaFamiliograma(0, "Lucía", "Rivas", "no_identificado", 34.0)
    assert madre == PersonaFamiliograma(
        1, "Marta", "Rivas", "mujer", diagnosticos=(CodigoNombre("SIM-FABRY", "Fabry"),)
    )
    assert (tio.parentesco, tio.sexo, tio.edad, tio.fallecido, tio.sintomas) == (5, "hombre", None, False, ())
    assert r.etiquetas == ["Paciente", "Familiar n.º 1 (madre)", "Familiar n.º 2 (tio materno)"]


def test_lo_que_no_se_puede_mapear_se_informa_y_no_se_fuerza() -> None:
    r = m.armar_personas(
        PACIENTE,
        [
            _f(Parentesco.OTRO),
            _f(Parentesco.ABUELA),  # sin lado (fila anterior a la migración)
            _f(Parentesco.HERMANO, apellido=None),  # sin apellido (fila anterior a la migración)
            _f(Parentesco.PADRE, patologia="Patología sin código"),
        ],
        hoy=HOY,
    )
    assert [a.codigo for a in r.advertencias] == [
        "PARENTESCO_SIN_CODIGO",
        "FAMILIAR_SIN_LADO",
        "FAMILIAR_INCOMPLETO",
        "DIAGNOSTICO_SIN_CODIGO",
    ]
    assert [p.parentesco for p in r.personas] == [0, 1]
    assert r.personas[1].diagnosticos == ()
    # Las advertencias no llevan nombres ni el diagnóstico
    assert all("Ana" not in a.mensaje and "Patología sin" not in a.mensaje for a in r.advertencias)


def test_payload_con_opciones_y_sin_edad_desconocida() -> None:
    r = m.armar_personas(PACIENTE, [_f(Parentesco.MADRE)], hoy=HOY)
    payload = m.a_payload(r.personas)
    assert payload["opciones"] == {"reglaSospecha": "desactivada"}
    assert payload["personas"][0] == {
        "parentesco": 0,
        "nombre": "Lucía",
        "apellido": "Rivas",
        "sexo": "no_identificado",
        "fallecido": False,
        "sintomas": [],
        "diagnosticos": [],
        "edad": 34.0,
    }
    assert "edad" not in payload["personas"][1]


@pytest.mark.parametrize(
    ("personas", "mensaje"),
    [
        ([PersonaFamiliograma(1, "Ana", "Rivas")], "exactamente un paciente"),
        ([PersonaFamiliograma(0, "A", "B"), PersonaFamiliograma(0, "C", "D")], "exactamente un paciente"),
        ([PersonaFamiliograma(0, " ", "Rivas")], "personas.0.nombre"),
        ([PersonaFamiliograma(0, "Ana", "")], "personas.0.apellido"),
        (
            [PersonaFamiliograma(0, "Ana", "Rivas"), PersonaFamiliograma(16, "B", "C")],
            "personas.1.parentesco",
        ),
        ([PersonaFamiliograma(0, "Ana", "Rivas", edad=-1)], "personas.0.edad"),
    ],
)
def test_validacion_previa(personas: list[PersonaFamiliograma], mensaje: str) -> None:
    with pytest.raises(m.ErrorMapeo, match=mensaje):
        m.a_payload(personas)


def test_regla_sospecha_invalida() -> None:
    with pytest.raises(m.ErrorMapeo, match="reglaSospecha"):
        m.a_payload([PersonaFamiliograma(0, "Ana", "Rivas")], "otra")  # type: ignore[arg-type]


def test_payload_de_mas_de_1_mib_no_se_envia() -> None:
    enorme = [PersonaFamiliograma(0, "Ana", "Rivas"), PersonaFamiliograma(2, "x" * (1024 * 1024), "Rivas")]
    with pytest.raises(m.ErrorMapeo, match="1 MiB"):
        m.serializar(m.a_payload(enorme))
