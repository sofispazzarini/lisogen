"""Generador mínimo de PDF (texto, Helvetica, WinAnsi). Evita dependencias pesadas para los documentos
del sistema: orden de extracción, consentimiento, Resultado, Familiograma y Cupones de los mocks."""

import textwrap
from collections.abc import Sequence

_LINEAS_POR_PAGINA = 48
_ANCHO = 92


def _escapar(texto: str) -> bytes:
    crudo = texto.encode("cp1252", errors="replace")
    return crudo.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def generar_pdf(titulo: str, lineas: Sequence[str]) -> bytes:
    envueltas: list[str] = []
    for linea in lineas:
        envueltas.extend(textwrap.wrap(linea, _ANCHO) or [""])
    paginas = [
        envueltas[i : i + _LINEAS_POR_PAGINA] for i in range(0, len(envueltas), _LINEAS_POR_PAGINA)
    ] or [[]]

    objetos: list[bytes] = []
    # 1 catálogo, 2 árbol de páginas, 3 fuente normal, 4 fuente negrita; luego (página, contenido) por página
    ids_paginas = [5 + 2 * i for i in range(len(paginas))]
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = b" ".join(f"{i} 0 R".encode() for i in ids_paginas)
    objetos.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(paginas)).encode() + b" >>")
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for n, pagina in enumerate(paginas):
        flujo = [b"BT /F2 16 Tf 56 790 Td (" + _escapar(titulo) + b") Tj ET"]
        flujo.append(b"BT /F1 10 Tf 56 760 Td 14 TL")
        for linea in pagina:
            flujo.append(b"(" + _escapar(linea) + b") Tj T*")
        flujo.append(b"ET")
        pie = f"LisoGen - pagina {n + 1} de {len(paginas)}"
        flujo.append(b"BT /F1 8 Tf 56 30 Td (" + _escapar(pie) + b") Tj ET")
        contenido = b"\n".join(flujo)
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {ids_paginas[n] + 1} 0 R "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>".encode()
        )
        objetos.append(
            b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream"
        )

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        salida += f"{off:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def es_pdf(contenido: bytes) -> bool:
    return contenido.startswith(b"%PDF-")
