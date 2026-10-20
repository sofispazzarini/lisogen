"""Puertos de las integraciones externas. Cada uno tiene un adaptador mock determinístico (mock.py)
y toda llamada queda registrada en `integracion_log` (registro.py)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class VarianteExterna:
    nomenclatura: str
    id_externo: str


@dataclass(frozen=True)
class FamiliarExterno:
    parentesco: str
    nombre: str
    sintomas: str | None
    diagnostico: str | None


@dataclass(frozen=True)
class ConceptoSnomed:
    concept_id: int
    termino: str


@dataclass(frozen=True)
class CuponExterno:
    codigo: str
    qr_pdf: bytes | None  # None: el módulo no generó QR y entregó sólo el código numérico (E32)


@dataclass(frozen=True)
class Punto:
    latitud: Decimal
    longitud: Decimal


@dataclass(frozen=True)
class Parada:
    id: int
    punto: Punto


class BioinformaticaPort(Protocol):
    async def genes_por_patologia(self, *, patologia: str) -> list[str]: ...
    async def genes_hallazgos_secundarios(self) -> list[str]: ...
    async def variantes_por_gen(self, *, gen: str) -> list[VarianteExterna]: ...


class ObrasSocialesPort(Protocol):
    async def cobertura(self, *, codigo_obra_social: str, cantidad_genes: int) -> Decimal: ...


class FamiliogramaPort(Protocol):
    async def generar(self, *, familiares: list[FamiliarExterno]) -> bytes: ...


class SnomedPort(Protocol):
    async def buscar(self, *, texto: str, limite: int = 20) -> list[ConceptoSnomed]: ...


class CuponesPort(Protocol):
    async def generar(self, *, descuento_pct: int, cantidad: int) -> list[CuponExterno]: ...
    async def validar(self, *, codigo: str) -> bool: ...
    async def marcar_usado(self, *, codigo: str) -> None: ...


class FedexPort(Protocol):
    async def programar_retiro(self, *, fecha_hora: datetime, url_lote: str) -> str: ...


class MinisterioSaludPort(Protocol):
    async def autorizar_lote(self, *, codigo_lote: str, csv: bytes) -> bytes: ...


class OptimizacionRutasPort(Protocol):
    async def ordenar_paradas(self, *, origen: Punto, paradas: list[Parada]) -> list[int]: ...


class ChatbotPort(Protocol):
    async def responder(self, *, pregunta: str) -> str: ...


class MailPort(Protocol):
    async def enviar(self, *, destinatario: str, asunto: str, cuerpo: str) -> None: ...


class StoragePort(Protocol):
    """MinIO privado. Nunca se exponen claves: sólo URLs firmadas de corta duración."""

    async def guardar(self, *, clave: str, contenido: bytes, mime: str) -> None: ...
    async def leer(self, *, clave: str) -> bytes: ...
    async def url_firmada(self, *, clave: str, nombre_descarga: str) -> str: ...
