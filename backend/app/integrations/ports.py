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


class ErrorCupones(Exception):
    """La API de Cupones rechazó el pedido o no respondió.

    `status`: código HTTP (0 si no hubo respuesta). `incierto`: no hubo respuesta (timeout, 5xx), así que
    la operación pudo haberse aplicado igual; hay que consultar `GET /cupones` antes de repetirla."""

    def __init__(self, mensaje: str, *, status: int = 0, incierto: bool = False) -> None:
        super().__init__(mensaje)
        self.status = status
        self.incierto = incierto


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
    """API de Cupones de Exoma Care: generar → asignar al médico → asignar al paciente → canjear."""

    async def generar(self, *, gerente_id: int, descuento_pct: int, cantidad: int) -> list[CuponExterno]: ...
    async def asignar_a_medico(self, *, gerente_id: int, medico_id: int, codigo: str) -> None: ...
    async def asignar_a_paciente(self, *, medico_id: int, paciente_id: int, codigo: str) -> None: ...
    async def canjear(self, *, paciente_id: int, codigo: str) -> None: ...


class FedexPort(Protocol):
    async def programar_retiro(self, *, fecha_hora: datetime, url_lote: str) -> str: ...


class MinisterioSaludPort(Protocol):
    async def autorizar_lote(self, *, codigo_lote: str, csv: bytes) -> bytes: ...


class OptimizacionRutasPort(Protocol):
    async def ordenar_paradas(
        self, *, origen: Punto, paradas: list[Parada], destino: Punto | None = None
    ) -> list[int]:
        """Orden de visita. `origen` y `destino` (por defecto, el mismo origen) quedan fijos."""
        ...


@dataclass(frozen=True)
class RespuestaChat:
    """`tipo`: respuesta | fuera_de_alcance | derivar_medico | sin_informacion. En los cuatro casos
    se muestra el texto tal cual."""

    respuesta: str
    conversacion_id: str | None
    tipo: str


class ErrorChatbot(Exception):
    """El Chatbot rechazó el pedido o no respondió.

    `status`: código HTTP (0 si no hubo respuesta). `detalle`: el `detail` que mandó el servicio (sirve
    para mostrar tal cual el aviso de 503). `reintentar_en`: segundos que pidió esperar (429)."""

    def __init__(
        self, mensaje: str, *, status: int = 0, detalle: str = "", reintentar_en: int | None = None
    ) -> None:
        super().__init__(mensaje)
        self.status = status
        self.detalle = detalle
        self.reintentar_en = reintentar_en


class ChatbotPort(Protocol):
    async def responder(self, *, pregunta: str, conversacion_id: str | None = None) -> RespuestaChat: ...


class MailPort(Protocol):
    async def enviar(
        self, *, destinatario: str, asunto: str, cuerpo: str, clave: str | None = None
    ) -> str | None:
        """`clave` identifica el aviso para reintentar sin duplicar (API de Notificaciones).
        Devuelve el id del aviso en la API, si el adaptador lo tiene."""
        ...


class StoragePort(Protocol):
    """MinIO privado. Nunca se exponen claves: sólo URLs firmadas de corta duración."""

    async def guardar(self, *, clave: str, contenido: bytes, mime: str) -> None: ...
    async def leer(self, *, clave: str) -> bytes: ...
    async def url_firmada(self, *, clave: str, nombre_descarga: str) -> str: ...
