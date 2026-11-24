"""E27 Tomar Estudio para análisis y E28 Cargar Variantes (Resultado)."""

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EstadoEstudio, OrigenGen, RolUsuario, TipoArchivo, TipoResultado
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado, SinPermiso
from app.domain.reglas import tipo_resultado
from app.integrations.pdf import generar_pdf
from app.integrations.ports import VarianteExterna
from app.integrations.registro import Integraciones
from app.models import (
    DatosCrudos,
    Estudio,
    EstudioGen,
    Gen,
    Paciente,
    Resultado,
    ResultadoVariante,
    Usuario,
    Variante,
)
from app.schemas.comun import EstudioResumen
from app.schemas.roles import EstudioAnalisis, ResultadoEntrada, VarianteCatalogo
from app.services import consultas
from app.services.comun import ahora, guardar_archivo, url_archivo
from app.services.estudios import obtener_estudio
from app.services.transiciones import transicionar


async def pendientes(session: AsyncSession) -> list[EstudioResumen]:
    """E27 ep. 2: los Estudios Urgentes (Pompe < 4 meses) primero, después por antigüedad."""
    return await consultas.resumenes(
        session,
        Estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        orden=[Estudio.urgente.desc(), Estudio.created_at, Estudio.id],
    )


async def mis_estudios(session: AsyncSession, bio: Usuario) -> list[EstudioResumen]:
    return await consultas.resumenes(
        session,
        Estudio.estado == EstadoEstudio.EN_ANALISIS,
        Estudio.bioinformatico_id == bio.id,
        orden=[Estudio.urgente.desc(), Estudio.tomado_at],
    )


async def tomar(session: AsyncSession, bio: Usuario, estudio_id: int, version: int) -> Estudio:
    """E27: lock optimista con `estudio.version`. Si otro Bioinformático lo tomó antes → 409."""
    estudio = await obtener_estudio(session, estudio_id)
    ya_tomado = Conflicto("ESTUDIO_YA_TOMADO", "Otro Bioinformático ya tomó este Estudio.")
    if estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICA or estudio.version != version:
        raise ya_tomado
    estudio.bioinformatico_id, estudio.tomado_at = bio.id, ahora()
    try:
        await transicionar(session, estudio, EstadoEstudio.EN_ANALISIS, bio, "Tomado para análisis")
    except Conflicto as e:
        if e.code == "ESTUDIO_MODIFICADO":
            raise ya_tomado from e
        raise
    return estudio


async def _mio_en_analisis(session: AsyncSession, bio: Usuario, estudio_id: int) -> Estudio:
    estudio = await obtener_estudio(session, estudio_id)
    if estudio.estado not in (EstadoEstudio.EN_ANALISIS_BIOINFORMATICA, EstadoEstudio.EN_ANALISIS):
        raise NoEncontrado("Estudio")
    if estudio.estado == EstadoEstudio.EN_ANALISIS and estudio.bioinformatico_id != bio.id:
        raise SinPermiso("Ese Estudio lo está analizando otro Bioinformático.")
    return estudio


async def para_analisis(
    session: AsyncSession, ints: Integraciones, bio: Usuario, estudio_id: int
) -> EstudioAnalisis:
    estudio = await _mio_en_analisis(session, bio, estudio_id)
    exoma_id = (
        estudio.estudio_origen_id or estudio.id
    )  # el Reanálisis usa los datos crudos del exoma original
    crudos = await session.scalar(select(DatosCrudos).where(DatosCrudos.estudio_id == exoma_id))
    origen = await session.get(Estudio, estudio.estudio_origen_id) if estudio.estudio_origen_id else None
    base = await consultas.resumen(session, estudio.id)
    return EstudioAnalisis(
        **base.model_dump(),
        genes=await consultas.genes_del_estudio(session, estudio.id),
        estudio_origen_codigo=origen.codigo if origen else None,
        datos_crudos_url=await url_archivo(session, ints, crudos.archivo_id) if crudos else None,
        tomado_por_mi=estudio.bioinformatico_id == bio.id,
    )


async def _gen_del_estudio(session: AsyncSession, estudio: Estudio, simbolo: str) -> tuple[Gen, EstudioGen]:
    fila = (
        await session.execute(
            select(Gen, EstudioGen)
            .join(EstudioGen, EstudioGen.gen_id == Gen.id)
            .where(EstudioGen.estudio_id == estudio.id, Gen.simbolo == simbolo.upper())
        )
    ).first()
    if fila is None:
        raise ErrorNegocio("GEN_NO_SOLICITADO", f"El gen {simbolo.upper()} no está en el Estudio.")
    return fila[0], fila[1]


async def variantes_de_gen(
    session: AsyncSession,
    ints: Integraciones,
    bio: Usuario,
    estudio_id: int,
    simbolo: str,
    *,
    texto: str = "",
    limite: int = 50,
    offset: int = 0,
) -> list[VarianteCatalogo]:
    estudio = await _mio_en_analisis(session, bio, estudio_id)
    gen, _ = await _gen_del_estudio(session, estudio, simbolo)
    externas = await ints.para_estudio(estudio.id).bioinformatica.variantes_por_gen(
        gen=gen.simbolo, texto=texto, limite=limite, offset=offset
    )
    return [VarianteCatalogo(nomenclatura=v.nomenclatura, id_externo=v.id_externo) for v in externas]


async def _guardar_variantes(
    session: AsyncSession, seleccionadas: dict[tuple[int, str], VarianteExterna]
) -> dict[tuple[int, str], Variante]:
    if not seleccionadas:
        return {}
    await session.execute(
        insert(Variante)
        .values(
            [
                {
                    "gen_id": gen_id,
                    "nomenclatura": nombre,
                    "id_externo": seleccionadas[gen_id, nombre].id_externo,
                }
                for gen_id, nombre in sorted(seleccionadas)
            ]
        )
        .on_conflict_do_nothing(index_elements=[Variante.gen_id, Variante.nomenclatura])
    )
    variantes = await session.scalars(
        select(Variante).where(tuple_(Variante.gen_id, Variante.nomenclatura).in_(seleccionadas))
    )
    return {(v.gen_id, v.nomenclatura): v for v in variantes}


_CONCLUSION = {
    TipoResultado.POSITIVO: "Se identificaron variantes patogénicas compatibles con la sospecha clínica.",
    TipoResultado.NEGATIVO: "No se identificaron variantes patogénicas en los genes analizados.",
    TipoResultado.NO_CONCLUYENTE: "Se identificaron variantes de significado incierto. "
    "Se sugiere correlación clínica y estudio de familiares.",
}


def _clasificacion(rv: ResultadoVariante) -> str:
    return rv.clasificacion.value.replace("_", " ").lower()


async def confirmar_resultado(
    session: AsyncSession, ints: Integraciones, bio: Usuario, estudio_id: int, datos: ResultadoEntrada
) -> Resultado:
    """E28: registra las Variantes y su clasificación, genera el PDF del Resultado y avisa al Médico
    Tratante y al Paciente. Sin Variantes → NEGATIVO (excepción de E28)."""
    estudio = await obtener_estudio(session, estudio_id, para_actualizar=True)
    if estudio.estado != EstadoEstudio.EN_ANALISIS:
        raise Conflicto("ESTUDIO_NO_EN_ANALISIS", "Primero tenés que tomar el Estudio.")
    if estudio.bioinformatico_id != bio.id or bio.rol != RolUsuario.BIOINFORMATICO:
        raise SinPermiso("Ese Estudio lo está analizando otro Bioinformático.")
    catalogo = ints.para_estudio(estudio.id).bioinformatica
    seleccionadas: dict[tuple[int, str], VarianteExterna] = {}
    elegidas = []
    for v in datos.variantes:
        gen, eg = await _gen_del_estudio(session, estudio, v.gen)
        clave = (gen.id, v.nomenclatura)
        if clave in seleccionadas:
            raise ErrorNegocio("VARIANTE_REPETIDA", f"La Variante {v.gen} {v.nomenclatura} está repetida.")
        externa = await catalogo.variante_exacta(gen=gen.simbolo, nomenclatura=v.nomenclatura)
        if externa is None:
            raise ErrorNegocio(
                "VARIANTE_DESCONOCIDA",
                f"La API de bioinformática no informa la Variante {v.nomenclatura} en {gen.simbolo}.",
            )
        seleccionadas[clave] = externa
        elegidas.append((gen, eg, v))

    guardadas = await _guardar_variantes(session, seleccionadas)
    filas: list[tuple[Gen, Variante, ResultadoVariante]] = []
    for gen, eg, v in elegidas:
        variante = guardadas[gen.id, v.nomenclatura]
        filas.append(
            (
                gen,
                variante,
                ResultadoVariante(
                    variante_id=variante.id,
                    clasificacion=v.clasificacion,
                    hallazgo_secundario=eg.origen == OrigenGen.HALLAZGO_SECUNDARIO,
                ),
            )
        )
    # SUPUESTO S5: los hallazgos secundarios no definen el tipo de Resultado
    tipo = tipo_resultado(rv.clasificacion for _, _, rv in filas if not rv.hallazgo_secundario)
    resultado = Resultado(estudio_id=estudio.id, tipo=tipo, confirmado_por=bio.id)
    session.add(resultado)
    await session.flush()
    for _, _, rv in filas:
        rv.resultado_id = resultado.id
        session.add(rv)

    paciente = await session.get(Paciente, estudio.paciente_id)
    assert paciente is not None
    genes = await consultas.genes_del_estudio(session, estudio.id)
    analizados = [g.simbolo for g in genes if g.origen != OrigenGen.HALLAZGO_SECUNDARIO.value]
    lineas = [
        f"Estudio: {estudio.codigo} ({estudio.tipo.value.title()})",
        f"Paciente: {paciente.nombre_completo} - DNI {paciente.dni}",
        f"Genes analizados: {', '.join(analizados)}",
        "",
        f"RESULTADO: {tipo.value.replace('_', ' ')}",
        _CONCLUSION[tipo],
        "",
        "Variantes identificadas:" if filas else "Variantes identificadas: ninguna.",
    ]
    for gen, variante, rv in filas:
        extra = " (hallazgo secundario)" if rv.hallazgo_secundario else ""
        lineas.append(f"  - {gen.simbolo} {variante.nomenclatura}: {_clasificacion(rv)}{extra}")
    lineas += [
        "",
        f"Informe confirmado por {bio.nombre_completo} el {ahora().astimezone().strftime('%d/%m/%Y')}.",
        "Este informe debe ser interpretado por el Médico Tratante.",
    ]
    pdf = generar_pdf("Resultado del Estudio genético", lineas)
    resultado.pdf_id = (
        await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.RESULTADO_PDF,
            nombre=f"resultado-{estudio.codigo}.pdf",
            mime="application/pdf",
            contenido=pdf,
            subido_por=bio.id,
        )
    ).id
    await transicionar(
        session, estudio, EstadoEstudio.FINALIZADO, bio, f"Resultado {tipo.value.replace('_', ' ')}"
    )
    return resultado
