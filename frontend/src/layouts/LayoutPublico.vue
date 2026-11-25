<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/** Armazón de las páginas públicas: el home y las pantallas de acceso (ingresar, verificar, registro). */
const auth = useAuthStore()
const route = useRoute()

const SECCIONES = [
  { texto: 'Qué ofrecemos', hash: '#estudios' },
  { texto: 'Cómo funciona', hash: '#como-funciona' },
  { texto: 'Laboratorio', hash: '#laboratorio' },
  { texto: 'Dónde estamos', hash: '#sede' },
  { texto: 'Preguntas', hash: '#preguntas' },
]

const enAcceso = computed(() => route.name !== 'inicio')
</script>

<template>
  <div class="publico">
    <header class="cabecera">
      <div class="envoltura cabecera-interior">
        <RouterLink :to="{ path: '/', hash: '#inicio' }" class="marca">
          <img src="/favicon.svg" alt="" width="30" height="30" />
          LisoGen
        </RouterLink>
        <nav class="anclas" aria-label="Principal">
          <RouterLink v-for="s in SECCIONES" :key="s.hash" :to="{ path: '/', hash: s.hash }">{{ s.texto }}</RouterLink>
        </nav>
        <RouterLink v-if="auth.autenticado" :to="auth.inicio" class="entrar">Ir a mi panel</RouterLink>
        <RouterLink v-else to="/ingresar" class="entrar" :aria-current="enAcceso ? 'page' : undefined">Ingresar</RouterLink>
      </div>
    </header>

    <main>
      <RouterView />
    </main>

    <footer class="pie-sitio">
      <div class="envoltura pie-grilla">
        <div>
          <strong>LisoGen</strong>
          <p>Estudios de exoma clínico para Fabry, Pompe, MPS 1, Gaucher y ASMD, con Laboratorio Central en La Plata.</p>
        </div>
        <nav aria-label="Pie">
          <RouterLink v-for="s in SECCIONES.filter((x) => x.hash !== '#laboratorio')" :key="s.hash" :to="{ path: '/', hash: s.hash }">
            {{ s.texto }}
          </RouterLink>
          <RouterLink v-if="auth.autenticado" :to="auth.inicio">Ir a mi panel</RouterLink>
          <RouterLink v-else to="/ingresar">Ingresar</RouterLink>
        </nav>
      </div>
      <p class="grupo">Grupo 03</p>
    </footer>
  </div>
</template>

<style scoped>
.publico { min-height: 100vh; display: flex; flex-direction: column; font-size: 16px; line-height: 1.6; }
main { flex: 1; }
.envoltura { width: min(1080px, 100% - 48px); margin: 0 auto; }

.cabecera { position: sticky; top: 0; z-index: 20; background: var(--color-superficie); border-bottom: 1px solid var(--color-borde); }
.cabecera-interior { display: flex; align-items: center; gap: 28px; padding: 16px 0; }
.marca {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-texto);
  font: 600 20px/1 var(--fuente-titulos);
  letter-spacing: -0.01em;
  text-decoration: none;
}
.marca img { flex: none; }
.anclas { display: flex; gap: 22px; margin-left: 12px; }
.anclas a { color: var(--color-texto-suave); font-size: 15px; text-decoration: none; }
.anclas a:hover { color: var(--color-texto); }
.entrar {
  margin-left: auto;
  display: inline-block;
  padding: 8px 18px;
  border: 1px solid var(--color-primario);
  border-radius: var(--radio-chico);
  color: var(--color-primario);
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}
.entrar:hover,
.entrar[aria-current='page'] { background: var(--color-primario-suave); }

.pie-sitio { padding-top: 44px; background: var(--color-superficie); border-top: 1px solid var(--color-borde); }
.pie-grilla { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 32px; padding-bottom: 32px; }
.pie-grilla strong { display: block; margin-bottom: 6px; font: 600 18px/1.2 var(--fuente-titulos); }
.pie-grilla p { margin: 0; max-width: 40ch; font-size: 14.5px; color: var(--color-texto-suave); }
.pie-grilla nav { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 20px; }
.pie-grilla nav a { color: var(--color-texto-suave); font-size: 14.5px; text-decoration: none; }
.pie-grilla nav a:hover { color: var(--color-texto); }
.grupo { margin: 0; padding: 18px 16px 24px; text-align: center; font-size: 12px; color: var(--color-texto-suave); border-top: 1px solid var(--color-borde); }

@media (max-width: 920px) {
  .anclas { display: none; }
}
@media (max-width: 560px) {
  .envoltura { width: calc(100% - 32px); }
  .cabecera-interior { gap: 12px; padding: 12px 0; }
}
</style>
