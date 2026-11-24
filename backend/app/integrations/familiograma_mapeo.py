"""Único punto de conversión del modelo interno (Paciente + Familiar) al payload de la API de familiograma.

Reglas (ver DECISIONES D2 y S40):
- El Paciente es la persona con parentesco 0. Su sexo no está en el modelo: va `no_identificado`. Sus
  diagnósticos son *presuntivos* y la API sólo dibuja diagnósticos confirmados, así que no se envían.
- Parentesco interno + lado → código del catálogo (`CODIGOS`). Abuelos, tíos y primos necesitan el lado;
  `OTRO` no tiene código. Lo que no se puede mapear no se fuerza: se excluye y queda como advertencia.
- Sexo: sale del parentesco con género (PADRE → hombre, TIA → mujer, ...). `OTRO` → no_identificado.
- Diagnóstico previo del familiar: sólo las cinco Patologías con código en el catálogo provisorio
  (`DIAGNOSTICOS_SIM`). Los síntomas no se envían hasta tener la fuente de `SIM-0001`…`SIM-0022`.
- Edad y fallecido de los familiares no están en el modelo: quedan en los valores por defecto.

Ni este módulo ni sus errores escriben nombres, edades ni diagnósticos en logs: los mensajes de las
advertencias identifican a la persona por su posición y parentesco."""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

from app.domain.enums import LadoFamiliar, Parentesco
from app.integrations.ports import (
    Advertencia,
    CodigoNombre,
    PersonaFamiliograma,
    ReglaSospecha,
    SexoFamiliograma,
)

PACIENTE: Final = 0
MAX_BYTES: Final = 1024 * 1024  # la API responde 413 por encima de 1 MiB

# Catálogo fijo de la API (GET /parentescos): código → etiqueta
CATALOGO: Final[dict[int, str]] = {
    0: "paciente",
    1: "progenitor",
    2: "hermano/a",
    3: "abuelo/a materno/a",
    4: "abuelo/a paterno/a",
    5: "tío/a materno/a",
    6: "tío/a paterno/a",
    7: "primo/a materno/a",
    8: "primo/a paterno/a",
    9: "hijo/a",
    10: "medio hermano/a materno/a",
    11: "medio hermano/a paterno/a",
    12: "pareja del paciente",
    13: "suegro/a",
    14: "sobrino/a",
    15: "nieto/a",
}

_SIN_LADO: Final[dict[Parentesco, int]] = {
    Parentesco.PADRE: 1,
    Parentesco.MADRE: 1,
    Parentesco.HERMANO: 2,
    Parentesco.HERMANA: 2,
    Parentesco.HIJO: 9,
    Parentesco.HIJA: 9,
}
_CON_LADO: Final[dict[Parentesco, tuple[int, int]]] = {  # (materno, paterno)
    Parentesco.ABUELO: (3, 4),
    Parentesco.ABUELA: (3, 4),
    Parentesco.TIO: (5, 6),
    Parentesco.TIA: (5, 6),
    Parentesco.PRIMO: (7, 8),
    Parentesco.PRIMA: (7, 8),
}
REQUIEREN_LADO: Final = frozenset(_CON_LADO)

_HOMBRES: Final = frozenset(
    {
        Parentesco.PADRE,
        Parentesco.HERMANO,
        Parentesco.HIJO,
        Parentesco.ABUELO,
        Parentesco.TIO,
        Parentesco.PRIMO,
    }
)
_MUJERES: Final = frozenset(
    {
        Parentesco.MADRE,
        Parentesco.HERMANA,
        Parentesco.HIJA,
        Parentesco.ABUELA,
        Parentesco.TIA,
        Parentesco.PRIMA,
    }
)

# Nombre de la Patología en LisoGen → código del catálogo provisorio de la API (publicado en su Swagger)
DIAGNOSTICOS_SIM: Final[dict[str, str]] = {
    "Fabry": "SIM-FABRY",
    "Pompe": "SIM-POMPE",
    "MPS 1": "SIM-MPS1",
    "Gaucher": "SIM-GAUCHER",
    "ASMD": "SIM-ASMD",
}

_SEXOS: Final = frozenset({"hombre", "mujer", "no_identificado"})
_REGLAS: Final = frozenset({"desactivada", "un_cardinal_o_dos_secundarios"})


class ErrorMapeo(ValueError):
    """El árbol no cumple el contrato de la API (se detecta antes de llamarla)."""


@dataclass(frozen=True)
class PacienteInterno:
    nombre: str
    apellido: str
    fecha_nacimiento: date


@dataclass(frozen=True)
class FamiliarInterno:
    parentesco: Parentesco
    nombre: str
    apellido: str | None
    lado: LadoFamiliar | None
    patologia_diagnosticada: str | None  # nombre de la Patología


@dataclass
class ResultadoMapeo:
    """`personas[i]` se describe (sin datos personales) en `etiquetas[i]`, para traducir los errores 422
    de la API (`personas.<i>.campo`). `advertencias`: familiares o datos que no se pudieron enviar."""

    personas: list[PersonaFamiliograma] = field(default_factory=list)
    etiquetas: list[str] = field(default_factory=list)
    advertencias: list[Advertencia] = field(default_factory=list)


def codigo_parentesco(parentesco: Parentesco, lado: LadoFamiliar | None) -> int | None:
    """Código del catálogo, o None si la relación interna no existe en el catálogo (o le falta el lado)."""
    if parentesco in _SIN_LADO:
        return _SIN_LADO[parentesco]
    if parentesco in _CON_LADO and lado is not None:
        materno, paterno = _CON_LADO[parentesco]
        return materno if lado == LadoFamiliar.MATERNO else paterno
    return None


def sexo_de(parentesco: Parentesco) -> SexoFamiliograma:
    if parentesco in _HOMBRES:
        return "hombre"
    if parentesco in _MUJERES:
        return "mujer"
    return "no_identificado"


def edad_en_anios(fecha_nacimiento: date, hoy: date) -> float:
    """Años cumplidos; con fracción (dos decimales) para menores de 2 años, como pide la API."""
    anios = (
        hoy.year
        - fecha_nacimiento.year
        - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )
    if anios >= 2:
        return float(anios)
    return max(0.0, round((hoy - fecha_nacimiento).days / 365.25, 2))


def _etiqueta(numero: int, parentesco: Parentesco, lado: LadoFamiliar | None) -> str:
    texto = parentesco.value.lower()
    if lado is not None:
        texto += f" {lado.value.lower()}"
    return f"familiar n.º {numero} ({texto})"


def armar_personas(
    paciente: PacienteInterno, familiares: list[FamiliarInterno], *, hoy: date
) -> ResultadoMapeo:
    """Árbol completo para la API: el Paciente y todos los familiares que se puedan mapear."""
    r = ResultadoMapeo()
    r.personas.append(
        PersonaFamiliograma(
            parentesco=PACIENTE,
            nombre=paciente.nombre.strip(),
            apellido=paciente.apellido.strip(),
            edad=edad_en_anios(paciente.fecha_nacimiento, hoy),
        )
    )
    r.etiquetas.append("Paciente")
    for numero, f in enumerate(familiares, start=1):
        etiqueta = _etiqueta(numero, f.parentesco, f.lado)
        codigo = codigo_parentesco(f.parentesco, f.lado)
        if codigo is None:
            if f.parentesco in REQUIEREN_LADO:
                r.advertencias.append(
                    Advertencia(
                        "FAMILIAR_SIN_LADO",
                        f"El {etiqueta} no tiene lado materno o paterno y no se dibujó. Cargalo de nuevo "
                        "indicando el lado.",
                    )
                )
            else:
                r.advertencias.append(
                    Advertencia(
                        "PARENTESCO_SIN_CODIGO",
                        f"El {etiqueta} no tiene un parentesco equivalente en el familiograma "
                        "y no se dibujó.",
                    )
                )
            continue
        if not f.nombre.strip() or not (f.apellido or "").strip():
            r.advertencias.append(
                Advertencia(
                    "FAMILIAR_INCOMPLETO",
                    f"El {etiqueta} no tiene nombre y apellido y no se dibujó. "
                    "Cargalo de nuevo con apellido.",
                )
            )
            continue
        diagnosticos: tuple[CodigoNombre, ...] = ()
        if f.patologia_diagnosticada:
            sim = DIAGNOSTICOS_SIM.get(f.patologia_diagnosticada)
            if sim:
                diagnosticos = (CodigoNombre(sim, f.patologia_diagnosticada),)
            else:
                r.advertencias.append(
                    Advertencia(
                        "DIAGNOSTICO_SIN_CODIGO",
                        f"El diagnóstico previo del {etiqueta} no tiene código en el catálogo del "
                        "familiograma y no se dibujó.",
                    )
                )
        r.personas.append(
            PersonaFamiliograma(
                parentesco=codigo,
                nombre=f.nombre.strip(),
                apellido=(f.apellido or "").strip(),
                sexo=sexo_de(f.parentesco),
                diagnosticos=diagnosticos,
            )
        )
        r.etiquetas.append(etiqueta[0].upper() + etiqueta[1:])
    return r


def validar(personas: list[PersonaFamiliograma]) -> None:
    """Contrato mínimo de la API, antes de llamarla (evita un 422 evitable)."""
    pacientes = sum(1 for p in personas if p.parentesco == PACIENTE)
    if pacientes != 1:
        raise ErrorMapeo(f"El familiograma necesita exactamente un paciente (hay {pacientes}).")
    for i, p in enumerate(personas):
        if p.parentesco not in CATALOGO:
            raise ErrorMapeo(f"personas.{i}.parentesco: código fuera del catálogo")
        if not p.nombre.strip():
            raise ErrorMapeo(f"personas.{i}.nombre: obligatorio")
        if not p.apellido.strip():
            raise ErrorMapeo(f"personas.{i}.apellido: obligatorio")
        if p.sexo not in _SEXOS:
            raise ErrorMapeo(f"personas.{i}.sexo: valor no admitido")
        if p.edad is not None and p.edad < 0:
            raise ErrorMapeo(f"personas.{i}.edad: no puede ser negativa")


def _items(items: tuple[CodigoNombre, ...]) -> list[dict[str, str]]:
    return [{"codigo": c.codigo, "nombre": c.nombre} for c in items]


def a_payload(
    personas: list[PersonaFamiliograma], regla_sospecha: ReglaSospecha = "desactivada"
) -> dict[str, Any]:
    """Cuerpo del POST. Valida antes; `edad` desconocida se omite."""
    validar(personas)
    if regla_sospecha not in _REGLAS:
        raise ErrorMapeo("opciones.reglaSospecha: valor no admitido")
    salida: list[dict[str, Any]] = []
    for p in personas:
        d: dict[str, Any] = {
            "parentesco": p.parentesco,
            "nombre": p.nombre,
            "apellido": p.apellido,
            "sexo": p.sexo,
            "fallecido": p.fallecido,
            "sintomas": _items(p.sintomas),
            "diagnosticos": _items(p.diagnosticos),
        }
        if p.edad is not None:
            d["edad"] = p.edad
        salida.append(d)
    return {"personas": salida, "opciones": {"reglaSospecha": regla_sospecha}}


def serializar(payload: dict[str, Any]) -> bytes:
    """JSON en UTF-8; ErrorMapeo si supera el límite de la API."""
    cuerpo = json.dumps(payload, ensure_ascii=False).encode()
    if len(cuerpo) > MAX_BYTES:
        raise ErrorMapeo("El árbol familiar supera el tamaño que admite el servicio (1 MiB).")
    return cuerpo
