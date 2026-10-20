import type { Router } from 'vue-router'

/** Avanza al paso que pide el backend en el ingreso (E7). */
export async function seguirIngreso(router: Router, estado: string | undefined, destino: string): Promise<void> {
  if (estado === 'VERIFICACION_REQUERIDA') await router.push({ name: 'verificar', query: { volver: destino } })
  else if (estado === 'CAMBIO_PASSWORD_REQUERIDO') await router.push({ name: 'cambiar-password', query: { volver: destino } })
  else if (estado === 'OK') await router.push(destino)
}

export function destinoDe(query: Record<string, unknown>, porDefecto: string): string {
  const v = query.volver
  return typeof v === 'string' && v.startsWith('/') && !v.startsWith('//') ? v : porDefecto
}
