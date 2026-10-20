import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { api, ErrorApi, ok } from '@/api/cliente'
import { guardarTokens, obtenerTokens } from '@/api/sesion'
import { useAuthStore } from '@/stores/auth'
import { fetchFalso, respuesta } from './setup'

const USUARIO = { id: 7, email: 'paciente@lisogen-demo.com.ar', rol: 'PACIENTE', nombre: 'Martín', apellido: 'Ibarra' }

beforeEach(() => {
  setActivePinia(createPinia())
  guardarTokens(null)
  sessionStorage.clear()
  fetchFalso.mockReset()
})

describe('ingreso (E7)', () => {
  it('dispositivo nuevo → código → cambio de contraseña → sesión', async () => {
    const auth = useAuthStore()
    fetchFalso
      .mockResolvedValueOnce(respuesta(200, { estado: 'VERIFICACION_REQUERIDA', desafio_token: 'd1' }))
      .mockResolvedValueOnce(respuesta(200, { estado: 'CAMBIO_PASSWORD_REQUERIDO', desafio_token: 'd2' }))
      .mockResolvedValueOnce(respuesta(200, { estado: 'OK', access_token: 'a', refresh_token: 'r', usuario: USUARIO }))

    expect(await auth.ingresar('paciente@lisogen-demo.com.ar', 'Provisoria1')).toBe('VERIFICACION_REQUERIDA')
    expect(auth.desafio).toBe('d1')
    expect(auth.autenticado).toBe(false)

    expect(await auth.verificar('123456')).toBe('CAMBIO_PASSWORD_REQUERIDO')
    expect(auth.desafio).toBe('d2')

    expect(await auth.cambiarPassword('Clave-nueva-2026')).toBe('OK')
    expect(auth.autenticado).toBe(true)
    expect(auth.rol).toBe('PACIENTE')
    expect(auth.inicio).toBe('/paciente')
    expect(auth.desafio).toBeNull()
    expect(obtenerTokens()).toEqual({ access: 'a', refresh: 'r' })

    const verificacion = fetchFalso.mock.calls[1]![0] as Request
    expect(verificacion.url).toMatch(/\/auth\/verificar$/)
    expect(verificacion.headers.get('X-Device-Id')).toBeTruthy()
  })

  it('las credenciales inválidas llegan como ErrorApi con el mensaje del backend', async () => {
    fetchFalso.mockResolvedValueOnce(
      respuesta(401, { code: 'CREDENCIALES_INVALIDAS', message: 'El mail o la contraseña no son correctos.' }),
    )
    await expect(useAuthStore().ingresar('x@y.com', 'mala')).rejects.toMatchObject({
      code: 'CREDENCIALES_INVALIDAS',
      status: 401,
      message: 'El mail o la contraseña no son correctos.',
    })
  })

  it('salir borra la sesión', () => {
    guardarTokens({ access: 'a', refresh: 'r' })
    const auth = useAuthStore()
    auth.salir()
    expect(obtenerTokens()).toBeNull()
    expect(sessionStorage.getItem('lisogen.tokens')).toBeNull()
  })
})

describe('cliente HTTP', () => {
  it('manda el access token y renueva una vez ante un 401', async () => {
    guardarTokens({ access: 'viejo', refresh: 'r1' })
    fetchFalso
      .mockResolvedValueOnce(respuesta(401, { code: 'SESION_VENCIDA', message: 'Tu sesión venció.' }))
      .mockResolvedValueOnce(respuesta(200, { estado: 'OK', access_token: 'nuevo', refresh_token: 'r2', usuario: USUARIO }))
      .mockResolvedValueOnce(respuesta(200, []))

    const avisos = await ok(api.GET('/avisos'))
    expect(avisos).toEqual([])
    expect((fetchFalso.mock.calls[0]![0] as Request).headers.get('Authorization')).toBe('Bearer viejo')
    expect(fetchFalso.mock.calls[1]![0]).toMatch(/\/auth\/refresh$/)
    expect((fetchFalso.mock.calls[2]![0] as Request).headers.get('Authorization')).toBe('Bearer nuevo')
    expect(obtenerTokens()).toEqual({ access: 'nuevo', refresh: 'r2' })
  })

  it('si no puede renovar, cierra la sesión', async () => {
    guardarTokens({ access: 'viejo', refresh: 'vencido' })
    fetchFalso
      .mockResolvedValueOnce(respuesta(401, { code: 'SESION_VENCIDA', message: 'Tu sesión venció.' }))
      .mockResolvedValueOnce(respuesta(401, { code: 'SESION_VENCIDA', message: 'Tu sesión venció.' }))
    await expect(ok(api.GET('/avisos'))).rejects.toBeInstanceOf(ErrorApi)
    expect(obtenerTokens()).toBeNull()
  })

  it('traduce la falta de conexión', async () => {
    fetchFalso.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(ok(api.GET('/auth/especialidades'))).rejects.toMatchObject({ code: 'SIN_CONEXION', status: 0 })
  })

  it('expone los campos inválidos de un 422', async () => {
    fetchFalso.mockResolvedValueOnce(
      respuesta(422, { code: 'DATOS_INVALIDOS', message: 'Revisá estos datos: dni.', campos: ['dni'] }),
    )
    await expect(ok(api.GET('/auth/especialidades'))).rejects.toMatchObject({ campos: ['dni'] })
  })
})
