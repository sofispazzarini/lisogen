import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { guardarTokens } from '@/api/sesion'
import PantallaAuth from '@/components/PantallaAuth.vue'
import LayoutPublico from '@/layouts/LayoutPublico.vue'
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'
import Inicio from '@/views/publico/Inicio.vue'
import { fetchFalso } from './setup'

beforeEach(async () => {
  setActivePinia(createPinia())
  guardarTokens(null)
  fetchFalso.mockReset()
  await router.push('/')
})

describe('home público', () => {
  it('tiene las seis secciones y la cabecera apunta a ellas', async () => {
    const w = mount(LayoutPublico, { global: { plugins: [router], stubs: { RouterView: true } } })
    await flushPromises()
    const inicio = mount(Inicio, { global: { plugins: [router] } })
    for (const id of ['inicio', 'estudios', 'como-funciona', 'laboratorio', 'sede', 'preguntas']) {
      expect(inicio.find(`section#${id}`).exists()).toBe(true)
    }
    const anclas = w.findAll('nav[aria-label="Principal"] a').map((a) => a.attributes('href'))
    expect(anclas).toEqual(['/#estudios', '/#como-funciona', '/#laboratorio', '/#sede', '/#preguntas'])
    expect(inicio.findAll('.pasos li')).toHaveLength(5)
    expect(inicio.findAll('.faq details')).toHaveLength(7)
    expect(inicio.text()).toContain('Fabry, Pompe, MPS 1, Gaucher y ASMD')
    expect(inicio.find('svg[aria-label="Ilustración de una doble hélice de ADN"] path').attributes('d')).toMatch(/^M/)
  })

  it('el botón dice Ingresar sin sesión e Ir a mi panel con sesión', async () => {
    const w = mount(LayoutPublico, { global: { plugins: [router], stubs: { RouterView: true } } })
    expect(w.get('.entrar').text()).toBe('Ingresar')
    expect(w.get('.entrar').attributes('href')).toBe('/ingresar')

    useAuthStore().usuario = { id: 1, email: 'm@test.com.ar', rol: 'MEDICO_TRATANTE', nombre: 'Lucía', apellido: 'Ferreyra' }
    await flushPromises()
    expect(w.get('.entrar').text()).toBe('Ir a mi panel')
    expect(w.get('.entrar').attributes('href')).toBe('/medico')
  })
})

describe('pantallas de acceso', () => {
  it('las pestañas marcan la pantalla actual y no ofrecen recuperar la contraseña', async () => {
    await router.push('/registro')
    const w = mount(PantallaAuth, { props: { titulo: 'Ingresá a LisoGen', pestanas: true }, global: { plugins: [router] } })
    const pestanas = w.findAll('[role="tab"]')
    expect(pestanas.map((p) => [p.text(), p.attributes('aria-selected')])).toEqual([
      ['Iniciar sesión', 'false'],
      ['Registrarse', 'true'],
    ])
    expect(w.text()).not.toMatch(/olvid/i)
    expect(w.get('a.volver').attributes('href')).toBe('/')
  })

  it('sin pestañas (verificación, primer cambio de contraseña) no muestra la lista', () => {
    const w = mount(PantallaAuth, { props: { titulo: 'Verificá que sos vos' }, global: { plugins: [router] } })
    expect(w.find('[role="tablist"]').exists()).toBe(false)
  })
})
