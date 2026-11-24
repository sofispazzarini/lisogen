import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import FormCambioPassword from '@/components/FormCambioPassword.vue'
import MenuCuenta from '@/components/MenuCuenta.vue'
import PanelLateral from '@/components/PanelLateral.vue'
import { GRUPOS, NAVEGACION, itemActivo, migas } from '@/layouts/navegacion'
import { fetchFalso, respuesta } from './setup'

beforeEach(() => {
  setActivePinia(createPinia())
  fetchFalso.mockReset()
  document.body.innerHTML = ''
})

describe('navegación agrupada', () => {
  it('la lista plana conserva todas las secciones de cada grupo', () => {
    expect(NAVEGACION.ADMINISTRATIVO.map((i) => i.texto)).toEqual([
      'Tablero',
      'Emitir presupuesto',
      'Autorizaciones',
      'Registro financiero',
      'Nueva extracción',
      'Seguir muestra',
      'Datos crudos',
      'Lotes y FedEx',
    ])
  })

  it('el ítem activo es el de ruta más larga que coincide', () => {
    expect(itemActivo(GRUPOS.MEDICO_TRATANTE, '/medico/pacientes/3')?.item.texto).toBe('Pacientes')
    expect(itemActivo(GRUPOS.MEDICO_TRATANTE, '/medico/pacientes/nuevo')?.item.texto).toBe('Alta Paciente')
    expect(itemActivo(GRUPOS.MEDICO_TRATANTE, '/medico/estudios/2')?.item.texto).toBe('Mis Estudios')
    expect(itemActivo(GRUPOS.MEDICO_TRATANTE, '/otra')).toBeNull()
  })

  it('migas: grupo / sección / detalle, con la sección como enlace en un detalle', () => {
    expect(migas(GRUPOS.ADMINISTRATIVO, '/administrativo/lotes')).toEqual([{ texto: 'Envíos' }, { texto: 'Lotes y FedEx' }])
    expect(migas(GRUPOS.MEDICO_TRATANTE, '/medico/pacientes/3', 'Ficha del Paciente')).toEqual([
      { texto: 'Pacientes' },
      { texto: 'Pacientes', ruta: '/medico/pacientes' },
      { texto: 'Ficha del Paciente' },
    ])
    expect(migas(GRUPOS.PACIENTE, '/paciente')).toEqual([{ texto: 'Mis Estudios' }])
    expect(migas(GRUPOS.PACIENTE, '/cuenta/password', 'Cambiar contraseña')).toEqual([
      { texto: 'Cuenta' },
      { texto: 'Cambiar contraseña' },
    ])
  })
})

describe('MenuCuenta', () => {
  it('muestra las iniciales y abre las acciones de la cuenta', async () => {
    const w = mount(MenuCuenta, { props: { nombre: 'Carla', apellido: 'Soria' }, attachTo: document.body })
    const avatar = w.get('button[aria-haspopup]')
    expect(avatar.text()).toBe('CS')
    expect(avatar.attributes('aria-label')).toBe('Cuenta de Carla Soria')
    expect(w.find('[role="menu"]').exists()).toBe(false)

    await avatar.trigger('click')
    expect(avatar.attributes('aria-expanded')).toBe('true')
    await w.findAll('[role="menuitem"]')[0]!.trigger('click')
    expect(w.emitted('perfil')).toHaveLength(1)
    expect(w.find('[role="menu"]').exists()).toBe(false)

    await avatar.trigger('click')
    await w.findAll('[role="menuitem"]')[1]!.trigger('click')
    expect(w.emitted('salir')).toHaveLength(1)
    w.unmount()
  })

  it('se cierra con Escape y al tocar afuera', async () => {
    const w = mount(MenuCuenta, { props: { nombre: 'Carla', apellido: 'Soria' }, attachTo: document.body })
    await w.get('button[aria-haspopup]').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(w.find('[role="menu"]').exists()).toBe(false)

    await w.get('button[aria-haspopup]').trigger('click')
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(w.find('[role="menu"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('PanelLateral', () => {
  it('se abre, se cierra con Escape y devuelve el foco', async () => {
    const disparador = document.createElement('button')
    document.body.appendChild(disparador)
    disparador.focus()
    const w = mount(PanelLateral, {
      props: { titulo: 'Mi perfil', modelValue: false, 'onUpdate:modelValue': (v: boolean) => w.setProps({ modelValue: v }) },
      slots: { default: '<p>Contenido</p>' },
      attachTo: document.body,
    })
    const dialogo = () => document.body.querySelector('[role="dialog"]')!
    expect(dialogo().classList.contains('abierto')).toBe(false)

    await w.setProps({ modelValue: true })
    await nextTick()
    expect(dialogo().classList.contains('abierto')).toBe(true)
    expect(dialogo().getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement?.textContent).toBe('Cerrar')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    await nextTick()
    expect(dialogo().classList.contains('abierto')).toBe(false)
    expect(document.activeElement).toBe(disparador)
    w.unmount()
  })
})

describe('FormCambioPassword', () => {
  it('pide la contraseña actual salvo en el primer ingreso y valida la nueva', async () => {
    expect(mount(FormCambioPassword).findAll('input')).toHaveLength(3)
    const w = mount(FormCambioPassword, { props: { obligatorio: true } })
    const [nueva, repetida] = w.findAll('input')
    const guardar = w.get('button[type="submit"]')

    await nueva!.setValue('corta1')
    await repetida!.setValue('corta1')
    expect(guardar.attributes('disabled')).toBeDefined()

    await nueva!.setValue('UnaClaveSegura2026')
    await repetida!.setValue('OtraClave2026')
    expect(w.text()).toContain('No coinciden.')
    expect(guardar.attributes('disabled')).toBeDefined()

    await repetida!.setValue('UnaClaveSegura2026')
    expect(guardar.attributes('disabled')).toBeUndefined()
  })

  it('avisa cuando se cambió', async () => {
    fetchFalso.mockResolvedValueOnce(
      respuesta(200, {
        estado: 'OK',
        access_token: 'a',
        refresh_token: 'r',
        usuario: { id: 1, email: 'x@test.com.ar', rol: 'PACIENTE', nombre: 'A', apellido: 'B' },
      }),
    )
    const w = mount(FormCambioPassword)
    const [actual, nueva, repetida] = w.findAll('input')
    await actual!.setValue('Anterior2025')
    await nueva!.setValue('UnaClaveSegura2026')
    await repetida!.setValue('UnaClaveSegura2026')
    await w.get('form').trigger('submit')
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    expect(w.emitted('cambiada')).toHaveLength(1)
    expect(w.text()).toContain('Listo, cambiaste tu contraseña.')
  })
})
