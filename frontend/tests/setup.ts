import { vi } from 'vitest'

/** openapi-fetch toma `fetch` al crear el cliente: se reemplaza antes de importar los módulos. */
export const fetchFalso = vi.fn<typeof fetch>()
globalThis.fetch = fetchFalso

export function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

// jsdom no implementa scrollTo (lo usa el scrollBehavior del router).
window.scrollTo = () => {}
