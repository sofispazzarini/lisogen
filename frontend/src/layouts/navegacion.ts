import type { Rol } from '@/stores/auth'

export interface ItemNav {
  texto: string
  ruta: string
  escenarios?: string
}

/** Navegación del prototipo por rol (cada ítem se traza a sus Escenarios). */
export const NAVEGACION: Record<Rol, ItemNav[]> = {
  MEDICO_TRATANTE: [
    { texto: 'Mis Estudios', ruta: '/medico', escenarios: 'E4, E6' },
    { texto: 'Pacientes', ruta: '/medico/pacientes', escenarios: 'E2, E6' },
    { texto: 'Alta Paciente', ruta: '/medico/pacientes/nuevo', escenarios: 'E2, E3' },
    { texto: 'Alta Estudio', ruta: '/medico/estudios/nuevo', escenarios: 'E4' },
    { texto: 'Mis Cupones', ruta: '/medico/cupones', escenarios: 'E5' },
  ],
  PACIENTE: [
    { texto: 'Mis Estudios', ruta: '/paciente', escenarios: 'E8–E13' },
    { texto: 'Chatbot', ruta: '/paciente/chatbot', escenarios: 'E14' },
  ],
  ADMINISTRATIVO: [
    { texto: 'Tablero', ruta: '/administrativo' },
    { texto: 'Emitir Presupuesto', ruta: '/administrativo/presupuestos', escenarios: 'E16' },
    { texto: 'Autorizaciones', ruta: '/administrativo/autorizaciones', escenarios: 'E17, E18' },
    { texto: 'Seguir Muestra', ruta: '/administrativo/muestras', escenarios: 'E19' },
    { texto: 'Lotes y FedEx', ruta: '/administrativo/lotes', escenarios: 'E20' },
    { texto: 'Datos crudos', ruta: '/administrativo/datos-crudos', escenarios: 'E21' },
    { texto: 'Nueva extracción', ruta: '/administrativo/reextracciones', escenarios: 'E22' },
    { texto: 'Registro financiero', ruta: '/administrativo/finanzas' },
  ],
  TRANSPORTISTA: [
    { texto: 'Orden del Día', ruta: '/transportista', escenarios: 'E23, E24' },
    { texto: 'Confirmar llegada', ruta: '/transportista/llegada', escenarios: 'E25' },
  ],
  BIOINFORMATICO: [
    { texto: 'Pendientes', ruta: '/bioinformatico', escenarios: 'E27' },
    { texto: 'Mis análisis', ruta: '/bioinformatico/mis-estudios', escenarios: 'E28' },
  ],
  GERENTE_MEDICO: [
    { texto: 'Patologías', ruta: '/gerente', escenarios: 'E30, E31' },
    { texto: 'Cupones', ruta: '/gerente/cupones', escenarios: 'E32, E33' },
  ],
}
