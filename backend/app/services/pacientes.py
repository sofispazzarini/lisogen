"""E2 Dar de alta Paciente, E3 Cargar Familiograma, ficha del Paciente."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import al_confirmar
from app.domain.enums import RolUsuario, TipoArchivo
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado, SinPermiso
from app.domain.reglas import es_menor_de_edad, validar_diagnostico
from app.integrations.ports import FamiliarExterno
from app.integrations.registro import Integraciones
from app.models import (
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
    DiagnosticoSalida,
    FamiliarEntrada,
    FamiliarSalida,
    PacienteAlta,
    PacienteFicha,
    PacienteResumen,
)
from app.services import consultas
from app.services.comun import ahora, auditar, guardar_archivo, url_archivo


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
    if datos.familiares:
        await cargar_familiograma(session, ints, medico, paciente, datos.familiares)

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
) -> None:
    """E3: registra a los familiares, los envía a la API de familiograma y asocia el PDF al Paciente."""
    nombres_patologia: dict[int, str] = {}
    ids = {f.patologia_diagnosticada_id for f in familiares if f.patologia_diagnosticada_id}
    if ids:
        nombres_patologia = dict(
            (await session.execute(select(Patologia.id, Patologia.nombre).where(Patologia.id.in_(ids))))
            .tuples()
            .all()
        )
        if set(nombres_patologia) != ids:
            raise ErrorNegocio("PATOLOGIA_INVALIDA", "Alguna Patología de los familiares no existe.")
    session.add_all(
        Familiar(
            paciente_id=paciente.id,
            parentesco=f.parentesco,
            nombre=f.nombre,
            sintomas=f.sintomas,
            patologia_diagnosticada=f.patologia_diagnosticada_id,
        )
        for f in familiares
    )
    await session.flush()
    todos = list(
        await session.scalars(
            select(Familiar).where(Familiar.paciente_id == paciente.id).order_by(Familiar.id)
        )
    )
    nombres_patologia |= dict((await session.execute(select(Patologia.id, Patologia.nombre))).tuples().all())
    pdf = await ints.familiograma.generar(
        familiares=[
            FamiliarExterno(
                parentesco=f.parentesco.value,
                nombre=f.nombre,
                sintomas=f.sintomas,
                diagnostico=nombres_patologia.get(f.patologia_diagnosticada)
                if f.patologia_diagnosticada
                else None,
            )
            for f in todos
        ]
    )
    archivo = await guardar_archivo(
        session,
        ints,
        tipo=TipoArchivo.FAMILIOGRAMA_PDF,
        nombre=f"familiograma-{paciente.id}.pdf",
        mime="application/pdf",
        contenido=pdf,
        subido_por=medico.id,
    )
    paciente.familiograma_archivo_id = archivo.id


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
                parentesco=f.parentesco, nombre=f.nombre, sintomas=f.sintomas, patologia_diagnosticada=n
            )
            for f, n in familiares
        ],
        familiograma_url=await url_archivo(session, ints, paciente.familiograma_archivo_id),
        estudios=await consultas.resumenes(
            session, Estudio.paciente_id == paciente.id, orden=[Estudio.created_at.desc(), Estudio.id.desc()]
        ),
    )
