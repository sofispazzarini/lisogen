<script setup lang="ts">
import { computed } from 'vue'
import { ETIQUETA, pasos, type EstadoEstudio, type TipoEstudio } from '@/utils/estados'

const props = withDefaults(defineProps<{ estado: EstadoEstudio; tipo?: TipoEstudio }>(), { tipo: 'EXOMA' })
const lista = computed(() => pasos(props.estado, props.tipo))
</script>

<template>
  <ol class="pasos" :aria-label="`Estado actual: ${ETIQUETA[estado]}`">
    <li v-for="{ paso, estado: e } in lista" :key="paso.clave" :class="`paso paso--${e}`" :aria-current="e === 'actual' ? 'step' : undefined">
      <span class="punto" aria-hidden="true">{{ e === 'hecho' ? '✓' : '' }}</span>
      <span class="nombre">{{ paso.etiqueta }}</span>
      <span v-if="e === 'actual'" class="detalle">{{ ETIQUETA[estado] }}</span>
    </li>
  </ol>
</template>

<style scoped>
.pasos {
  display: flex;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}
.paso {
  flex: 1 1 0;
  min-width: 92px;
  display: grid;
  justify-items: center;
  gap: 4px;
  text-align: center;
  position: relative;
  font-size: 0.82rem;
}
.paso:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 13px;
  left: calc(50% + 16px);
  right: calc(-50% + 16px);
  height: 2px;
  background: var(--color-borde);
}
.paso--hecho:not(:last-child)::after { background: var(--color-acento); }
.punto {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 2px solid var(--color-borde);
  background: var(--color-superficie);
  color: #fff;
  font-weight: 700;
}
.paso--hecho .punto { background: var(--color-acento); border-color: var(--color-acento); }
.paso--actual .punto { border-color: var(--color-primario); box-shadow: 0 0 0 4px var(--color-primario-suave); }
.paso--actual .nombre { font-weight: 700; color: var(--color-primario); }
.paso--pendiente .nombre { color: var(--color-texto-suave); }
.detalle { font-size: 0.75rem; color: var(--color-texto-suave); }
</style>
