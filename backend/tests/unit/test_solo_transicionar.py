"""Regla 1: ningún código fuera de services/transiciones.py asigna `<algo>.estado` con un EstadoEstudio.

Complementa el guard en tiempo de ejecución de models/estudio.py con una revisión estática del código."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
PERMITIDO = APP / "services" / "transiciones.py"


def _asigna_estado_estudio(nodo: ast.AST) -> bool:
    if not isinstance(nodo, ast.Assign | ast.AugAssign | ast.AnnAssign):
        return False
    objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
    planos: list[ast.expr] = []
    for t in objetivos:
        planos.extend(t.elts if isinstance(t, ast.Tuple) else [t])
    valores = nodo.value.elts if isinstance(nodo.value, ast.Tuple) else [nodo.value]
    for t, v in zip(planos, valores * len(planos) if len(valores) == 1 else valores, strict=False):
        if not (isinstance(t, ast.Attribute) and t.attr == "estado"):
            continue
        texto_valor = ast.unparse(v) if v is not None else ""
        receptor = ast.unparse(t.value)
        if "EstadoEstudio" in texto_valor or receptor == "estudio" or receptor.endswith(".estudio"):
            return True
    return False


def test_solo_transicionar_asigna_estudio_estado() -> None:
    infractores = []
    for archivo in APP.rglob("*.py"):
        if archivo == PERMITIDO:
            continue
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if _asigna_estado_estudio(nodo):
                infractores.append(f"{archivo.relative_to(APP)}:{nodo.lineno}")
    assert infractores == [], f"Asignaciones a estudio.estado fuera de transicionar: {infractores}"


def test_el_detector_encuentra_asignaciones() -> None:
    for codigo in (
        "estudio.estado = EstadoEstudio.PAGADO",
        "e.estado = EstadoEstudio.FINALIZADO",
        "estudio.estado, x = EstadoEstudio.PAGADO, 1",
        "self.estudio.estado = destino",
    ):
        assert any(_asigna_estado_estudio(n) for n in ast.walk(ast.parse(codigo))), codigo
    for codigo in ("muestra.estado = EstadoMuestra.EN_LOTE", "lote.estado = EstadoLote.RECIBIDO"):
        assert not any(_asigna_estado_estudio(n) for n in ast.walk(ast.parse(codigo))), codigo
