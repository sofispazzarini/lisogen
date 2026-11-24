import { flushPromises, mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import CargarVariantes from '@/views/bioinformatico/CargarVariantes.vue'
import { fetchFalso, respuesta } from './setup'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

it('busca variantes por nomenclatura, permite reintentar la página y conserva la clasificación elegida', async () => {
  const catalogo = Array.from({ length: 21 }, (_, i) => ({
    nomenclatura: `c.${i + 10}A>T`, id_externo: String(i),
  }))
  fetchFalso.mockReset()
  fetchFalso
    .mockResolvedValueOnce(respuesta(200, {
      codigo: 'EST-2026-000002',
      genes: [{ simbolo: 'GAA' }],
      patologias: ['Pompe'],
      tomado_por_mi: true,
    }))
    .mockResolvedValueOnce(respuesta(200, catalogo))
    .mockResolvedValueOnce(respuesta(502, { code: 'APIGEN_NO_DISPONIBLE', message: 'Apigen no está disponible.' }))
    .mockResolvedValueOnce(respuesta(200, catalogo.slice(20)))
    .mockResolvedValueOnce(respuesta(200, catalogo.slice(0, 1)))

  const vista = mount(CargarVariantes, { props: { id: '2' } })
  const boton = (texto: string) => vista.findAll('button').find((b) => b.text() === texto)!
  await flushPromises()
  await boton('GAA').trigger('click')
  await flushPromises()
  expect(vista.findAll('select option')).toHaveLength(21)

  await boton('Siguiente').trigger('click')
  await flushPromises()
  expect(vista.text()).toContain('Apigen no está disponible.')
  await boton('Reintentar').trigger('click')
  await flushPromises()
  const urls = fetchFalso.mock.calls.map(([req]) => new URL((req as Request).url))
  expect(urls[2]!.searchParams.get('offset')).toBe('20')
  expect(urls[3]!.href).toBe(urls[2]!.href)

  await vista.get('input[type="search"]').setValue('c.10')
  await vista.get('form').trigger('submit')
  await flushPromises()
  const busqueda = new URL((fetchFalso.mock.lastCall![0] as Request).url)
  expect(busqueda.searchParams.get('q')).toBe('c.10')
  expect(busqueda.searchParams.get('offset')).toBe('0')

  await vista.get('select').setValue('c.10A>T')
  expect(boton('Agregar Variante').attributes('disabled')).toBeDefined()
  await vista.get('input[value="BENIGNA"]').setValue(true)
  await boton('Agregar Variante').trigger('click')
  expect(vista.text()).toContain('c.10A>T · Benigna')
  expect(vista.text()).toContain('Resultado previsto: Negativo')
  vista.unmount()
})
