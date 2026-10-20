<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BandejaAvisos from '@/components/BandejaAvisos.vue'
import { NOMBRE_ROL, useAuthStore } from '@/stores/auth'
import { useAvisosStore } from '@/stores/avisos'
import { NAVEGACION } from './navegacion'

const auth = useAuthStore()
const avisos = useAvisosStore()
const router = useRouter()
const route = useRoute()
const menuAbierto = ref(false)

const items = computed(() => (auth.rol ? NAVEGACION[auth.rol] : []))

/** El ítem activo es el de ruta más larga que coincide con la actual. */
const activo = computed(() => {
  const coinciden = items.value.filter((i) => route.path === i.ruta || route.path.startsWith(`${i.ruta}/`))
  return coinciden.sort((a, b) => b.ruta.length - a.ruta.length)[0]?.ruta
})

watch(() => route.fullPath, () => (menuAbierto.value = false))
onMounted(() => avisos.iniciar())
onBeforeUnmount(() => avisos.detener())

function salir(): void {
  auth.salir()
  void router.push('/ingresar')
}
</script>

<template>
  <div class="layout">
    <header class="barra">
      <div class="barra-interior">
        <RouterLink :to="auth.inicio" class="marca">
          <img src="/favicon.svg" alt="" width="28" height="28" />
          <span>LisoGen</span>
        </RouterLink>
        <button class="boton boton--chico menu" type="button" :aria-expanded="menuAbierto" aria-controls="nav-principal" @click="menuAbierto = !menuAbierto">
          Menú
        </button>
        <nav id="nav-principal" class="nav" :class="{ abierta: menuAbierto }" aria-label="Principal">
          <RouterLink v-for="i in items" :key="i.ruta" :to="i.ruta" :class="{ activo: activo === i.ruta }" :title="i.escenarios ? `Escenarios ${i.escenarios}` : undefined">
            {{ i.texto }}
          </RouterLink>
        </nav>
        <div class="usuario">
          <BandejaAvisos />
          <div class="quien">
            <strong>{{ auth.usuario?.nombre }} {{ auth.usuario?.apellido }}</strong>
            <small v-if="auth.rol">{{ NOMBRE_ROL[auth.rol] }}</small>
          </div>
          <RouterLink to="/cuenta/password" class="boton boton--chico">Contraseña</RouterLink>
          <button class="boton boton--chico" type="button" @click="salir">Salir</button>
        </div>
      </div>
    </header>
    <main class="contenido">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.barra { background: var(--color-superficie); border-bottom: 1px solid var(--color-borde); position: sticky; top: 0; z-index: 500; }
.barra-interior { max-width: var(--ancho-max); margin: 0 auto; padding: 8px 16px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.marca { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 1.15rem; color: var(--color-primario); text-decoration: none; }
.nav { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
.nav a { padding: 6px 10px; border-radius: var(--radio-chico); text-decoration: none; color: var(--color-texto); font-weight: 500; }
.nav a:hover { background: var(--color-superficie-2); }
.nav a.activo { background: var(--color-primario-suave); color: var(--color-primario); font-weight: 700; }
.usuario { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.quien { display: grid; line-height: 1.2; text-align: right; }
.quien small { color: var(--color-texto-suave); }
.menu { display: none; }
.contenido { max-width: var(--ancho-max); margin: 0 auto; padding: 20px 16px 48px; }

@media (max-width: 860px) {
  .menu { display: inline-flex; margin-left: auto; }
  .nav { display: none; order: 3; flex-basis: 100%; flex-direction: column; }
  .nav.abierta { display: flex; }
  .usuario { order: 4; flex-basis: 100%; justify-content: space-between; margin-left: 0; }
  .quien { text-align: left; }
}
</style>
