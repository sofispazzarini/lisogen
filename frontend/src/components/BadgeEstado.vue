<script setup lang="ts">
import { computed } from 'vue'
import { ETIQUETA, TONO, type EstadoEstudio } from '@/utils/estados'

const props = defineProps<{ estado: EstadoEstudio }>()
const tono = computed(() => TONO[props.estado])
</script>

<template>
  <span class="badge" :class="`badge--${tono}`" :data-estado="estado">{{ ETIQUETA[estado] }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
}
.badge--neutro { background: var(--tono-neutro-fondo); color: var(--tono-neutro-texto); }
.badge--accion { background: var(--tono-accion-fondo); color: var(--tono-accion-texto); }
.badge--alerta { background: var(--tono-alerta-fondo); color: var(--tono-alerta-texto); }
.badge--error { background: var(--tono-error-fondo); color: var(--tono-error-texto); }
.badge--progreso { background: var(--tono-progreso-fondo); color: var(--tono-progreso-texto); }
.badge--exito { background: var(--tono-exito-fondo); color: var(--tono-exito-texto); }
</style>
