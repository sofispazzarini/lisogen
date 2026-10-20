import { onMounted, ref, type Ref } from 'vue'
import { ErrorApi } from '@/api/cliente'

export function mensajeDeError(e: unknown): string {
  if (e instanceof ErrorApi) return e.message
  return 'Ocurrió un error inesperado. Probá de nuevo.'
}

/** Carga datos al montar la vista, con estado de carga y error. */
export function usarCarga<T>(cargar: () => Promise<T>, inmediata = true) {
  const datos = ref<T | null>(null) as Ref<T | null>
  const cargando = ref(false)
  const error = ref<string | null>(null)

  async function recargar(): Promise<void> {
    cargando.value = true
    error.value = null
    try {
      datos.value = await cargar()
    } catch (e) {
      error.value = mensajeDeError(e)
    } finally {
      cargando.value = false
    }
  }

  if (inmediata) onMounted(recargar)
  return { datos, cargando, error, recargar }
}

/** Ejecuta una acción de negocio mostrando el resultado (éxito o el `message` del backend). */
export function usarAccion() {
  const enCurso = ref(false)
  const error = ref<string | null>(null)
  const exito = ref<string | null>(null)

  async function ejecutar<T>(accion: () => Promise<T>, mensajeExito?: string): Promise<T | undefined> {
    enCurso.value = true
    error.value = null
    exito.value = null
    try {
      const r = await accion()
      if (mensajeExito) exito.value = mensajeExito
      return r
    } catch (e) {
      error.value = mensajeDeError(e)
      return undefined
    } finally {
      enCurso.value = false
    }
  }

  return { enCurso, error, exito, ejecutar }
}
