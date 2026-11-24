"""Adaptadores mock determinísticos: misma entrada → misma salida, sin red."""

import hashlib
import html
import math
import re
import secrets
import unicodedata
import uuid
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import familiograma_mapeo
from app.integrations.pdf import generar_pdf
from app.integrations.ports import (
    ConceptoSnomed,
    CuponExterno,
    EstadoRetiroFedex,
    Familiograma,
    Parada,
    ParentescoCatalogo,
    PersonaFamiliograma,
    Punto,
    ReglaSospecha,
    RespuestaChat,
    RetiroFedex,
    SolicitudExterna,
    VarianteExterna,
)
from app.models import SnomedConcepto

GENES_POR_PATOLOGIA: Final = {
    "fabry": ["GLA"],
    "pompe": ["GAA"],
    "mps 1": ["IDUA"],
    "gaucher": ["GBA1"],
    "asmd": ["SMPD1"],
}
GENES_HALLAZGOS_SECUNDARIOS: Final = ["BRCA1", "BRCA2", "MLH1", "LDLR", "MYBPC3"]

# Una variante descripta en la literatura por gen + dos sintéticas determinísticas.
VARIANTES_CONOCIDAS: Final = {
    "GLA": "c.644A>G (p.Asn215Ser)",
    "GAA": "c.-32-13T>G",
    "IDUA": "c.1205G>A (p.Trp402Ter)",
    "GBA1": "c.1226A>G (p.Asn409Ser)",
    "SMPD1": "c.1829_1831del (p.Arg610del)",
    "BRCA1": "c.68_69del (p.Glu23ValfsTer17)",
    "BRCA2": "c.5946del (p.Ser1982ArgfsTer22)",
    "MLH1": "c.1852_1854del (p.Lys618del)",
    "LDLR": "c.1646G>A (p.Gly549Asp)",
    "MYBPC3": "c.1504C>T (p.Arg502Trp)",
}

# Mismos porcentajes que informa el catálogo real (IOMA 100, Medifé 70, OSPACP 50); OSPS/ANDINA/FEDERAL
# quedan como códigos de prueba para los tests.
COBERTURAS: Final = {
    "IOMA": Decimal(100),
    "MEDIFE": Decimal(70),
    "OSPACP": Decimal(50),
    "OSPS": Decimal(100),
    "ANDINA": Decimal(70),
    "FEDERAL": Decimal(50),
}


def _h(texto: str) -> int:
    return int(hashlib.sha256(texto.encode()).hexdigest(), 16)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().strip()


class BioinformaticaMock:
    async def genes_por_patologia(self, *, patologia: str) -> list[str]:
        return list(GENES_POR_PATOLOGIA.get(_normalizar(patologia), []))

    async def genes_hallazgos_secundarios(self) -> list[str]:
        return list(GENES_HALLAZGOS_SECUNDARIOS)

    async def variantes_por_gen(
        self, *, gen: str, texto: str = "", limite: int = 50, offset: int = 0
    ) -> list[VarianteExterna]:
        gen = gen.upper()
        variantes = []
        if gen in VARIANTES_CONOCIDAS:
            variantes.append(VarianteExterna(VARIANTES_CONOCIDAS[gen], f"VAR-{gen}-1"))
        base = _h(gen)
        bases = "ACGT"
        for i in (2, 3):
            pos = 100 + (base >> (i * 8)) % 1800
            ref, alt = bases[(base >> i) % 4], bases[(base >> (i + 2)) % 4]
            if ref == alt:
                alt = bases[(bases.index(ref) + 1) % 4]
            variantes.append(VarianteExterna(f"c.{pos}{ref}>{alt}", f"VAR-{gen}-{i}"))
        coincidencias = [v for v in variantes if texto.casefold() in v.nomenclatura.casefold()]
        return coincidencias[offset : offset + limite]

    async def variante_exacta(self, *, gen: str, nomenclatura: str) -> VarianteExterna | None:
        variantes = await self.variantes_por_gen(gen=gen)
        return next((v for v in variantes if v.nomenclatura == nomenclatura), None)


class ObrasSocialesMock:
    """No guarda estado ni aplica las reglas de la API (una solicitud sólo se resuelve una vez, una demanda
    por vez). Los tests que necesitan que la API rechace un pedido usan `ObrasSocialesFalla`
    (tests/falsos.py)."""

    async def cobertura(self, *, codigo_obra_social: str, cantidad_genes: int) -> Decimal:
        return COBERTURAS.get(codigo_obra_social.upper(), Decimal(0))

    async def solicitar(
        self, *, codigo_obra_social: str, paciente_nombre: str, fecha: date, referencia: str
    ) -> SolicitudExterna:
        token = f"{_h(codigo_obra_social + referencia) % 10**12:012d}"
        return SolicitudExterna(
            id=f"mock-sol-{token}",
            estado="pendiente",
            url_autorizar=f"mock://simulacion/{token}/autorizar",
            url_rechazar=f"mock://simulacion/{token}/rechazar",
        )

    async def autorizar(
        self, *, solicitud: SolicitudExterna, porcentaje: Decimal | None = None
    ) -> SolicitudExterna:
        return replace(solicitud, estado="autorizada")

    async def rechazar(self, *, solicitud: SolicitudExterna, motivo: str) -> SolicitudExterna:
        return replace(solicitud, estado="rechazada")

    async def presentar_demanda(
        self, *, solicitud: SolicitudExterna, nombre_archivo: str, contenido: bytes
    ) -> SolicitudExterna:
        return replace(solicitud, estado="demanda_en_curso")


class FamiliogramaMock:
    """Mismo contrato que la API (valida el payload y devuelve un SVG), sin red: una lista de las personas."""

    async def generar(
        self, *, personas: list[PersonaFamiliograma], regla_sospecha: ReglaSospecha = "desactivada"
    ) -> Familiograma:
        familiograma_mapeo.a_payload(personas, regla_sospecha)  # mismas validaciones que antes de la API
        alto = 40 + 24 * len(personas)
        lineas = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="{alto}" viewBox="0 0 520 {alto}">',
            '<text x="10" y="24" font-family="sans-serif" font-size="16">Familiograma (simulado)</text>',
        ]
        for i, p in enumerate(personas):
            etiqueta = familiograma_mapeo.CATALOGO[p.parentesco]
            diagnostico = f" · {', '.join(d.nombre for d in p.diagnosticos)}" if p.diagnosticos else ""
            texto = html.escape(f"{etiqueta}: {p.nombre} {p.apellido}{diagnostico}")
            lineas.append(
                f'<text x="10" y="{52 + 24 * i}" font-family="sans-serif" font-size="13">{texto}</text>'
            )
        lineas.append("</svg>")
        return Familiograma(contenido="\n".join(lineas).encode(), mime="image/svg+xml")

    async def parentescos(self) -> list[ParentescoCatalogo]:
        return [ParentescoCatalogo(i, e) for i, e in familiograma_mapeo.CATALOGO.items()]


class SnomedCacheLocal:
    """Búsqueda en la caché local `snomed_concepto` (no sale a la red)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar(self, *, texto: str, limite: int = 20) -> list[ConceptoSnomed]:
        texto = texto.strip()
        if not texto:
            return []
        filtros: list[ColumnElement[bool]] = [SnomedConcepto.termino.ilike(f"%{texto}%")]
        palabras = [p for p in re.findall(r"\w+", texto) if len(p) > 1]
        if palabras:
            consulta = " & ".join(f"{p}:*" for p in palabras)
            filtros.append(
                func.to_tsvector("spanish", SnomedConcepto.termino).op("@@")(
                    func.to_tsquery("spanish", consulta)
                )
            )
        if texto.isdigit():
            filtros.append(SnomedConcepto.concept_id == int(texto))
        filas = await self._session.scalars(
            select(SnomedConcepto).where(or_(*filtros)).order_by(SnomedConcepto.termino).limit(limite)
        )
        return [ConceptoSnomed(c.concept_id, c.termino) for c in filas]


class CuponesMock:
    """Cupones sin red: códigos hexadecimales de 8 caracteres, como los de la API real.

    No guarda estado: las reglas de la API (un Cupón por Paciente, vencimiento a 30 días) las simulan
    los tests con adaptadores propios cuando hace falta."""

    async def generar(self, *, gerente_id: int, descuento_pct: int, cantidad: int) -> list[CuponExterno]:
        return [CuponExterno(secrets.token_hex(4)) for _ in range(cantidad)]

    async def asignar_a_medico(self, *, gerente_id: int, medico_id: int, codigo: str) -> None:
        return None

    async def asignar_a_paciente(self, *, medico_id: int, paciente_id: int, codigo: str) -> None:
        return None

    async def canjear(self, *, paciente_id: int, codigo: str) -> None:
        return None


class FedexMock:
    async def programar_retiro(self, *, fecha_hora: datetime, lugar: str) -> RetiroFedex:
        id_retiro = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{fecha_hora.isoformat()}|{lugar}"))
        return RetiroFedex(id=id_retiro, url_seguimiento=f"https://fedex.invalid/retiros/{id_retiro}")

    async def consultar_retiro(self, *, retiro_id: str) -> EstadoRetiroFedex:
        return "PROGRAMADO"  # en modo mock la confirmación la hace la tarea `fedex` por hora


class MinisterioSaludMock:
    async def autorizar_lote(self, *, codigo_lote: str, csv: bytes) -> bytes:
        filas = max(0, csv.decode("utf-8").count("\n") - 1)
        numero = _h(codigo_lote) % 10**8
        return generar_pdf(
            "Ministerio de Salud - Autorización de envío",
            [
                f"Autorización N° MS-{numero:08d}",
                f"Lote: {codigo_lote}",
                f"Muestras declaradas: {filas}",
                "Se autoriza el envío de las Muestras biológicas al exterior para secuenciación.",
            ],
        )


def _distancia(a: Punto, b: Punto) -> float:
    return math.hypot(float(a.latitud - b.latitud), float(a.longitud - b.longitud))


class OptimizacionRutasMock:
    """Vecino más cercano desde el origen; empates por id. Determinístico."""

    async def ordenar_paradas(
        self, *, origen: Punto, paradas: list[Parada], destino: Punto | None = None
    ) -> list[int]:
        pendientes = sorted(paradas, key=lambda p: p.id)
        actual, orden = origen, []
        while pendientes:
            siguiente = min(pendientes, key=lambda p: (_distancia(actual, p.punto), p.id))
            orden.append(siguiente.id)
            pendientes.remove(siguiente)
            actual = siguiente.punto
        return orden


_RESPUESTAS: Final = {
    "fabry": "La enfermedad de Fabry es lisosomal y ligada al cromosoma X. Se debe a la falta de la "
    "enzima alfa-galactosidasa A (gen GLA). Puede dar dolor y ardor en manos y pies (acroparestesias), "
    "angioqueratomas en la piel, poca sudoración y, con los años, afectar riñón, corazón y cerebro. "
    "Existen terapia de reemplazo enzimático y, para algunas variantes, una chaperona oral.",
    "pompe": "La enfermedad de Pompe se debe a la falta de la enzima alfa-glucosidasa ácida (gen GAA) y se "
    "hereda de forma autosómica recesiva. En bebés suele dar hipotonía, agrandamiento del corazón y "
    "dificultad para alimentarse; en formas tardías, debilidad muscular y problemas respiratorios. "
    "Se trata con terapia de reemplazo enzimático; en menores de 4 meses el Estudio es Urgente.",
    "mps": "La MPS 1 (mucopolisacaridosis tipo 1) se debe a la falta de la enzima alfa-L-iduronidasa (gen "
    "IDUA). Puede dar rasgos faciales toscos, opacidad de córnea, alteraciones óseas, rigidez articular, "
    "hernias y agrandamiento de hígado y bazo. Hay terapia de reemplazo enzimático y, en la forma grave, "
    "trasplante de células madre hematopoyéticas.",
    "gaucher": "La enfermedad de Gaucher se debe a la falta de la enzima glucocerebrosidasa (gen GBA1). Lo "
    "más frecuente es el agrandamiento del bazo y del hígado, plaquetas bajas, anemia, cansancio y dolor "
    "óseo. Se trata con terapia de reemplazo enzimático o de reducción de sustrato.",
    "asmd": "La ASMD (deficiencia de esfingomielinasa ácida, antes llamada Niemann-Pick A/B) se debe a "
    "variantes en el gen SMPD1. Puede dar agrandamiento de hígado y bazo, enfermedad pulmonar intersticial, "
    "alteración de los lípidos en sangre y retraso del crecimiento. Existe terapia de reemplazo enzimático.",
    "exoma": "El exoma clínico secuencia las regiones de tu ADN que codifican proteínas. En LisoGen se "
    "analizan los genes que indicó tu Médico Tratante para las cinco Patologías lisosomales.",
    "turno": "Podés Sacar Turno cuando tu Estudio está Pagado o Autorizado. Los Turnos son de 15 minutos, de "
    "lunes a viernes de 9 a 18, en cualquiera de los Centros de Extracción del mapa.",
    "resultado": "Cuando el Resultado está listo te avisamos por mail y lo ves en Mis Estudios. Tu Médico "
    "Tratante también lo recibe para explicártelo.",
}
_ALIAS: Final = {"mps 1": "mps", "mucopolisacaridosis": "mps", "niemann": "asmd", "esfingomielinasa": "asmd"}


class ChatbotMock:
    """Responde sólo sobre las cinco Patologías y el proceso del Estudio. No deriva a una persona (E14)."""

    async def responder(self, *, pregunta: str, conversacion_id: str | None = None) -> RespuestaChat:
        p = _normalizar(pregunta)
        claves = [k for k in _RESPUESTAS if k in p] + [v for a, v in _ALIAS.items() if a in p]
        tipo = "respuesta"
        if claves:
            vistas = list(dict.fromkeys(claves))
            texto = " ".join(_RESPUESTAS[k] for k in vistas[:2])
        else:
            tipo = "fuera_de_alcance"
            texto = (
                "Puedo responder dudas sobre las cinco Patologías que estudia LisoGen: Fabry, Pompe, MPS 1, "
                "Gaucher y ASMD, y sobre cómo sigue tu Estudio. Probá preguntarme, por ejemplo, "
                '"¿qué es la enfermedad de Gaucher?".'
            )
        aviso = "Esta información es general y no reemplaza la consulta con tu Médico Tratante."
        return RespuestaChat(
            respuesta=f"{texto}\n\n{aviso}",
            conversacion_id=conversacion_id or f"mock-{uuid.uuid4()}",
            tipo=tipo,
        )
