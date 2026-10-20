import { describe, expect, it } from 'vitest'
import { ETIQUETA, PASOS_EXOMA, TONO, accionPaciente, pasos, type EstadoEstudio } from '@/utils/estados'
import { destinoDe } from '@/utils/ingreso'
import { isoDiaAR, sumarDias, titulo, usd } from '@/utils/formato'

const TODOS = Object.keys(ETIQUETA) as EstadoEstudio[]

describe('estados del Estudio', () => {
  it('tiene etiqueta y tono para los 15 Estados del schema', () => {
    expect(TODOS).toHaveLength(15)
    for (const e of TODOS) {
      expect(ETIQUETA[e]).toBeTruthy()
      expect(TONO[e]).toBeTruthy()
    }
  })

  it('cada Estado pertenece a un único paso de la línea del exoma', () => {
    for (const e of TODOS) {
      expect(PASOS_EXOMA.filter((p) => p.estados.includes(e))).toHaveLength(1)
    }
  })

  it('marca los pasos hechos, el actual y los pendientes', () => {
    const l = pasos('TURNO_SACADO')
    expect(l.map((p) => p.estado)).toEqual(['hecho', 'hecho', 'actual', 'pendiente', 'pendiente', 'pendiente', 'pendiente'])
    expect(pasos('FINALIZADO').every((p) => p.estado === 'hecho')).toBe(true)
    expect(pasos('RECHAZADO')[1]!.estado).toBe('actual')
  })

  it('el Reanálisis no pasa por Turno ni logística', () => {
    expect(pasos('EN_ANALISIS_BIOINFORMATICA', 'REANALISIS').map((p) => p.paso.clave)).toEqual(['alta', 'analisis', 'resultado'])
  })

  it('sugiere la acción del Paciente según el Estado', () => {
    expect(accionPaciente('POR_PAGAR')?.ruta).toBe('pagar')
    expect(accionPaciente('RECHAZADO')?.ruta).toBe('reautorizacion')
    expect(accionPaciente('AUTORIZADO')?.ruta).toBe('turno')
    expect(accionPaciente('FINALIZADO')?.ruta).toBe('resultado')
    expect(accionPaciente('EN_VIAJE_COREA')).toBeNull()
  })
})

describe('formatos', () => {
  it('formatea USD sin pasar por float', () => {
    expect(usd('560.00')).toBe('USD 560,00')
    expect(usd('1234567.5')).toBe('USD 1.234.567,50')
    expect(usd('0.10')).toBe('USD 0,10')
    expect(usd(null)).toBe('—')
  })

  it('suma días en fechas ISO', () => {
    expect(sumarDias('2026-12-31', 1)).toBe('2027-01-01')
    expect(sumarDias('2026-03-01', -1)).toBe('2026-02-28')
  })

  it('usa la fecha de Argentina', () => {
    // 02:00 UTC del 20/10 es 23:00 del 19/10 en Argentina
    expect(isoDiaAR(new Date('2026-10-20T02:00:00Z'))).toBe('2026-10-19')
  })

  it('titula enums', () => {
    expect(titulo('NO_CONCLUYENTE')).toBe('No concluyente')
  })

  it('sólo redirige a rutas internas después del ingreso', () => {
    expect(destinoDe({ volver: '/paciente/estudios/3' }, '/x')).toBe('/paciente/estudios/3')
    expect(destinoDe({ volver: 'https://malicioso.com' }, '/x')).toBe('/x')
    expect(destinoDe({ volver: '//malicioso.com' }, '/x')).toBe('/x')
    expect(destinoDe({}, '/x')).toBe('/x')
  })
})
