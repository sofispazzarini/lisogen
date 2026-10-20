<script setup lang="ts">
defineProps<{ titulo: string; subtitulo?: string }>()
</script>

<template>
  <main class="auth">
    <div class="tarjeta caja">
      <div class="marca">
        <img src="/favicon.svg" alt="" width="36" height="36" />
        <div>
          <strong>LisoGen</strong>
          <small>Estudios genéticos de Patologías lisosomales</small>
        </div>
      </div>
      <h1>{{ titulo }}</h1>
      <p v-if="subtitulo" class="suave">{{ subtitulo }}</p>
      <slot />
    </div>
  </main>
</template>

<style scoped>
.auth { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; }
.caja { width: min(440px, 100%); display: grid; gap: 14px; }
.marca { display: flex; align-items: center; gap: 10px; }
.marca div { display: grid; line-height: 1.2; }
.marca strong { color: var(--color-primario); font-size: 1.2rem; }
.marca small { color: var(--color-texto-suave); }
h1 { margin: 6px 0 0; }
p { margin: 0; }
</style>
