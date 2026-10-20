import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { Esquemas } from '@/api/cliente'
import BadgeEstado from '@/components/BadgeEstado.vue'
import LineaPasos from '@/components/LineaPasos.vue'
import ResultadoVista from '@/components/ResultadoVista.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'

function estudio(cambios: Partial<Esquemas['EstudioResumen']> = {}): Esquemas['EstudioResumen'] {
  return {
    id: 1,
    codigo: 'EST-2026-000001',
    tipo: 'EXOMA',
    estado: 'POR_PAGAR',
    estado_etiqueta: 'Por Pagar',
    urgente: false,
    created_at: '2026-10-20T12:00:00Z',
    paciente: { id: 1, nombre_completo: 'Martín Ibarra' },
    medico_tratante: { id: 2, nombre_completo: 'Lucía Ferreyra' },
    patologias: ['Fabry'],
    version: 3,
    ...cambios,
  }
}

describe('BadgeEstado', () => {
  it('muestra la etiqueta del LEL con el tono del Estado', () => {
    const w = mount(BadgeEstado, { props: { estado: 'RECHAZADO' } })
    expect(w.text()).toBe('Rechazado')
    expect(w.classes()).toContain('badge--error')
  })
})

describe('LineaPasos', () => {
  it('resalta el paso actual con el detalle del Estado', () => {
    const w = mount(LineaPasos, { props: { estado: 'EN_CAMINO_LAB_CENTRAL' } })
    const actual = w.find('[aria-current="step"]')
    expect(actual.text()).toContain('Muestra')
    expect(actual.text()).toContain('En camino al Laboratorio Central')
    expect(w.findAll('.paso--hecho')).toHaveLength(3)
  })
})

describe('TablaEstudios', () => {
  it('lista Estudios con badge de Estado y de Urgente', () => {
    const w = mount(TablaEstudios, {
      props: { estudios: [estudio(), estudio({ id: 2, codigo: 'EST-2026-000002', urgente: true, estado: 'EN_ANALISIS' })], enlace: (e) => `/x/${e.id}` },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.findAll('tbody tr')).toHaveLength(2)
    expect(w.findAll('.urgente')).toHaveLength(1)
    expect(w.findAllComponents(RouterLinkStub)[1]!.props('to')).toBe('/x/2')
    expect(w.text()).toContain('Martín Ibarra')
  })

  it('muestra el mensaje de vacío', () => {
    const w = mount(TablaEstudios, { props: { estudios: [], vacio: 'Nada por acá' } })
    expect(w.text()).toContain('Nada por acá')
  })
})

describe('ResultadoVista', () => {
  it('muestra el tipo, las Variantes y el enlace firmado al PDF', () => {
    const w = mount(ResultadoVista, {
      props: {
        resultado: {
          tipo: 'POSITIVO',
          confirmado_at: '2026-10-20T15:00:00Z',
          pdf_url: 'https://minio/firmada',
          variantes: [{ gen: 'GLA', nomenclatura: 'c.644A>G', clasificacion: 'PATOGENICA', hallazgo_secundario: false }],
        },
      },
    })
    expect(w.text()).toContain('Positivo')
    expect(w.text()).toContain('GLA')
    expect(w.find('a').attributes('href')).toBe('https://minio/firmada')
    expect(w.find('a').attributes('rel')).toBe('noopener')
  })
})
