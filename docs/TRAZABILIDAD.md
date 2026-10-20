# TRAZABILIDAD — Escenario → servicio → endpoint → vista

Fuente: `docs/Escenarios.pdf` (E1–E33). Cada endpoint y cada vista se trazan a un Escenario. Los servicios viven en `backend/app/services/`, los routers en `backend/app/api/routers/` y las vistas en `frontend/src/views/`.

| Esc. | Título | Rol | Servicio (`services/`) | Endpoint | Vista (`views/<rol>/`) |
|---|---|---|---|---|---|
| E1 | Registrar Médico Tratante | Médico | `registro.registrar_profesional(rol=MEDICO)` | `POST /auth/registro` | `auth/RegistroProfesional` |
| E2 | Dar de alta Paciente | Médico | `pacientes.dar_de_alta_paciente` (+`domain.reglas.validar_diagnostico`, mail de credenciales) | `POST /medico/pacientes`, `GET /medico/snomed?q=`, `GET /medico/patologias`, `GET /medico/obras-sociales`, `POST /medico/pacientes/buscar` | `medico/AltaPaciente` |
| E3 | Cargar Familiograma | Médico | `pacientes.cargar_familiograma` (API familiograma → PDF en MinIO) | `POST /medico/pacientes` (campo `familiares`), `POST /medico/pacientes/{id}/familiograma` | `medico/AltaPaciente` (sección) |
| E4 | Dar de alta Estudio | Médico | `estudios.dar_de_alta_estudio` (API bioinformática, genes manuales, hallazgos secundarios, Urgente) | `GET /medico/patologias/{id}/genes`, `POST /medico/estudios`, `GET /medico/estudios`, `GET /medico/estudios/{id}` | `medico/AltaEstudio` |
| E5 | Asignar Cupón a Paciente | Médico | `cupones.del_medico`, `cupones.asignar_a_paciente` | `GET /medico/cupones`, `POST /medico/cupones/{id}/asignar` | `medico/MisCupones` |
| E6 | Solicitar Reanálisis | Médico | `pacientes.ficha` (+auditoría), `estudios.solicitar_reanalisis` | `GET /medico/pacientes/{id}`, `POST /medico/estudios/{id}/reanalisis` | `medico/FichaPaciente` |
| E7 | Ingresar por primera vez | Paciente | `auth.login`, `auth.cambiar_password`, `auth.verificar_dispositivo` | `POST /auth/login`, `/auth/cambiar-password`, `/auth/verificar`, `/auth/refresh` | `auth/Login`, `auth/CambioPassword`, `auth/Verificacion` |
| E8 | Pagar Presupuesto | Paciente | `finanzas.pagar` (simulado, movimiento financiero) | `GET /paciente/estudios`, `GET /paciente/estudios/{id}`, `GET /paciente/estudios/{id}/presupuesto`, `POST /paciente/estudios/{id}/pagar` | `paciente/MisEstudios`, `paciente/Pagar` |
| E9 | Aplicar Cupón | Paciente | `cupones.aplicar` (valida con el módulo, lee el QR del PDF, marca USADO) | `GET /paciente/cupones`, `POST /paciente/estudios/{id}/cupon` (multipart: `codigo` o `archivo`) | `paciente/Pagar` |
| E10 | Solicitar reautorización | Paciente | `finanzas.solicitar_reautorizacion` (PDF judicial en MinIO) | `POST /paciente/estudios/{id}/reautorizacion` (multipart) | `paciente/Reautorizacion` |
| E11 | Sacar Turno | Paciente | `turnos.agenda`, `turnos.sacar_turno` (PDFs de orden y consentimiento, recordatorio), `turnos.registrar_inasistencia` | `GET /paciente/centros`, `GET /paciente/centros/{id}/agenda?fecha=`, `POST /paciente/turnos`, `GET /paciente/estudios/{id}/turno` | `paciente/SacarTurno` (Leaflet + grilla), `paciente/MiTurno` |
| E12 | Cancelar Turno | Paciente | `turnos.cancelar_turno` | `POST /paciente/turnos/{id}/cancelar` | `paciente/MiTurno` |
| E13 | Consultar Resultado | Paciente | `resultados.resultado` (+auditoría `VER_RESULTADO`, URL firmada) | `GET /paciente/estudios`, `GET /paciente/estudios/{id}/resultado` (y `GET /medico/estudios/{id}/resultado`) | `paciente/MisEstudios` (línea de pasos), `paciente/Resultado` |
| E14 | Consultar Chatbot | Paciente | `chatbot.preguntar`, `chatbot.historial` | `POST /paciente/chatbot`, `GET /paciente/chatbot` | `paciente/Chatbot` |
| E15 | Registrar Administrativo | Administrativo | `registro.registrar_profesional(rol=ADMIN)` | `POST /auth/registro` | `auth/RegistroProfesional` |
| E16 | Emitir Presupuesto | Administrativo | `finanzas.previsualizar_presupuesto`, `finanzas.emitir_presupuesto` (+`domain.reglas.calcular_presupuesto`, API de obras sociales) | `GET /administrativo/estudios?estado=CREADO`, `GET /administrativo/estudios/{id}/presupuesto/previo`, `POST /administrativo/estudios/{id}/presupuesto` | `administrativo/Tablero`, `administrativo/EmitirPresupuesto` |
| E17 | Registrar Autorización OS | Administrativo | `finanzas.registrar_autorizacion` (pago de la OS; parcial → diferencia POR_PAGAR) | `POST /administrativo/estudios/{id}/autorizacion`, `GET /administrativo/reautorizaciones` | `administrativo/Autorizaciones` |
| E18 | Registrar Rechazo OS | Administrativo | `finanzas.registrar_rechazo` | `POST /administrativo/estudios/{id}/rechazo` | `administrativo/Autorizaciones` |
| E19 | Seguir Muestra en mapa | Administrativo | `logistica.buscar_muestras`, `logistica.ubicar_muestra` | `POST /administrativo/muestras/buscar`, `GET /administrativo/muestras/{id}/ubicacion` | `administrativo/SeguirMuestra` (Leaflet) |
| E20 | Programar retiro FedEx | Administrativo | `lotes.listar`, `lotes.programar_retiro`, `lotes.confirmar_retiro_fedex` (webhook) | `GET /administrativo/lotes`, `POST /administrativo/lotes/{id}/retiro`, `POST /integraciones/fedex/lotes/{id}/{token}` | `administrativo/Lotes` |
| E21 | Cargar datos crudos | Administrativo | `laboratorio.cargar_datos_crudos` (MinIO, avisa a los Bioinformáticos) | `POST /administrativo/estudios/{id}/datos-crudos` (multipart) | `administrativo/CargarDatosCrudos` |
| E22 | Solicitar nueva extracción | Administrativo | `laboratorio.solicitar_reextraccion` (sin costo) | `POST /administrativo/estudios/{id}/reextraccion` | `administrativo/NuevaExtraccion` |
| — | Registro financiero | Administrativo | `finanzas.registro_financiero` | `GET /administrativo/movimientos` | `administrativo/RegistroFinanciero` |
| E23 | Consultar Orden del Día | Transportista | `logistica.generar_ordenes_del_dia` (job 06:00, optimizador), `logistica.orden_del_dia` | `GET /transportista/orden-del-dia` | `transportista/OrdenDelDia` |
| E24 | Recolectar Muestras | Transportista | `logistica.recolectar`, `logistica.registrar_posicion` | `POST /transportista/paradas/{id}/recolectar`, `POST /transportista/posicion` | `transportista/Recolectar` |
| E25 | Confirmar llegada Lab Central | Transportista | `lotes.confirmar_llegada` (+`domain.reglas.armar_lotes`, CSV al Ministerio, sellado, re-extracción < 2 ml) | `POST /transportista/llegada` | `transportista/ConfirmarLlegada` |
| E26 | Registrar Bioinformático | Bioinformático | `registro.registrar_profesional(rol=BIOINF)` | `POST /auth/registro` | `auth/RegistroProfesional` |
| E27 | Tomar Estudio | Bioinformático | `analisis.pendientes`, `analisis.tomar` (lock optimista con `version` → 409) | `GET /bioinformatico/pendientes`, `POST /bioinformatico/estudios/{id}/tomar`, `GET /bioinformatico/estudios` | `bioinformatico/Pendientes` |
| E28 | Cargar Variantes | Bioinformático | `analisis.variantes_de_gen`, `analisis.confirmar_resultado` (+`domain.reglas.tipo_resultado`, PDF, avisos) | `GET /bioinformatico/estudios/{id}`, `GET /bioinformatico/estudios/{id}/genes/{gen}/variantes`, `POST /bioinformatico/estudios/{id}/resultado` | `bioinformatico/CargarVariantes` |
| E29 | Registrar Gerente Médico | Gerente | `registro.registrar_profesional(rol=GERENTE)` | `POST /auth/registro` | `auth/RegistroProfesional` |
| E30 | Dar de alta Patología | Gerente | `patologias.dar_de_alta` | `GET /gerente/snomed?q=`, `GET /gerente/patologias`, `POST /gerente/patologias` | `gerente/Patologias` |
| E31 | Modificar Patología | Gerente | `patologias.modificar` | `PUT /gerente/patologias/{id}` | `gerente/Patologias` |
| E32 | Generar Cupón | Gerente | `cupones.generar` (módulo cupones; sin QR → código numérico) | `POST /gerente/cupones`, `GET /gerente/cupones` | `gerente/Cupones` |
| E33 | Asignar Cupón a Médico | Gerente | `cupones.asignar_a_medico` | `POST /gerente/cupones/asignar`, `GET /gerente/medicos` | `gerente/Cupones` |

Transversales: `GET /avisos`, `POST /avisos/{id}/leido`, `POST /avisos/leidos` (bandeja de Avisos en cada layout, cualquier rol); `GET /{rol}/estudios` (tabla con badge de Estado y Urgente).

Jobs: `jobs/orden_del_dia.py` (06:00 L–V no feriado, E23) · `jobs/recordatorios.py` (día anterior, E11) · `jobs/cierre_jornada.py` (RESERVADO vencido → AUSENTE, +inasistencia; 5 → POR_PAGAR + PERDIDA_POR_INASISTENCIAS, E11).

Fuera de alcance (PO): tablero de control de gerencia, WhatsApp, pasarela de pago real.
