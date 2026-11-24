"""E2 Dar de alta Paciente, E3 Cargar Familiograma, ficha del Paciente."""

import logging
from dataclasses import asdict
from typing import Final

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import al_confirmar
from app.domain.enums import RolUsuario, TipoArchivo
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado, SinPermiso
from app.domain.reglas import es_menor_de_edad, validar_diagnostico
from app.integrations import familiograma_mapeo as mapeo
from app.integrations.ports import Advertencia, ErrorFamiliograma, Familiograma
from app.integrations.registro import Integraciones
from app.models import (
    Archivo,
    DiagnosticoPresuntivo,
    Estudio,
    Familiar,
    ObraSocial,
    Paciente,
    PacienteSintoma,
    Patologia,
    SnomedConcepto,
    Usuario,
)
from app.schemas.comun import Concepto
from app.schemas.roles import (
    AdvertenciaSalida,
    DiagnosticoSalida,
    FamiliarEntrada,
    FamiliarSalida,
    PacienteAlta,
    PacienteFicha,
    PacienteResumen,
)
from app.services import consultas
from app.services.comun import ahora, auditar, guardar_archivo, url_archivo

logger = logging.getLogger(__name__)


async def paciente_del_medico(session: AsyncSession, medico: Usuario, paciente_id: int) -> Paciente:
    """Un Médico sólo ve a sus Pacientes: los que dio de alta o los que tienen Estudios suyos."""
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise NoEncontrado("Paciente")
    if paciente.medico_alta_id != medico.id:
        tiene_estudio = await session.scalar(
            select(Estudio.id).where(
                Estudio.paciente_id == paciente.id, Estudio.medico_tratante_id == medico.id
            )
        )
        if tiene_estudio is None:
            raise SinPermiso("Ese Paciente no está a tu cargo.")
    return paciente


async def validar_sintomas_contra_patologias(
    session: AsyncSession, sintomas: list[int], patologia_ids: list[int]
) -> list[Patologia]:
    """Validar Diagnóstico (E2): síntoma cardinal o dos secundarios de cada Patología sospechada."""
    patologias = list(await session.scalars(select(Patologia).where(Patologia.id.in_(patologia_ids))))
    if len(patologias) != len(set(patologia_ids)):
        raise ErrorNegocio("PATOLOGIA_INVALIDA", "Alguna Patología no existe.")
    for p in patologias:
        secundarios = [s.concept_id for s in p.secundarios]
        if not validar_diagnostico(sintomas, p.sintoma_cardinal_id, secundarios):
            raise ErrorNegocio(
                "DIAGNOSTICO_NO_VALIDADO",
                f"Los síntomas no incluyen el síntoma cardinal ni dos síntomas secundarios de {p.nombre}.",
            )
    return patologias


async def dar_de_alta_paciente(
    session: AsyncSession, ints: Integraciones, medico: Usuario, datos: PacienteAlta
) -> Paciente:
    if medico.rol != RolUsuario.MEDICO_TRATANTE:
        raise SinPermiso()
    if datos.fecha_nacimiento > ahora().date():
        raise ErrorNegocio("FECHA_NACIMIENTO_INVALIDA", "La fecha de nacimiento no puede ser futura.")
    if datos.nro_afiliado and datos.obra_social_id is None:
        raise ErrorNegocio("OBRA_SOCIAL_REQUERIDA", "Indicá la Obra Social del número de afiliado.")
    if datos.obra_social_id is not None and await session.get(ObraSocial, datos.obra_social_id) is None:
        raise ErrorNegocio("OBRA_SOCIAL_INVALIDA", "La Obra Social no existe.")
    sintomas = sorted(set(datos.sintomas))
    conocidos = set(
        await session.scalars(
            select(SnomedConcepto.concept_id).where(SnomedConcepto.concept_id.in_(sintomas))
        )
    )
    if conocidos != set(sintomas):
        raise ErrorNegocio("SINTOMA_DESCONOCIDO", "Algún síntoma no está en el catálogo SNOMED.")
    await validar_sintomas_contra_patologias(session, sintomas, [d.patologia_id for d in datos.diagnosticos])

    if await session.scalar(select(Paciente.id).where(Paciente.dni == datos.dni)):
        raise Conflicto("PACIENTE_EXISTENTE", "Ya hay un Paciente registrado con ese DNI.")
    if await session.scalar(select(Usuario.id).where(Usuario.email == datos.email)):
        # SUPUESTO S7: la cuenta es 1:1 con el Paciente; un padre o madre con dos hijos usa mails distintos.
        raise Conflicto("EMAIL_EN_USO", "Ya hay una cuenta registrada con ese mail.")

    menor = es_menor_de_edad(datos.fecha_nacimiento, ahora().date())
    provisoria = security.password_provisoria()
    usuario = Usuario(
        email=datos.email,
        password_hash=security.hashear_password(provisoria),
        rol=RolUsuario.PACIENTE,
        nombre=datos.nombre,
        apellido=datos.apellido,
        telefono=datos.telefono,
        debe_cambiar_password=True,
    )
    session.add(usuario)
    await session.flush()
    paciente = Paciente(
        usuario_id=usuario.id,
        dni=datos.dni,
        nombre=datos.nombre,
        apellido=datos.apellido,
        fecha_nacimiento=datos.fecha_nacimiento,
        telefono=datos.telefono,
        email_contacto=datos.email,
        es_menor_al_alta=menor,
        obra_social_id=datos.obra_social_id,
        nro_afiliado=datos.nro_afiliado if datos.obra_social_id else None,
        resumen_historia_clinica=datos.resumen_historia_clinica,
        medico_alta_id=medico.id,
    )
    session.add(paciente)
    await session.flush()
    session.add_all(PacienteSintoma(paciente_id=paciente.id, concept_id=c) for c in sintomas)
    session.add_all(
        DiagnosticoPresuntivo(
            paciente_id=paciente.id,
            patologia_id=d.patologia_id,
            tipo_sospecha=d.tipo_sospecha,
            medico_id=medico.id,
        )
        for d in {d.patologia_id: d for d in datos.diagnosticos}.values()
    )
    if datos.familiares:  # el Familiograma es opcional (C1): si la API falla, el alta sigue igual
        await cargar_familiograma(session, ints, medico, paciente, datos.familiares, bloqueante=False)

    destinatario = datos.email
    saludo = "Hola. Te damos de alta en LisoGen en nombre de tu hijo o hija." if menor else "Hola."

    async def _enviar_credenciales() -> None:
        await ints.mail.enviar(
            destinatario=destinatario,
            asunto="LisoGen: tus credenciales de acceso",
            cuerpo=(
                f"{saludo}\nTu Médico Tratante te registró en LisoGen para seguir tu Estudio genético.\n\n"
                f"Usuario: {destinatario}\nContraseña provisoria: {provisoria}\n\n"
                "La primera vez que ingreses te vamos a pedir que la cambies."
            ),
        )

    al_confirmar(session, _enviar_credenciales)
    return paciente


async def cargar_familiograma(
    session: AsyncSession,
    ints: Integraciones,
    medico: Usuario,
    paciente: Paciente,
    familiares: list[FamiliarEntrada],
    *,
    bloqueante: bool = True,
) -> None:
    """E3: registra a los familiares (puede no haber nuevos: entonces regenera la imagen), envía el árbol
    completo a la API de familiograma y asocia el SVG y sus advertencias al Paciente.

    `bloqueante=False` (alta del Paciente): si la API no genera la imagen, los familiares se guardan igual
    y queda la advertencia FAMILIOGRAMA_PENDIENTE para regenerarlo desde la ficha."""
    ids = {f.patologia_diagnosticada_id for f in familiares if f.patologia_diagnosticada_id}
    if ids:
        existentes = set(await session.scalars(select(Patologia.id).where(Patologia.id.in_(ids))))
        if existentes != ids:
            raise ErrorNegocio("PATOLOGIA_INVALIDA", "Alguna Patología de los familiares no existe.")
    session.add_all(
        Familiar(
            paciente_id=paciente.id,
            parentesco=f.parentesco,
            nombre=f.nombre,
            apellido=f.apellido,
            lado=f.lado,
            sintomas=f.sintomas,
            patologia_diagnosticada=f.patologia_diagnosticada_id,
        )
        for f in familiares
    )
    await session.flush()
    todos = (
        await session.execute(
            select(Familiar, Patologia.nombre)
            .outerjoin(Patologia, Patologia.id == Familiar.patologia_diagnosticada)
            .where(Familiar.paciente_id == paciente.id)
            .order_by(Familiar.id)
        )
    ).all()
    arbol = mapeo.armar_personas(
        mapeo.PacienteInterno(paciente.nombre, paciente.apellido, paciente.fecha_nacimiento),
        [mapeo.FamiliarInterno(f.parentesco, f.nombre, f.apellido, f.lado, n) for f, n in todos],
        hoy=ahora().date(),
    )
    try:
        imagen = await _generar_excluyendo_sin_referencia(ints, arbol)
    except ErrorNegocio as e:
        if bloqueante:
            raise
        logger.warning("Familiograma del paciente %s pendiente: %s", paciente.id, e.code)
        pendiente = Advertencia(
            "FAMILIOGRAMA_PENDIENTE",
            f"No se pudo generar el Familiograma. {e.message} Los familiares quedaron guardados: "
            "generalo de nuevo desde la ficha.",
        )
        paciente.familiograma_advertencias = [asdict(a) for a in (*arbol.advertencias, pendiente)]
        return
    advertencias = [*arbol.advertencias, *imagen.advertencias]
    if advertencias:  # sólo los códigos: los mensajes describen a los familiares
        logger.warning(
            "Familiograma del paciente %s con advertencias: %s", paciente.id, [a.codigo for a in advertencias]
        )
    archivo = await guardar_archivo(
        session,
        ints,
        tipo=TipoArchivo.FAMILIOGRAMA_PDF,  # el tipo conserva su nombre histórico; el contenido es SVG
        nombre=f"familiograma-{paciente.id}.svg",
        mime=imagen.mime,
        contenido=imagen.contenido,
        subido_por=medico.id,
    )
    paciente.familiograma_archivo_id = archivo.id
    paciente.familiograma_advertencias = [asdict(a) for a in advertencias]


# Errores de la API que señalan a un familiar al que le falta su persona de referencia (por ejemplo, un tío
# paterno sin abuelo paterno). Ese familiar se deja fuera del dibujo; el resto del árbol se dibuja igual.
SIN_REFERENCIA: Final = frozenset(
    {"FALTA_PERSONA_DE_REFERENCIA", "LADO_MATERNO_NO_DEDUCIBLE", "LADO_PATERNO_NO_DEDUCIBLE"}
)
MAX_INTENTOS_FAMILIOGRAMA: Final = 3  # cubre exclusiones en cadena (sin tío no hay primo)


async def _generar_excluyendo_sin_referencia(
    ints: Integraciones, arbol: mapeo.ResultadoMapeo
) -> Familiograma:
    """Genera la imagen; si la API marca familiares sin persona de referencia, los excluye (con su
    advertencia) y reintenta. No inventa personas para completar el árbol. Agrega a
    `arbol.advertencias` lo excluido. ErrorNegocio si no se puede generar."""
    vivos = list(range(len(arbol.personas)))  # posición en el pedido → posición en `arbol`
    for intento in range(1, MAX_INTENTOS_FAMILIOGRAMA + 1):
        personas = [arbol.personas[i] for i in vivos]
        etiquetas = [arbol.etiquetas[i] for i in vivos]
        try:
            return await ints.familiograma.generar(personas=personas)
        except mapeo.ErrorMapeo as e:
            raise ErrorNegocio("FAMILIOGRAMA_DATOS_INVALIDOS", str(e)) from e
        except ErrorFamiliograma as e:
            excluir: dict[int, str] = {}
            if e.status == 422 and e.detalles:
                for d in e.detalles:
                    codigo, _, motivo = d.mensaje.partition(":")
                    partes = d.ruta.split(".")
                    if codigo.strip() not in SIN_REFERENCIA or len(partes) < 2 or not partes[1].isdigit():
                        excluir = {}
                        break
                    pos = int(partes[1])
                    if pos == 0 or pos >= len(vivos):  # el Paciente nunca se excluye
                        excluir = {}
                        break
                    excluir[pos] = motivo.strip()
            if not excluir or intento == MAX_INTENTOS_FAMILIOGRAMA:
                raise _rechazo_familiograma(e, etiquetas) from e
            for pos, motivo in sorted(excluir.items()):
                arbol.advertencias.append(
                    Advertencia(
                        "FAMILIAR_SIN_REFERENCIA",
                        f"No se dibujó al {etiquetas[pos][0].lower()}{etiquetas[pos][1:]}: {motivo} Cargá a "
                        "esa persona y generá el Familiograma de nuevo.",
                    )
                )
            vivos = [v for pos, v in enumerate(vivos) if pos not in excluir]
    raise AssertionError("inalcanzable")


def _rechazo_familiograma(e: ErrorFamiliograma, etiquetas: list[str]) -> ErrorNegocio:
    """Traduce el error de la API para el Médico. 401/400/415 son de configuración o bugs nuestros: se
    registran (sin la clave ni los datos enviados) y al usuario le llega un mensaje genérico."""
    if e.status == 422:
        problemas, campos = [], []
        for d in e.detalles:
            partes = d.ruta.split(".")
            quien = "El árbol familiar"
            if len(partes) >= 2 and partes[0] == "personas" and partes[1].isdigit():
                i = int(partes[1])
                quien = etiquetas[i] if i < len(etiquetas) else f"Persona {i}"
                if len(partes) > 2:
                    campos.append(f"{quien} · {'.'.join(partes[2:])}")
            motivo = d.mensaje.split(":", 1)[-1].strip() or d.mensaje
            problemas.append(f"{quien}: {motivo}")
        detalle = "; ".join(problemas) or "revisá los parentescos cargados."
        return ErrorNegocio(
            "FAMILIOGRAMA_DATOS_INVALIDOS",
            f"El servicio de familiograma rechazó el árbol familiar. {detalle}",
            campos=campos,
        )
    if e.status == 413:
        return ErrorNegocio(
            "FAMILIOGRAMA_DEMASIADO_GRANDE",
            "El árbol familiar supera el tamaño que admite el servicio (1 MiB).",
        )
    if e.status == 401:
        logger.error("API de familiograma: HTTP 401, revisar FAMILIOGRAMA_API_KEY")
        return ErrorNegocio(
            "FAMILIOGRAMA_NO_DISPONIBLE",
            "El servicio de familiograma no está disponible por ahora. Avisá a soporte.",
            status=502,
        )
    if e.status in (400, 415):
        logger.error("API de familiograma: HTTP %s (%s), pedido mal armado por LisoGen", e.status, e.codigo)
        return ErrorNegocio(
            "FAMILIOGRAMA_ERROR_INTERNO",
            "No pudimos generar el Familiograma por un error de LisoGen. Avisá a soporte.",
            status=502,
        )
    logger.warning("API de familiograma sin respuesta válida: HTTP %s", e.status)
    return ErrorNegocio(
        "FAMILIOGRAMA_SIN_RESPUESTA",
        "El servicio de familiograma no respondió. Probá de nuevo en unos minutos.",
        status=502,
    )


async def buscar_pacientes(session: AsyncSession, medico: Usuario, texto: str) -> list[PacienteResumen]:
    estudios_mios = select(Estudio.paciente_id).where(Estudio.medico_tratante_id == medico.id)
    consulta = (
        select(Paciente, ObraSocial.nombre, func.count(Estudio.id))
        .outerjoin(ObraSocial, ObraSocial.id == Paciente.obra_social_id)
        .outerjoin(Estudio, Estudio.paciente_id == Paciente.id)
        .where(or_(Paciente.medico_alta_id == medico.id, Paciente.id.in_(estudios_mios)))
        .group_by(Paciente.id, ObraSocial.nombre)
        .order_by(Paciente.apellido, Paciente.nombre)
        .limit(100)
    )
    texto = texto.strip()
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(Paciente.dni.ilike(patron), Paciente.apellido.ilike(patron), Paciente.nombre.ilike(patron))
        )
    filas = (await session.execute(consulta)).all()
    return [
        PacienteResumen(
            id=p.id,
            dni=p.dni,
            nombre_completo=p.nombre_completo,
            fecha_nacimiento=p.fecha_nacimiento,
            obra_social=os_nombre,
            cantidad_estudios=n,
        )
        for p, os_nombre, n in filas
    ]


async def ficha(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, paciente: Paciente, ip: str | None
) -> PacienteFicha:
    auditar(session, usuario.id, "VER_FICHA", "paciente", paciente.id, ip)
    sintomas = await session.execute(
        select(SnomedConcepto)
        .join(PacienteSintoma, PacienteSintoma.concept_id == SnomedConcepto.concept_id)
        .where(PacienteSintoma.paciente_id == paciente.id)
        .order_by(SnomedConcepto.termino)
    )
    diagnosticos = await session.execute(
        select(DiagnosticoPresuntivo, Patologia.nombre)
        .join(Patologia, Patologia.id == DiagnosticoPresuntivo.patologia_id)
        .where(DiagnosticoPresuntivo.paciente_id == paciente.id)
    )
    familiares = await session.execute(
        select(Familiar, Patologia.nombre)
        .outerjoin(Patologia, Patologia.id == Familiar.patologia_diagnosticada)
        .where(Familiar.paciente_id == paciente.id)
        .order_by(Familiar.id)
    )
    os_nombre = (
        await session.scalar(select(ObraSocial.nombre).where(ObraSocial.id == paciente.obra_social_id))
        if paciente.obra_social_id
        else None
    )
    return PacienteFicha(
        id=paciente.id,
        dni=paciente.dni,
        nombre=paciente.nombre,
        apellido=paciente.apellido,
        fecha_nacimiento=paciente.fecha_nacimiento,
        telefono=paciente.telefono,
        email_contacto=paciente.email_contacto,
        es_menor_al_alta=paciente.es_menor_al_alta,
        obra_social=os_nombre,
        nro_afiliado=paciente.nro_afiliado,
        resumen_historia_clinica=paciente.resumen_historia_clinica,
        sintomas=[Concepto(concept_id=c.concept_id, termino=c.termino) for c in sintomas.scalars()],
        diagnosticos=[
            DiagnosticoSalida(patologia_id=d.patologia_id, patologia=n, tipo_sospecha=d.tipo_sospecha)
            for d, n in diagnosticos
        ],
        familiares=[
            FamiliarSalida(
                parentesco=f.parentesco,
                nombre=f.nombre,
                apellido=f.apellido,
                lado=f.lado,
                sintomas=f.sintomas,
                patologia_diagnosticada=n,
            )
            for f, n in familiares
        ],
        familiograma_url=await url_archivo(session, ints, paciente.familiograma_archivo_id),
        familiograma_mime=await session.scalar(
            select(Archivo.mime).where(Archivo.id == paciente.familiograma_archivo_id)
        )
        if paciente.familiograma_archivo_id
        else None,
        familiograma_advertencias=[AdvertenciaSalida(**a) for a in paciente.familiograma_advertencias or []],
        estudios=await consultas.resumenes(
            session, Estudio.paciente_id == paciente.id, orden=[Estudio.created_at.desc(), Estudio.id.desc()]
        ),
    )
