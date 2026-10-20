<script setup lang="ts">
import Alerta from './Alerta.vue'

/** Envoltorio para cargas: muestra "Cargando…", el error o el contenido. */
defineProps<{ cargando: boolean; error: string | null }>()
</script>

<template>
  <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
  <p v-else-if="cargando" class="suave" aria-live="polite">Cargando…</p>
  <slot v-else />
</template>
