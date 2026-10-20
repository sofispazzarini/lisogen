import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import { guardarTokens, obtenerTokens } from '@/api/sesion'

export type Rol = Esquemas['RolUsuario']
export type Usuario = Esquemas['UsuarioSalida']
type Ingreso = Esquemas['IngresoSalida']

export const INICIO_POR_ROL: Record<Rol, string> = {
  MEDICO_TRATANTE: '/medico',
  PACIENTE: '/paciente',
  ADMINISTRATIVO: '/administrativo',
  TRANSPORTISTA: '/transportista',
  BIOINFORMATICO: '/bioinformatico',
  GERENTE_MEDICO: '/gerente',
}

export const NOMBRE_ROL: Record<Rol, string> = {
  MEDICO_TRATANTE: 'Médico Tratante',
  PACIENTE: 'Paciente',
  ADMINISTRATIVO: 'Administrativo del Laboratorio',
  TRANSPORTISTA: 'Transportista',
  BIOINFORMATICO: 'Bioinformático',
  GERENTE_MEDICO: 'Gerente Médico',
}

/** E7: ingreso → (código por dispositivo nuevo) → (cambio de contraseña provisoria) → sesión. */
export const useAuthStore = defineStore('auth', () => {
  const usuario = ref<Usuario | null>(null)
  const desafio = ref<string | null>(null)
  const paso = ref<Ingreso['estado'] | null>(null)

  const autenticado = computed(() => usuario.value !== null)
  const rol = computed<Rol | null>(() => usuario.value?.rol ?? null)
  const inicio = computed(() => (rol.value ? INICIO_POR_ROL[rol.value] : '/ingresar'))

  function aplicar(r: Ingreso): Ingreso['estado'] {
    paso.value = r.estado
    if (r.estado === 'OK' && r.access_token && r.refresh_token && r.usuario) {
      guardarTokens({ access: r.access_token, refresh: r.refresh_token })
      usuario.value = r.usuario
      desafio.value = null
    } else {
      desafio.value = r.desafio_token ?? null
    }
    return r.estado
  }

  async function ingresar(email: string, password: string) {
    return aplicar(await ok(api.POST('/auth/login', { body: { email, password } })))
  }

  async function verificar(codigo: string) {
    if (!desafio.value) throw new Error('No hay un ingreso en curso')
    return aplicar(await ok(api.POST('/auth/verificar', { body: { desafio_token: desafio.value, codigo } })))
  }

  async function cambiarPassword(passwordNueva: string, passwordActual?: string) {
    const body = desafio.value
      ? { desafio_token: desafio.value, password_nueva: passwordNueva }
      : { password_actual: passwordActual ?? '', password_nueva: passwordNueva }
    return aplicar(await ok(api.POST('/auth/cambiar-password', { body })))
  }

  /** Recupera la sesión guardada al recargar la página. */
  async function restaurar(): Promise<void> {
    if (usuario.value || !obtenerTokens()) return
    try {
      usuario.value = await ok(api.GET('/auth/yo'))
    } catch {
      salir()
    }
  }

  function salir(): void {
    guardarTokens(null)
    usuario.value = null
    desafio.value = null
    paso.value = null
  }

  return { usuario, desafio, paso, autenticado, rol, inicio, ingresar, verificar, cambiarPassword, restaurar, salir }
})
