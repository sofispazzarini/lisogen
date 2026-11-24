<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BandejaAvisos from '@/components/BandejaAvisos.vue'
import FormCambioPassword from '@/components/FormCambioPassword.vue'
import MenuCuenta from '@/components/MenuCuenta.vue'
import PanelLateral from '@/components/PanelLateral.vue'
import { NOMBRE_ROL, useAuthStore } from '@/stores/auth'
import { useAvisosStore } from '@/stores/avisos'
import { GRUPOS, itemActivo, migas } from './navegacion'

const auth = useAuthStore()
const avisos = useAvisosStore()
const router = useRouter()
const route = useRoute()

const grupos = computed(() => (auth.rol ? GRUPOS[auth.rol] : []))
const activo = computed(() => itemActivo(grupos.value, route.path)?.item.ruta)
const miga = computed(() => migas(grupos.value, route.path, route.meta.titulo))

// Perfil en un panel lateral: datos de la cuenta y cambio de contraseña sin salir de la pantalla
const perfilAbierto = ref(false)
const cambiandoPassword = ref(false)
watch(perfilAbierto, (abierto) => {
  if (!abierto) cambiandoPassword.value = false
})
const formPassword = ref<HTMLElement | null>(null)
async function abrirCambioPassword(): Promise<void> {
  cambiandoPassword.value = true
  await nextTick()
  formPassword.value?.querySelector('input')?.focus() // el botón que se tocó desaparece: el foco va al formulario
}
watch(() => route.fullPath, () => (perfilAbierto.value = false))

// En el celular la barra lateral es una fila que se desliza: se lleva a la vista la sección activa
watch(activo, async () => {
  await nextTick()
  document.querySelector('.item-nav[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
})

onMounted(() => avisos.iniciar())
onBeforeUnmount(() => avisos.detener())

function salir(): void {
  perfilAbierto.value = false
  auth.salir()
  void router.push('/ingresar')
}
</script>

<template>
  <div class="app">
    <aside class="lateral">
      <RouterLink :to="auth.inicio" class="marca" aria-label="LisoGen, inicio">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        LisoGen
      </RouterLink>
      <nav class="secciones" aria-label="Secciones">
        <div v-for="g in grupos" :key="g.nombre || 'principal'" class="grupo">
          <div v-if="g.nombre" class="grupo-nombre">{{ g.nombre }}</div>
          <RouterLink
            v-for="i in g.items"
            :key="i.ruta"
            :to="i.ruta"
            class="item-nav"
            :aria-current="activo === i.ruta ? 'page' : undefined"
            :title="i.escenarios ? `Escenarios ${i.escenarios}` : undefined"
          >
            {{ i.texto }}
          </RouterLink>
        </div>
      </nav>
    </aside>

    <div class="columna">
      <header class="superior">
        <nav class="migas" aria-label="Ubicación">
          <template v-for="(m, i) in miga" :key="i">
            <span v-if="i > 0" class="separador" aria-hidden="true">/</span>
            <RouterLink v-if="m.ruta" :to="m.ruta">{{ m.texto }}</RouterLink>
            <strong v-else-if="i === miga.length - 1" aria-current="page">{{ m.texto }}</strong>
            <span v-else>{{ m.texto }}</span>
          </template>
        </nav>
        <div class="herramientas">
          <BandejaAvisos />
          <MenuCuenta
            v-if="auth.usuario"
            :nombre="auth.usuario.nombre"
            :apellido="auth.usuario.apellido"
            @perfil="perfilAbierto = true"
            @salir="salir"
          />
        </div>
      </header>

      <main class="contenido">
        <RouterView />
      </main>

      <footer class="pie">Grupo 03</footer>
    </div>

    <PanelLateral v-model="perfilAbierto" titulo="Mi perfil">
      <template v-if="auth.usuario">
        <div class="perfil-id">
          <span class="avatar avatar--grande" aria-hidden="true">{{ (auth.usuario.nombre.charAt(0) + auth.usuario.apellido.charAt(0)).toUpperCase() }}</span>
          <div>
            <strong>{{ auth.usuario.nombre }} {{ auth.usuario.apellido }}</strong>
            <p v-if="auth.rol">{{ NOMBRE_ROL[auth.rol] }}</p>
          </div>
        </div>
        <dl class="campos-perfil">
          <div><dt>Correo</dt><dd>{{ auth.usuario.email }}</dd></div>
          <div v-if="auth.rol"><dt>Rol</dt><dd>{{ NOMBRE_ROL[auth.rol] }}</dd></div>
        </dl>
        <div v-if="cambiandoPassword" ref="formPassword" class="tarjeta-plana">
          <h3>Cambiar contraseña</h3>
          <FormCambioPassword />
        </div>
        <div class="acciones-perfil">
          <button v-if="!cambiandoPassword" class="boton ancho" type="button" @click="abrirCambioPassword">Cambiar contraseña</button>
          <button class="boton ancho boton--peligro" type="button" @click="salir">Cerrar sesión</button>
        </div>
      </template>
    </PanelLateral>
  </div>
</template>

<style scoped>
.app { display: flex; min-height: 100vh; }

/* Barra lateral con las secciones agrupadas por flujo de trabajo */
.lateral {
  position: sticky;
  top: 0;
  align-self: flex-start;
  flex: none;
  width: 248px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 22px 14px;
  overflow-y: auto;
  background: var(--color-superficie);
  border-right: 1px solid var(--color-borde);
}
.marca {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  color: var(--color-texto);
  font: 600 19px/1 var(--fuente-titulos);
  letter-spacing: -0.01em;
  text-decoration: none;
}
.marca img { flex: none; }
.secciones { display: flex; flex-direction: column; gap: 18px; }
.grupo { display: flex; flex-direction: column; gap: 2px; }
.grupo-nombre { padding: 0 12px 6px; font-size: 12px; font-weight: 600; color: var(--color-texto-suave); }
.item-nav {
  position: relative;
  display: block;
  padding: 8px 12px;
  border-radius: var(--radio-chico);
  color: var(--color-texto);
  font-size: 14.5px;
  text-decoration: none;
}
.item-nav:hover { background: var(--color-fondo); }
.item-nav[aria-current='page'] { background: var(--color-primario-suave); color: var(--color-primario); font-weight: 600; }
.item-nav[aria-current='page']::before {
  content: '';
  position: absolute;
  left: -14px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--color-primario);
}

/* Columna de contenido */
.columna { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.superior {
  position: sticky;
  top: 0;
  z-index: 500;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 32px;
  background: var(--color-superficie);
  border-bottom: 1px solid var(--color-borde);
}
.migas { min-width: 0; font-size: 14px; color: var(--color-texto-suave); }
.migas a { color: var(--color-texto-suave); }
.migas strong { font-weight: 500; color: var(--color-texto); }
.separador { margin: 0 6px; }
.herramientas { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.contenido { flex: 1; width: 100%; max-width: var(--ancho-max); margin: 0 auto; padding: 44px 32px 56px; }
.pie { padding: 18px 16px 22px; text-align: center; font-size: 12px; color: var(--color-texto-suave); }

/* Panel de perfil */
.perfil-id { display: flex; gap: 16px; align-items: center; margin-bottom: 24px; }
.perfil-id strong { display: block; font: 600 20px/1.2 var(--fuente-titulos); }
.perfil-id p { margin: 2px 0 0; color: var(--color-texto-suave); font-size: 14px; }
.avatar {
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-primario);
  color: var(--color-sobre-primario);
  font-weight: 600;
}
.avatar--grande { width: 60px; height: 60px; font-size: 20px; }
.campos-perfil { margin: 0 0 24px; }
.campos-perfil div { display: grid; grid-template-columns: 110px 1fr; gap: 12px; padding: 12px 0; border-top: 1px solid var(--color-borde); }
.campos-perfil dt { color: var(--color-texto-suave); font-size: 14px; }
.campos-perfil dd { margin: 0; font-size: 14px; overflow-wrap: anywhere; }
.tarjeta-plana { margin-bottom: 16px; padding: 16px; border: 1px solid var(--color-borde); border-radius: var(--radio-panel); }
.acciones-perfil { display: flex; flex-direction: column; gap: 10px; }
.ancho { width: 100%; }

/* Celular y tablet: la barra lateral pasa a ser una fila de secciones que se desliza de costado */
@media (max-width: 860px) {
  .app { flex-direction: column; }
  .lateral {
    position: static;
    width: 100%;
    height: auto;
    flex-direction: row;
    align-items: center;
    gap: 18px;
    padding: 12px 16px;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid var(--color-borde);
  }
  .marca { flex: none; padding: 0; }
  .secciones { flex-direction: row; flex: none; gap: 4px; }
  .grupo { flex-direction: row; flex: none; gap: 2px; }
  .grupo + .grupo { margin-left: 4px; padding-left: 4px; border-left: 1px solid var(--color-borde); }
  .grupo-nombre { display: none; }
  .item-nav { width: auto; padding: 7px 10px; white-space: nowrap; }
  .item-nav[aria-current='page']::before { display: none; }
  .superior { padding: 10px 16px; }
  .contenido { padding: 32px 16px 48px; }
}
@media (max-width: 640px) {
  .contenido { padding: 24px 12px 40px; }
  .herramientas { gap: 6px; }
}
</style>
