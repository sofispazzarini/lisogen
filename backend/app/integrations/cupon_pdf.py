"""PDF del Cupón que arma LisoGen a partir del código que entrega la API de Cupones (la API no genera
PDF ni QR). El QR codifica `LISOGEN-CUPON:<código>` y el mismo texto queda escrito en el PDF: al
subirlo, el código se lee de ese texto (no se decodifica la imagen del QR)."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.integrations.pdf import generar_pdf

MARCA_CUPON = "LISOGEN-CUPON:"
_ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def pdf_de_cupon(*, codigo: str, descuento_pct: int, vence_at: datetime) -> bytes:
    contenido = f"{MARCA_CUPON}{codigo}"
    return generar_pdf(
        "Cupón de descuento LisoGen",
        [
            f"Descuento: {descuento_pct}% sobre lo que paga el Paciente.",
            f"Código: {codigo}",
            f"Vence: {vence_at.astimezone(_ZONA):%d/%m/%Y}",
            "",
            f"QR: {contenido}",
            "Presentalo al pagar el Presupuesto de tu Estudio. Uso único.",
        ],
        qr=contenido,
    )


def leer_codigo_de_pdf_cupon(contenido: bytes) -> str | None:
    """Código del Cupón escrito en un PDF hecho por `pdf_de_cupon` (None si no tiene la marca)."""
    m = re.search(re.escape(MARCA_CUPON).encode() + rb"([A-Za-z0-9-]{6,20})", contenido)
    return m.group(1).decode() if m else None
