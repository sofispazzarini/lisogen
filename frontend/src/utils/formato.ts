const ZONA = 'America/Argentina/Buenos_Aires'

const fechaFmt = new Intl.DateTimeFormat('es-AR', { timeZone: ZONA, day: '2-digit', month: '2-digit', year: 'numeric' })
const fechaHoraFmt = new Intl.DateTimeFormat('es-AR', {
  timeZone: ZONA,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
const horaFmt = new Intl.DateTimeFormat('es-AR', { timeZone: ZONA, hour: '2-digit', minute: '2-digit', hour12: false })
const diaLargoFmt = new Intl.DateTimeFormat('es-AR', { timeZone: ZONA, weekday: 'long', day: 'numeric', month: 'long' })

export const fecha = (iso: string | null | undefined): string => (iso ? fechaFmt.format(new Date(iso)) : '—')
export const fechaHora = (iso: string | null | undefined): string => (iso ? fechaHoraFmt.format(new Date(iso)) : '—')
export const hora = (iso: string): string => horaFmt.format(new Date(iso))
export const diaLargo = (iso: string): string => {
  const t = diaLargoFmt.format(new Date(iso))
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** Los montos llegan como string decimal desde la API: se muestran sin pasar por float. */
export function usd(monto: string | number | null | undefined): string {
  if (monto === null || monto === undefined) return '—'
  const [entero = '0', dec = '00'] = String(monto).split('.')
  const negativo = entero.startsWith('-')
  const miles = entero.replace('-', '').replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${negativo ? '-' : ''}USD ${miles},${dec.padEnd(2, '0').slice(0, 2)}`
}

/** Fecha local (YYYY-MM-DD) en hora Argentina, para la agenda de Turnos. */
export function isoDiaAR(d: Date): string {
  const partes = new Intl.DateTimeFormat('en-CA', { timeZone: ZONA, year: 'numeric', month: '2-digit', day: '2-digit' })
  return partes.format(d)
}

export function sumarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.split('-').map(Number)
  const f = new Date(Date.UTC(a ?? 1970, (m ?? 1) - 1, (d ?? 1) + dias, 12))
  return f.toISOString().slice(0, 10)
}

export const titulo = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase().replaceAll('_', ' ')
