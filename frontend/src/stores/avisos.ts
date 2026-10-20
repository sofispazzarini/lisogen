import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'

type Aviso = Esquemas['Aviso']

const CADA_MS = 30_000

/** Bandeja de Avisos (notificaciones de la app): se refresca cada 30 segundos mientras hay sesión. */
export const useAvisosStore = defineStore('avisos', () => {
  const avisos = ref<Aviso[]>([])
  let temporizador: ReturnType<typeof setInterval> | null = null

  const noLeidos = computed(() => avisos.value.filter((a) => !a.leida).length)

  async function cargar(): Promise<void> {
    try {
      avisos.value = await ok(api.GET('/avisos'))
    } catch {
      /* sin conexión: se reintenta en el próximo ciclo */
    }
  }

  async function marcarLeido(id: number): Promise<void> {
    await ok(api.POST('/avisos/{aviso_id}/leido', { params: { path: { aviso_id: id } } }))
    const a = avisos.value.find((x) => x.id === id)
    if (a) a.leida = true
  }

  async function marcarTodos(): Promise<void> {
    await ok(api.POST('/avisos/leidos'))
    avisos.value.forEach((a) => (a.leida = true))
  }

  function iniciar(): void {
    detener()
    void cargar()
    temporizador = setInterval(() => void cargar(), CADA_MS)
  }

  function detener(): void {
    if (temporizador) clearInterval(temporizador)
    temporizador = null
    avisos.value = []
  }

  return { avisos, noLeidos, cargar, marcarLeido, marcarTodos, iniciar, detener }
})
