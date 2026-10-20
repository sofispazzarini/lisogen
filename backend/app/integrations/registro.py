"""Contenedor de integraciones. Cada llamada a un servicio externo queda en `integracion_log`,
sin datos personales: se omiten destinatarios, textos libres y contenidos binarios."""

import time
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Final, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.domain.enums import ServicioExterno
from app.integrations import mock
from app.integrations.infra import MailMemoria, MailSmtp, StorageMemoria, StorageMinio
from app.integrations.ports import (
    BioinformaticaPort,
    ChatbotPort,
    CuponesPort,
    FamiliogramaPort,
    FedexPort,
    MailPort,
    MinisterioSaludPort,
    ObrasSocialesPort,
    OptimizacionRutasPort,
    SnomedPort,
    StoragePort,
)
from app.models import IntegracionLog

CAMPOS_SENSIBLES: Final = frozenset(
    {"destinatario", "asunto", "cuerpo", "familiares", "csv", "pregunta", "contenido", "qr_pdf", "nombre"}
)


def _resumir(valor: Any, profundidad: int = 0) -> Any:
    if isinstance(valor, bytes):
        return {"bytes": len(valor)}
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if is_dataclass(valor) and not isinstance(valor, type):
        return _resumir(asdict(valor), profundidad)
    if isinstance(valor, dict):
        return {
            k: ("[omitido]" if k in CAMPOS_SENSIBLES else _resumir(v, profundidad + 1))
            for k, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        if profundidad > 0 or len(valor) > 20:
            return {"cantidad": len(valor)}
        return [_resumir(v, profundidad + 1) for v in valor]
    if isinstance(valor, str) and len(valor) > 120:
        return {"texto_len": len(valor)}
    return valor


class _Registrado:
    """Proxy que mide y registra cada llamada async del adaptador."""

    def __init__(
        self, adaptador: Any, servicio: ServicioExterno, session: AsyncSession, estudio_id: int | None
    ) -> None:
        self._adaptador = adaptador
        self._servicio = servicio
        self._session = session
        self._estudio_id = estudio_id

    def __getattr__(self, nombre: str) -> Callable[..., Any]:
        metodo = getattr(self._adaptador, nombre)

        async def llamar(**kwargs: Any) -> Any:
            inicio = time.perf_counter()
            ok, respuesta, status = False, None, None
            try:
                respuesta = await metodo(**kwargs)
                ok, status = True, 200
                return respuesta
            except Exception as e:
                respuesta = {"error": type(e).__name__}
                status = 502
                raise
            finally:
                self._session.add(
                    IntegracionLog(
                        servicio=self._servicio,
                        operacion=nombre,
                        estudio_id=self._estudio_id,
                        request=_resumir(kwargs),
                        response={
                            "resultado": _resumir(
                                respuesta, 1 if self._servicio != ServicioExterno.CHATBOT else 9
                            )
                        }
                        if ok
                        else respuesta,
                        http_status=status,
                        ok=ok,
                        duracion_ms=int((time.perf_counter() - inicio) * 1000),
                    )
                )

        return llamar


class Adaptadores:
    """Instancias sin estado de sesión (se crean una vez por proceso)."""

    def __init__(self, settings: Settings) -> None:
        self.bioinformatica: BioinformaticaPort = mock.BioinformaticaMock()
        self.obras_sociales: ObrasSocialesPort = mock.ObrasSocialesMock()
        self.familiograma: FamiliogramaPort = mock.FamiliogramaMock()
        self.cupones: CuponesPort = mock.CuponesMock(sin_qr=settings.mock_cupones_sin_qr)
        self.fedex: FedexPort = mock.FedexMock()
        self.ministerio: MinisterioSaludPort = mock.MinisterioSaludMock()
        self.rutas: OptimizacionRutasPort = mock.OptimizacionRutasMock()
        self.chatbot: ChatbotPort = mock.ChatbotMock()
        self.mail: MailPort = MailSmtp(settings) if settings.mail_modo == "smtp" else MailMemoria()
        self.storage: StoragePort = (
            StorageMinio(settings) if settings.storage_modo == "minio" else StorageMemoria()
        )


@lru_cache
def get_adaptadores() -> Adaptadores:
    return Adaptadores(get_settings())


class Integraciones:
    """Integraciones ligadas a la sesión del caso de uso (para registrar las llamadas en la misma
    transacción) y, opcionalmente, al Estudio afectado."""

    def __init__(
        self, session: AsyncSession, adaptadores: Adaptadores, estudio_id: int | None = None
    ) -> None:
        self._session = session
        self._a = adaptadores
        self._estudio_id = estudio_id
        self.storage: StoragePort = adaptadores.storage

    def para_estudio(self, estudio_id: int) -> "Integraciones":
        return Integraciones(self._session, self._a, estudio_id)

    def _r(self, adaptador: Any, servicio: ServicioExterno) -> Any:
        return _Registrado(adaptador, servicio, self._session, self._estudio_id)

    @property
    def bioinformatica(self) -> BioinformaticaPort:
        return cast(BioinformaticaPort, self._r(self._a.bioinformatica, ServicioExterno.BIOINFORMATICA))

    @property
    def obras_sociales(self) -> ObrasSocialesPort:
        return cast(ObrasSocialesPort, self._r(self._a.obras_sociales, ServicioExterno.OBRAS_SOCIALES))

    @property
    def familiograma(self) -> FamiliogramaPort:
        return cast(FamiliogramaPort, self._r(self._a.familiograma, ServicioExterno.FAMILIOGRAMA))

    @property
    def snomed(self) -> SnomedPort:
        return cast(SnomedPort, self._r(mock.SnomedCacheLocal(self._session), ServicioExterno.SNOMED))

    @property
    def cupones(self) -> CuponesPort:
        return cast(CuponesPort, self._r(self._a.cupones, ServicioExterno.CUPONES))

    @property
    def fedex(self) -> FedexPort:
        return cast(FedexPort, self._r(self._a.fedex, ServicioExterno.FEDEX))

    @property
    def ministerio(self) -> MinisterioSaludPort:
        return cast(MinisterioSaludPort, self._r(self._a.ministerio, ServicioExterno.MINISTERIO_SALUD))

    @property
    def rutas(self) -> OptimizacionRutasPort:
        return cast(OptimizacionRutasPort, self._r(self._a.rutas, ServicioExterno.OPTIMIZACION_RUTAS))

    @property
    def chatbot(self) -> ChatbotPort:
        return cast(ChatbotPort, self._r(self._a.chatbot, ServicioExterno.CHATBOT))

    @property
    def mail(self) -> MailPort:
        return cast(MailPort, self._r(self._a.mail, ServicioExterno.MAIL))
