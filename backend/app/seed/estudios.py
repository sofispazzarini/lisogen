"""Seis Estudios de ejemplo en distintos Estados, uno Urgente. Se arman con los servicios reales, así el
historial, los avisos, los PDFs y los movimientos son los mismos que dejaría el uso del sistema.

| Estudio | Paciente | Patología | Estado final |
|---|---|---|---|
| A | Paciente demo (Martín Ibarra) | Fabry | FINALIZADO (POSITIVO) |
| B | Paciente demo | Gaucher | POR_PAGAR, con un Cupón del 20% asignado |
| C | Lucas Ferrari, 2 meses, OSPS | Pompe (Urgente) | EN_ANALISIS_BIOINFORMATICA |
| D | Valeria Quiroga, Prepaga Andina | MPS 1 | CREADO |
| E | Jorge Medina, Obra Social Federal | ASMD | PENDIENTE_AUTORIZACION |
| F | Paula Sosa, particular | Fabry | LISTO_PARA_RETIRAR en Caballito |
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import ClasifVariante, RolUsuario, TipoSospecha
from app.domain.reglas import TZ_AR, es_dia_habil
from app.integrations.registro import Integraciones
from app.models import (
    CentroExtraccion,
    Estudio,
    Feriado,
    ObraSocial,
    Paciente,
    Patologia,
    Transportista,
    Usuario,
)
from app.schemas.roles import (
    DiagnosticoEntrada,
    EstudioAlta,
    PacienteAlta,
    ResultadoEntrada,
    TurnoEntrada,
    VarianteEntrada,
)
from app.seed.datos import USUARIOS
from app.services import (
    analisis,
    cupones,
    estudios,
    finanzas,
    laboratorio,
    logistica,
    lotes,
    pacientes,
    turnos,
)
from app.services.comun import ahora
from app.services.extracciones import registrar_extraccion


async def _dias_habiles(session: AsyncSession, cantidad: int) -> list[date]:
    no_habiles = set(await session.scalars(select(Feriado.fecha)))
    dia = ahora().astimezone(TZ_AR).date()
    dias: list[date] = []
    while len(dias) < cantidad:
        dia += timedelta(days=1)
        if es_dia_habil(dia, no_habiles):
            dias.append(dia)
    return dias


def _a_las(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=TZ_AR).astimezone(UTC)


async def _id(session: AsyncSession, modelo: type, **filtro: object) -> int:
    columna, valor = next(iter(filtro.items()))
    resultado = await session.scalar(select(modelo.id).where(getattr(modelo, columna) == valor))  # type: ignore[attr-defined]
    assert resultado is not None, f"{modelo.__name__} {filtro}"
    return int(resultado)


async def _alta_paciente(
    session: AsyncSession,
    ints: Integraciones,
    medico: Usuario,
    *,
    dni: str,
    nombre: str,
    apellido: str,
    nacimiento: date,
    email: str,
    patologia: str,
    sintomas: list[int],
    resumen: str,
    obra_social: str | None = None,
) -> Paciente:
    os_id = await _id(session, ObraSocial, codigo_externo=obra_social) if obra_social else None
    return await pacientes.dar_de_alta_paciente(
        session,
        ints,
        medico,
        PacienteAlta(
            dni=dni,
            nombre=nombre,
            apellido=apellido,
            fecha_nacimiento=nacimiento,
            telefono="+54 11 4000-0000",
            email=email,
            obra_social_id=os_id,
            nro_afiliado=f"{obra_social}-{dni}" if obra_social else None,
            resumen_historia_clinica=resumen,
            sintomas=sintomas,
            diagnosticos=[
                DiagnosticoEntrada(
                    patologia_id=await _id(session, Patologia, nombre=patologia),
                    tipo_sospecha=TipoSospecha.CLINICA,
                )
            ],
        ),
    )


async def _alta_estudio(
    session: AsyncSession,
    ints: Integraciones,
    medico: Usuario,
    paciente: Paciente,
    patologia: str,
    hallazgos: bool = False,
) -> Estudio:
    return await estudios.dar_de_alta_estudio(
        session,
        ints,
        medico,
        EstudioAlta(
            paciente_id=paciente.id,
            patologia_ids=[await _id(session, Patologia, nombre=patologia)],
            evalua_hallazgos_secundarios=hallazgos,
        ),
    )


async def cargar_estudios(session: AsyncSession, ints: Integraciones) -> None:
    emails = [d.email for d in USUARIOS]
    u = {x.rol: x for x in await session.scalars(select(Usuario).where(Usuario.email.in_(emails)))}
    medico, admin = u[RolUsuario.MEDICO_TRATANTE], u[RolUsuario.ADMINISTRATIVO]
    bio, gerente, transportista = (
        u[RolUsuario.BIOINFORMATICO],
        u[RolUsuario.GERENTE_MEDICO],
        u[RolUsuario.TRANSPORTISTA],
    )
    cuenta_demo = u[RolUsuario.PACIENTE]
    demo = await session.scalar(select(Paciente).where(Paciente.usuario_id == cuenta_demo.id))
    assert demo is not None
    palermo = await _id(session, CentroExtraccion, nombre="Centro de Extracción Palermo")
    caballito = await _id(session, CentroExtraccion, nombre="Centro de Extracción Caballito")
    dia1, dia2 = await _dias_habiles(session, 2)

    lucas = await _alta_paciente(
        session,
        ints,
        medico,
        dni="58123456",
        nombre="Lucas",
        apellido="Ferrari",
        nacimiento=ahora().date() - timedelta(days=60),
        email="familia.ferrari@lisogen-demo.com.ar",
        patologia="Pompe",
        sintomas=[398152000, 8186001, 25273001],
        obra_social="OSPS",
        resumen="Lactante de 2 meses con hipotonía marcada, cardiomegalia en la radiografía y macroglosia.",
    )
    valeria = await _alta_paciente(
        session,
        ints,
        medico,
        dni="45987654",
        nombre="Valeria",
        apellido="Quiroga",
        nacimiento=date(2004, 8, 2),
        email="valeria.quiroga@lisogen-demo.com.ar",
        patologia="MPS 1",
        sintomas=[254069004, 64634000, 84445001],
        obra_social="ANDINA",
        resumen="Disostosis múltiple, opacidad corneal bilateral y rigidez articular progresiva.",
    )
    jorge = await _alta_paciente(
        session,
        ints,
        medico,
        dni="27456123",
        nombre="Jorge",
        apellido="Medina",
        nacimiento=date(1979, 1, 23),
        email="jorge.medina@lisogen-demo.com.ar",
        patologia="ASMD",
        sintomas=[36760000, 233703007, 370992007],
        obra_social="FEDERAL",
        resumen="Hepatoesplenomegalia, enfermedad pulmonar intersticial y dislipidemia.",
    )
    paula = await _alta_paciente(
        session,
        ints,
        medico,
        dni="33222111",
        nombre="Paula",
        apellido="Sosa",
        nacimiento=date(1990, 11, 5),
        email="paula.sosa@lisogen-demo.com.ar",
        patologia="Fabry",
        sintomas=[254788004, 45004005, 60862001],
        resumen="Angioqueratomas en tronco, hipohidrosis y tinnitus. Padre con insuficiencia renal.",
    )
    cuentas = {
        p.id: await session.get(Usuario, p.usuario_id)
        for p in (demo, lucas, valeria, jorge, paula)
        if p.usuario_id
    }

    # A (Fabry, Paciente demo) y C (Pompe Urgente): viajan juntos en el Lote que sella el Urgente
    a = await _alta_estudio(session, ints, medico, demo, "Fabry", hallazgos=True)
    c = await _alta_estudio(session, ints, medico, lucas, "Pompe")
    await finanzas.emitir_presupuesto(session, ints, admin, a)
    await finanzas.pagar(session, cuenta_demo, a)
    await finanzas.emitir_presupuesto(session, ints, admin, c)
    await finanzas.registrar_autorizacion(session, admin, c)
    turno_a = await turnos.sacar_turno(
        session,
        ints,
        cuenta_demo,
        TurnoEntrada(estudio_id=a.id, centro_id=palermo, inicio=_a_las(dia1, 9, 30)),
    )
    cuenta_lucas = cuentas[lucas.id]
    assert cuenta_lucas is not None
    turno_c = await turnos.sacar_turno(
        session,
        ints,
        cuenta_lucas,
        TurnoEntrada(estudio_id=c.id, centro_id=palermo, inicio=_a_las(dia1, 9, 45)),
    )
    await registrar_extraccion(session, turno_a.id, Decimal("4.0"))
    await registrar_extraccion(session, turno_c.id, Decimal("2.5"))

    ayer = logistica.hoy() - timedelta(days=1)  # recorrido ya hecho: no ocupa la Orden del Día de hoy
    t = await session.get(Transportista, transportista.id)
    assert t is not None
    orden = await logistica.crear_orden(session, ints, t, ayer)
    assert orden is not None
    for parada in (await logistica.orden_del_dia(session, transportista, ayer)).paradas:
        await logistica.recolectar(session, transportista, parada.id, ayer)
    llegada = await lotes.confirmar_llegada(session, ints, transportista, ayer)
    lote_id = next(
        lt.id for lt in await lotes.listar(session, ints) if lt.codigo == llegada.lotes_sellados[0]
    )
    await lotes.programar_retiro(session, ints, lote_id, _a_las(dia2, 10))
    await lotes.confirmar_retiro_fedex(
        session, lote_id, security.token_webhook("lote", lote_id)
    )  # FedEx (mock)
    for e in (a, c):
        await laboratorio.cargar_datos_crudos(
            session, ints, admin, e.id, f"{e.codigo}.fastq.gz", b"@EXOMA\nACGT\n"
        )
    await analisis.tomar(session, bio, a.id, a.version)
    await analisis.confirmar_resultado(
        session,
        ints,
        bio,
        a.id,
        ResultadoEntrada(
            variantes=[
                VarianteEntrada(
                    gen="GLA", nomenclatura="c.644A>G (p.Asn215Ser)", clasificacion=ClasifVariante.PATOGENICA
                )
            ]
        ),
    )

    # B (Gaucher, Paciente demo): Presupuesto emitido y un Cupón listo para aplicar
    b = await _alta_estudio(session, ints, medico, demo, "Gaucher")
    await finanzas.emitir_presupuesto(session, ints, admin, b)
    generados = await cupones.generar(session, ints, gerente, 20, 3, None)
    await cupones.asignar_a_medico(session, [c_.id for c_ in generados[:2]], medico.id)
    await cupones.asignar_a_paciente(session, medico, generados[0].id, demo.id)

    # D (MPS 1): recién dado de alta, para Emitir Presupuesto
    await _alta_estudio(session, ints, medico, valeria, "MPS 1")

    # E (ASMD): esperando la Autorización de la Obra Social
    e = await _alta_estudio(session, ints, medico, jorge, "ASMD")
    await finanzas.emitir_presupuesto(session, ints, admin, e)

    # F (Fabry): Muestra lista en Caballito → aparece en la Orden del Día de hoy (si es hábil)
    f = await _alta_estudio(session, ints, medico, paula, "Fabry")
    await finanzas.emitir_presupuesto(session, ints, admin, f)
    cuenta_paula = cuentas[paula.id]
    assert cuenta_paula is not None
    await finanzas.pagar(session, cuenta_paula, f)
    turno_f = await turnos.sacar_turno(
        session,
        ints,
        cuenta_paula,
        TurnoEntrada(estudio_id=f.id, centro_id=caballito, inicio=_a_las(dia1, 11)),
    )
    await registrar_extraccion(session, turno_f.id, Decimal("3.5"))
    await logistica.generar_ordenes_del_dia(session, ints, logistica.hoy())
