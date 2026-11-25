<script setup lang="ts">
import { useRoute } from 'vue-router'

/** Tarjeta de las pantallas de acceso (ingresar, registro, verificar, primer cambio de contraseña). La cabecera
 * y el pie los pone LayoutPublico. `pestanas`: muestra "Iniciar sesión / Registrarse". */
defineProps<{ titulo: string; subtitulo?: string; pestanas?: boolean }>()
const route = useRoute()

const PESTANAS = [
  { texto: 'Iniciar sesión', ruta: '/ingresar', nombre: 'ingresar' },
  { texto: 'Registrarse', ruta: '/registro', nombre: 'registro' },
]
</script>

<template>
  <section class="acceso">
    <div class="tarjeta-acceso">
      <h1>{{ titulo }}</h1>
      <p v-if="subtitulo" class="subtitulo">{{ subtitulo }}</p>
      <nav v-if="pestanas" class="pestanas" role="tablist" aria-label="Acceso">
        <RouterLink
          v-for="p in PESTANAS"
          :key="p.ruta"
          :to="{ path: p.ruta, query: route.query }"
          role="tab"
          :aria-selected="route.name === p.nombre"
        >
          {{ p.texto }}
        </RouterLink>
      </nav>
      <div class="contenido-acceso" :role="pestanas ? 'tabpanel' : undefined">
        <slot />
      </div>
      <RouterLink to="/" class="volver">Volver al inicio</RouterLink>
    </div>
  </section>
</template>

<style scoped>
.acceso { padding: 72px 16px 96px; }
.tarjeta-acceso {
  width: min(440px, 100%);
  margin: 0 auto;
  padding: 32px;
  background: var(--color-superficie);
  border: 1px solid var(--color-borde);
  border-radius: var(--radio);
}
h1 { margin: 0 0 22px; font-size: 24px; }
.subtitulo { margin: -12px 0 22px; color: var(--color-texto-suave); font-size: 14.5px; }
.pestanas { display: flex; gap: 24px; margin-bottom: 26px; border-bottom: 1px solid var(--color-borde); }
.pestanas a {
  margin-bottom: -1px;
  padding: 10px 0 12px;
  border-bottom: 2px solid transparent;
  color: var(--color-texto-suave);
  font-weight: 500;
  text-decoration: none;
}
.pestanas a[aria-selected='true'] { color: var(--color-primario); border-bottom-color: var(--color-primario); }
.contenido-acceso { display: grid; gap: 16px; }
.volver { display: inline-block; margin-top: 22px; font-size: 14px; }
@media (max-width: 560px) {
  .acceso { padding: 32px 12px 56px; }
  .tarjeta-acceso { padding: 24px 18px; }
}
</style>
