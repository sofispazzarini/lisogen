<script setup lang="ts">
withDefaults(defineProps<{ tipo?: 'error' | 'exito' | 'info' }>(), { tipo: 'info' })
</script>

<template>
  <div class="alerta" :class="`alerta--${tipo}`" :role="tipo === 'error' ? 'alert' : 'status'"><slot /></div>
</template>

<style scoped>
.alerta { padding: 10px 14px; border-radius: var(--radio-chico); font-weight: 500; }
.alerta--error { background: var(--tono-error-fondo); color: var(--tono-error-texto); }
.alerta--exito { background: var(--tono-exito-fondo); color: var(--tono-exito-texto); }
.alerta--info { background: var(--tono-progreso-fondo); color: var(--tono-progreso-texto); }
</style>
