import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import LayoutRol from '@/layouts/LayoutRol.vue'
import { INICIO_POR_ROL, useAuthStore, type Rol } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    rol?: Rol
    publica?: boolean
  }
}

const vistas = import.meta.glob('../views/**/*.vue')

/** Carga diferida de la vista; falla al construir el router si la vista no existe. */
function v(ruta: string) {
  const cargar = vistas[`../views/${ruta}.vue`]
  if (!cargar) throw new Error(`No existe la vista ${ruta}`)
  return cargar
}

function seccion(path: string, rol: Rol, hijos: RouteRecordRaw[]): RouteRecordRaw {
  return { path, component: LayoutRol, meta: { rol }, children: hijos.map((h) => ({ ...h, meta: { rol, ...h.meta } })) }
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/ingresar' },
  // E7 y E1/E15/E26/E29
  { path: '/ingresar', name: 'ingresar', component: v('auth/Login'), meta: { publica: true } },
  { path: '/verificar', name: 'verificar', component: v('auth/Verificacion'), meta: { publica: true } },
  { path: '/cambiar-password', name: 'cambiar-password', component: v('auth/CambioPassword'), meta: { publica: true } },
  { path: '/registro', name: 'registro', component: v('auth/RegistroProfesional'), meta: { publica: true } },
  {
    path: '/cuenta',
    component: LayoutRol,
    children: [{ path: 'password', name: 'cuenta-password', component: v('auth/CambioPassword') }],
  },

  seccion('/medico', 'MEDICO_TRATANTE', [
    { path: '', name: 'medico', component: v('medico/MisEstudios') },
    { path: 'pacientes', name: 'medico-pacientes', component: v('medico/Pacientes') },
    { path: 'pacientes/nuevo', name: 'medico-alta-paciente', component: v('medico/AltaPaciente') },
    { path: 'pacientes/:id(\\d+)', name: 'medico-ficha', component: v('medico/FichaPaciente'), props: true },
    { path: 'estudios/nuevo', name: 'medico-alta-estudio', component: v('medico/AltaEstudio') },
    { path: 'estudios/:id(\\d+)', name: 'medico-estudio', component: v('medico/DetalleEstudio'), props: true },
    { path: 'cupones', name: 'medico-cupones', component: v('medico/MisCupones') },
  ]),

  seccion('/paciente', 'PACIENTE', [
    { path: '', name: 'paciente', component: v('paciente/MisEstudios') },
    { path: 'estudios/:id(\\d+)', name: 'paciente-estudio', component: v('paciente/DetalleEstudio'), props: true },
    { path: 'estudios/:id(\\d+)/pagar', name: 'paciente-pagar', component: v('paciente/Pagar'), props: true },
    { path: 'estudios/:id(\\d+)/reautorizacion', name: 'paciente-reautorizacion', component: v('paciente/Reautorizacion'), props: true },
    { path: 'estudios/:id(\\d+)/turno', name: 'paciente-turno', component: v('paciente/SacarTurno'), props: true },
    { path: 'estudios/:id(\\d+)/mi-turno', name: 'paciente-mi-turno', component: v('paciente/MiTurno'), props: true },
    { path: 'estudios/:id(\\d+)/resultado', name: 'paciente-resultado', component: v('paciente/Resultado'), props: true },
    { path: 'chatbot', name: 'paciente-chatbot', component: v('paciente/Chatbot') },
  ]),

  seccion('/administrativo', 'ADMINISTRATIVO', [
    { path: '', name: 'administrativo', component: v('administrativo/Tablero') },
    { path: 'estudios/:id(\\d+)', name: 'admin-estudio', component: v('administrativo/DetalleEstudio'), props: true },
    { path: 'presupuestos', name: 'admin-presupuestos', component: v('administrativo/EmitirPresupuesto') },
    { path: 'autorizaciones', name: 'admin-autorizaciones', component: v('administrativo/Autorizaciones') },
    { path: 'muestras', name: 'admin-muestras', component: v('administrativo/SeguirMuestra') },
    { path: 'lotes', name: 'admin-lotes', component: v('administrativo/Lotes') },
    { path: 'datos-crudos', name: 'admin-datos-crudos', component: v('administrativo/CargarDatosCrudos') },
    { path: 'reextracciones', name: 'admin-reextracciones', component: v('administrativo/NuevaExtraccion') },
    { path: 'finanzas', name: 'admin-finanzas', component: v('administrativo/RegistroFinanciero') },
  ]),

  seccion('/transportista', 'TRANSPORTISTA', [
    { path: '', name: 'transportista', component: v('transportista/OrdenDelDia') },
    { path: 'paradas/:id(\\d+)', name: 'transportista-recolectar', component: v('transportista/Recolectar'), props: true },
    { path: 'llegada', name: 'transportista-llegada', component: v('transportista/ConfirmarLlegada') },
  ]),

  seccion('/bioinformatico', 'BIOINFORMATICO', [
    { path: '', name: 'bioinformatico', component: v('bioinformatico/Pendientes') },
    { path: 'mis-estudios', name: 'bio-mis-estudios', component: v('bioinformatico/MisEstudios') },
    { path: 'estudios/:id(\\d+)', name: 'bio-variantes', component: v('bioinformatico/CargarVariantes'), props: true },
  ]),

  seccion('/gerente', 'GERENTE_MEDICO', [
    { path: '', name: 'gerente', component: v('gerente/Patologias') },
    { path: 'cupones', name: 'gerente-cupones', component: v('gerente/Cupones') },
  ]),

  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

/** Guarda: rutas privadas requieren sesión; cada sección, su rol. */
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restaurar()
  if (to.meta.publica) {
    if (auth.autenticado && to.name === 'ingresar') return auth.inicio
    return true
  }
  if (!auth.autenticado) return { name: 'ingresar', query: { volver: to.fullPath } }
  if (to.meta.rol && to.meta.rol !== auth.rol) return auth.rol ? INICIO_POR_ROL[auth.rol] : '/ingresar'
  return true
})
