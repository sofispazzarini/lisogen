import type { Esquemas } from '@/api/cliente'

export type EstadoEstudio = Esquemas['EstadoEstudio']
export type TipoEstudio = Esquemas['TipoEstudio']

/** Etiquetas del LEL (mismas que `domain/estados.py`). */
export const ETIQUETA: Record<EstadoEstudio, string> = {
  CREADO: 'Creado',
  POR_PAGAR: 'Por Pagar',
  PENDIENTE_AUTORIZACION: 'Pendiente de Autorización',
  RECHAZADO: 'Rechazado',
  PAGADO: 'Pagado',
  AUTORIZADO: 'Autorizado',
  TURNO_SACADO: 'Turno Sacado',
  LISTO_PARA_RETIRAR: 'Listo para Retirar',
  EN_CAMINO_LAB_CENTRAL: 'En camino al Laboratorio Central',
  EN_LAB_CENTRAL: 'En Laboratorio Central',
  EN_ESPERA_RETIRO: 'En Espera de Retiro',
  EN_VIAJE_COREA: 'En viaje a Corea',
  EN_ANALISIS_BIOINFORMATICA: 'En análisis por bioinformática',
  EN_ANALISIS: 'En Análisis',
  FINALIZADO: 'Finalizado',
}

export type Tono = 'neutro' | 'accion' | 'alerta' | 'error' | 'progreso' | 'exito'

/** Color del badge: qué tan cerca está de requerir una acción o de terminar. */
export const TONO: Record<EstadoEstudio, Tono> = {
  CREADO: 'neutro',
  POR_PAGAR: 'accion',
  PENDIENTE_AUTORIZACION: 'alerta',
  RECHAZADO: 'error',
  PAGADO: 'accion',
  AUTORIZADO: 'accion',
  TURNO_SACADO: 'progreso',
  LISTO_PARA_RETIRAR: 'progreso',
  EN_CAMINO_LAB_CENTRAL: 'progreso',
  EN_LAB_CENTRAL: 'progreso',
  EN_ESPERA_RETIRO: 'progreso',
  EN_VIAJE_COREA: 'progreso',
  EN_ANALISIS_BIOINFORMATICA: 'progreso',
  EN_ANALISIS: 'progreso',
  FINALIZADO: 'exito',
}

export interface Paso {
  clave: string
  etiqueta: string
  estados: EstadoEstudio[]
}

/** Línea de pasos que ve el Paciente (agrupa Estados del camino principal). */
export const PASOS_EXOMA: Paso[] = [
  { clave: 'alta', etiqueta: 'Alta', estados: ['CREADO'] },
  { clave: 'pago', etiqueta: 'Pago o Autorización', estados: ['POR_PAGAR', 'PENDIENTE_AUTORIZACION', 'RECHAZADO'] },
  { clave: 'turno', etiqueta: 'Turno', estados: ['PAGADO', 'AUTORIZADO', 'TURNO_SACADO'] },
  { clave: 'muestra', etiqueta: 'Muestra', estados: ['LISTO_PARA_RETIRAR', 'EN_CAMINO_LAB_CENTRAL', 'EN_LAB_CENTRAL'] },
  { clave: 'corea', etiqueta: 'Secuenciación', estados: ['EN_ESPERA_RETIRO', 'EN_VIAJE_COREA'] },
  { clave: 'analisis', etiqueta: 'Análisis', estados: ['EN_ANALISIS_BIOINFORMATICA', 'EN_ANALISIS'] },
  { clave: 'resultado', etiqueta: 'Resultado', estados: ['FINALIZADO'] },
]

export const PASOS_REANALISIS: Paso[] = [
  { clave: 'alta', etiqueta: 'Alta', estados: ['CREADO'] },
  { clave: 'analisis', etiqueta: 'Análisis', estados: ['EN_ANALISIS_BIOINFORMATICA', 'EN_ANALISIS'] },
  { clave: 'resultado', etiqueta: 'Resultado', estados: ['FINALIZADO'] },
]

export type EstadoPaso = 'hecho' | 'actual' | 'pendiente'

export function pasos(estado: EstadoEstudio, tipo: TipoEstudio = 'EXOMA'): { paso: Paso; estado: EstadoPaso }[] {
  const lista = tipo === 'REANALISIS' ? PASOS_REANALISIS : PASOS_EXOMA
  const actual = lista.findIndex((p) => p.estados.includes(estado))
  return lista.map((paso, i) => ({
    paso,
    estado: estado === 'FINALIZADO' || i < actual ? 'hecho' : i === actual ? 'actual' : 'pendiente',
  }))
}

/** Qué puede hacer el Paciente ahora con su Estudio (para la llamada a la acción). */
export function accionPaciente(estado: EstadoEstudio): { texto: string; ruta: string } | null {
  switch (estado) {
    case 'POR_PAGAR':
      return { texto: 'Pagar el Presupuesto', ruta: 'pagar' }
    case 'PENDIENTE_AUTORIZACION':
      return { texto: 'Ver el Presupuesto', ruta: 'pagar' }
    case 'RECHAZADO':
      return { texto: 'Solicitar reautorización', ruta: 'reautorizacion' }
    case 'PAGADO':
    case 'AUTORIZADO':
      return { texto: 'Sacar Turno', ruta: 'turno' }
    case 'TURNO_SACADO':
      return { texto: 'Ver mi Turno', ruta: 'mi-turno' }
    case 'FINALIZADO':
      return { texto: 'Ver el Resultado', ruta: 'resultado' }
    default:
      return null
  }
}
