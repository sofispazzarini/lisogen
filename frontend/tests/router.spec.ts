import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { guardarTokens } from '@/api/sesion'
import { router, routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { NAVEGACION } from '@/layouts/navegacion'
import { fetchFalso, respuesta } from './setup'

function conRol(rol: string): void {
  guardarTokens({ access: 'a', refresh: 'r' })
  fetchFalso.mockResolvedValue(respuesta(200, { id: 1, email: 'x@y.com', rol, nombre: 'X', apellido: 'Y' }))
}

beforeEach(async () => {
  setActivePinia(createPinia())
  guardarTokens(null)
  fetchFalso.mockReset()
  useAuthStore().salir()
  await router.push('/ingresar')
})

describe('guardas por rol', () => {
  it('sin sesión, manda al ingreso recordando la ruta', async () => {
    await router.push('/medico/pacientes')
    expect(router.currentRoute.value.name).toBe('ingresar')
    expect(router.currentRoute.value.query.volver).toBe('/medico/pacientes')
  })

  it('con sesión, cada rol entra sólo a su sección', async () => {
    conRol('PACIENTE')
    await router.push('/paciente/chatbot')
    expect(router.currentRoute.value.name).toBe('paciente-chatbot')
    await router.push('/administrativo/lotes')
    expect(router.currentRoute.value.path).toBe('/paciente')
  })

  it('el ingreso con sesión iniciada lleva al inicio del rol', async () => {
    conRol('TRANSPORTISTA')
    await router.push('/transportista')
    await router.push('/ingresar')
    expect(router.currentRoute.value.path).toBe('/transportista')
  })

  it('el registro de profesionales es público', async () => {
    await router.push('/registro')
    expect(router.currentRoute.value.name).toBe('registro')
  })
})

describe('navegación', () => {
  it('cada ítem del menú de cada rol tiene una ruta definida', () => {
    const resueltas = router.getRoutes().map((r) => r.path)
    for (const items of Object.values(NAVEGACION)) {
      for (const i of items) expect(resueltas).toContain(i.ruta)
    }
    expect(routes.length).toBeGreaterThan(5)
  })
})
