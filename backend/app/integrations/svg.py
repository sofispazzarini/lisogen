"""Saneado de SVG recibido de un servicio externo antes de guardarlo y servirlo.

El SVG queda en MinIO y el navegador lo abre desde una URL firmada; si trajera scripts, se ejecutarían
al abrirlo en una pestaña. Se rechaza todo DOCTYPE/ENTITY (evita expansión de entidades) y se quitan
scripts, contenido HTML embebido, manejadores `on*` y referencias que no sean anclas internas (`#id`)."""

import re
import xml.etree.ElementTree as ET
from typing import Final

SVG_NS: Final = "http://www.w3.org/2000/svg"
XLINK_NS: Final = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_PROHIBIDOS: Final = frozenset({"script", "foreignObject", "iframe", "embed", "object", "audio", "video"})
_PELIGROSO_CSS: Final = re.compile(r"@import|url\s*\(\s*['\"]?(?!#)|expression\s*\(|javascript:", re.I)
_PELIGROSO_VALOR: Final = re.compile(r"^\s*(javascript|data|vbscript):", re.I)


class SvgInvalido(ValueError):
    pass


def _local(nombre: str) -> str:
    return nombre.rsplit("}", 1)[-1]


def sanear(contenido: bytes) -> bytes:
    """Devuelve el SVG sin contenido activo. SvgInvalido si no es un SVG bien formado."""
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", contenido, re.I):
        raise SvgInvalido("el SVG declara DOCTYPE o entidades")
    try:
        raiz = ET.fromstring(contenido)  # noqa: S314 - sin DOCTYPE no hay entidades externas ni expansión
    except ET.ParseError as e:
        raise SvgInvalido("el SVG no es XML bien formado") from e
    if _local(raiz.tag) != "svg":
        raise SvgInvalido("la raíz no es <svg>")
    _limpiar(raiz)
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True)


def _limpiar(elemento: ET.Element) -> None:
    for hijo in list(elemento):
        nombre = _local(hijo.tag) if isinstance(hijo.tag, str) else ""
        if nombre in _PROHIBIDOS or (nombre == "style" and _PELIGROSO_CSS.search(hijo.text or "")):
            elemento.remove(hijo)
            continue
        _limpiar(hijo)
    for atributo, valor in list(elemento.attrib.items()):
        local = _local(atributo).lower()
        if (
            local.startswith("on")
            or (local == "href" and not valor.strip().startswith("#"))
            or (local == "style" and _PELIGROSO_CSS.search(valor))
            or _PELIGROSO_VALOR.search(valor)
        ):
            del elemento.attrib[atributo]
