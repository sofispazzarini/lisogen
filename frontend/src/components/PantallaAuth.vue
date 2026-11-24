<script setup lang="ts">
defineProps<{ titulo: string; subtitulo?: string }>()
</script>

<template>
  <div class="auth">
    <main class="caja">
      <div class="marca">
        <img src="/favicon.svg" alt="" width="36" height="36" />
        <div>
          <strong>LisoGen</strong>
          <small>Estudios genéticos de Patologías lisosomales</small>
        </div>
      </div>
      <div class="tarjeta contenido-auth">
        <h1>{{ titulo }}</h1>
        <p v-if="subtitulo" class="suave">{{ subtitulo }}</p>
        <slot />
      </div>
    </main>
    <footer class="pie">Grupo 03</footer>
  </div>
</template>

<style scoped>
.auth { min-height: 100vh; display: grid; grid-template-rows: 1fr auto; padding: 24px 16px 0; }
.caja { align-self: center; justify-self: center; width: min(440px, 100%); display: grid; gap: 20px; }
.marca { display: flex; align-items: center; gap: 12px; padding: 0 4px; }
.marca div { display: grid; line-height: 1.2; }
.marca strong { font: 600 22px/1.1 var(--fuente-titulos); letter-spacing: -0.01em; }
.marca small { color: var(--color-texto-suave); font-size: 13px; }
.contenido-auth { display: grid; gap: 14px; padding: 28px; }
h1 { margin: 0; font-size: clamp(26px, 4vw, 30px); }
p { margin: 0; }
.pie { padding: 18px 16px 22px; text-align: center; font-size: 12px; color: var(--color-texto-suave); }
@media (max-width: 640px) {
  .contenido-auth { padding: 20px 16px; }
}
</style>
