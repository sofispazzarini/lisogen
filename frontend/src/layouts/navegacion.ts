import type { Rol } from '@/stores/auth'

export interface ItemNav {
  texto: string
  ruta: string
  escenarios?: string
}

/** Secciones de la barra lateral agrupadas por flujo de trabajo. `nombre` vacío: grupo sin título. */
export interface GrupoNav {
  nombre: string
  items: ItemNav[]
}

/** Navegación por rol (cada ítem se traza a sus Escenarios). Los grupos del Administrativo son los de la
 * maqueta del rediseño; los de los demás roles son una propuesta a validar con el laboratorio. */
export const GRUPOS: Record<Rol, GrupoNav[]> = {
  MEDICO_TRATANTE: [
    {
      nombre: 'Estudios',
      items: [
        { texto: 'Mis Estudios', ruta: '/medico', escenarios: 'E4, E6' },
        { texto: 'Alta Estudio', ruta: '/medico/estudios/nuevo', escenarios: 'E4' },
      ],
    },
    {
      nombre: 'Pacientes',
      items: [
        { texto: 'Pacientes', ruta: '/medico/pacientes', escenarios: 'E2, E6' },
        { texto: 'Alta Paciente', ruta: '/medico/pacientes/nuevo', escenarios: 'E2, E3' },
      ],
    },
    { nombre: 'Beneficios', items: [{ texto: 'Mis Cupones', ruta: '/medico/cupones', escenarios: 'E5' }] },
  ],
  PACIENTE: [
    {
      nombre: '',
      items: [
        { texto: 'Mis Estudios', ruta: '/paciente', escenarios: 'E8–E13' },
        { texto: 'Chatbot', ruta: '/paciente/chatbot', escenarios: 'E14' },
      ],
    },
  ],
  ADMINISTRATIVO: [
    { nombre: 'Inicio', items: [{ texto: 'Tablero', ruta: '/administrativo' }] },
    {
      nombre: 'Comercial',
      items: [
        { texto: 'Emitir presupuesto', ruta: '/administrativo/presupuestos', escenarios: 'E16' },
        { texto: 'Autorizaciones', ruta: '/administrativo/autorizaciones', escenarios: 'E17, E18' },
        { texto: 'Registro financiero', ruta: '/administrativo/finanzas' },
      ],
    },
    {
      nombre: 'Muestras',
      items: [
        { texto: 'Nueva extracción', ruta: '/administrativo/reextracciones', escenarios: 'E22' },
        { texto: 'Seguir muestra', ruta: '/administrativo/muestras', escenarios: 'E19' },
        { texto: 'Datos crudos', ruta: '/administrativo/datos-crudos', escenarios: 'E21' },
      ],
    },
    { nombre: 'Envíos', items: [{ texto: 'Lotes y FedEx', ruta: '/administrativo/lotes', escenarios: 'E20' }] },
  ],
  TRANSPORTISTA: [
    {
      nombre: 'Recorrido',
      items: [
        { texto: 'Orden del Día', ruta: '/transportista', escenarios: 'E23, E24' },
        { texto: 'Confirmar llegada', ruta: '/transportista/llegada', escenarios: 'E25' },
      ],
    },
  ],
  BIOINFORMATICO: [
    {
      nombre: 'Análisis',
      items: [
        { texto: 'Pendientes', ruta: '/bioinformatico', escenarios: 'E27' },
        { texto: 'Mis análisis', ruta: '/bioinformatico/mis-estudios', escenarios: 'E28' },
      ],
    },
  ],
  GERENTE_MEDICO: [
    { nombre: 'Catálogo', items: [{ texto: 'Patologías', ruta: '/gerente', escenarios: 'E30, E31' }] },
    { nombre: 'Beneficios', items: [{ texto: 'Cupones', ruta: '/gerente/cupones', escenarios: 'E32, E33' }] },
  ],
}

/** Lista plana de ítems por rol (compatibilidad con quien no necesita los grupos). */
export const NAVEGACION: Record<Rol, ItemNav[]> = Object.fromEntries(
  Object.entries(GRUPOS).map(([rol, grupos]) => [rol, grupos.flatMap((g) => g.items)]),
) as Record<Rol, ItemNav[]>

/** Ítem activo: el de ruta más larga que coincide con la actual (así /medico/pacientes/3 marca Pacientes). */
export function itemActivo(grupos: GrupoNav[], path: string): { grupo: GrupoNav; item: ItemNav } | null {
  let mejor: { grupo: GrupoNav; item: ItemNav } | null = null
  for (const grupo of grupos) {
    for (const item of grupo.items) {
      const coincide = path === item.ruta || path.startsWith(`${item.ruta}/`)
      if (coincide && (!mejor || item.ruta.length > mejor.item.ruta.length)) mejor = { grupo, item }
    }
  }
  return mejor
}

/** Migas de pan: grupo / sección / detalle. En una pantalla de detalle, la sección es enlace. */
export interface Miga {
  texto: string
  ruta?: string
}

export function migas(grupos: GrupoNav[], path: string, titulo?: string): Miga[] {
  const activo = itemActivo(grupos, path)
  if (!activo) return titulo ? [{ texto: 'Cuenta' }, { texto: titulo }] : []
  const lista: Miga[] = []
  if (activo.grupo.nombre) lista.push({ texto: activo.grupo.nombre })
  const esLaSeccion = path === activo.item.ruta
  lista.push(esLaSeccion || !titulo ? { texto: activo.item.texto } : { texto: activo.item.texto, ruta: activo.item.ruta })
  if (!esLaSeccion && titulo) lista.push({ texto: titulo })
  return lista
}
