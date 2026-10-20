/**
 * Tokens de la sesión y identificador del dispositivo.
 * SUPUESTO F1: los tokens viven en sessionStorage (se borran al cerrar la pestaña). El id de dispositivo
 * persiste en localStorage para que el mismo navegador no pida código de verificación cada vez (E7).
 */

const CLAVE_TOKENS = 'lisogen.tokens'
const CLAVE_DISPOSITIVO = 'lisogen.dispositivo'

export interface Tokens {
  access: string
  refresh: string
}

let memoria: Tokens | null = null

function leer(storage: Storage | undefined, clave: string): string | null {
  try {
    return storage?.getItem(clave) ?? null
  } catch {
    return null
  }
}

function escribir(storage: Storage | undefined, clave: string, valor: string | null): void {
  try {
    if (valor === null) storage?.removeItem(clave)
    else storage?.setItem(clave, valor)
  } catch {
    /* almacenamiento bloqueado: la sesión queda sólo en memoria */
  }
}

const sesionStorage = (): Storage | undefined => (typeof sessionStorage === 'undefined' ? undefined : sessionStorage)
const localStorage_ = (): Storage | undefined => (typeof localStorage === 'undefined' ? undefined : localStorage)

export function obtenerTokens(): Tokens | null {
  if (memoria) return memoria
  const crudo = leer(sesionStorage(), CLAVE_TOKENS)
  if (!crudo) return null
  try {
    memoria = JSON.parse(crudo) as Tokens
    return memoria
  } catch {
    return null
  }
}

export function guardarTokens(tokens: Tokens | null): void {
  memoria = tokens
  escribir(sesionStorage(), CLAVE_TOKENS, tokens ? JSON.stringify(tokens) : null)
}

export function idDispositivo(): string {
  let id = leer(localStorage_(), CLAVE_DISPOSITIVO)
  if (!id) {
    id = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : String(Math.random()).slice(2)
    escribir(localStorage_(), CLAVE_DISPOSITIVO, id)
  }
  return id
}
