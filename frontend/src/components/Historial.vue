<script setup lang="ts">
import type { Esquemas } from '@/api/cliente'
import { fechaHora } from '@/utils/formato'
import BadgeEstado from './BadgeEstado.vue'

defineProps<{ items: Esquemas['HistorialItem'][] }>()
</script>

<template>
  <ol class="historial">
    <li v-for="(h, i) in [...items].reverse()" :key="i">
      <div class="fila">
        <BadgeEstado :estado="h.estado_nuevo" />
        <span class="suave">{{ fechaHora(h.created_at) }} · {{ h.actor }}</span>
      </div>
      <p v-if="h.motivo" class="motivo">{{ h.motivo }}</p>
    </li>
  </ol>
</template>

<style scoped>
.historial { margin: 0; padding: 0 0 0 14px; border-left: 2px solid var(--color-borde); display: grid; gap: 12px; list-style: none; }
.historial li { position: relative; }
.historial li::before { content: ''; position: absolute; left: -20px; top: 7px; width: 10px; height: 10px; border-radius: 50%; background: var(--color-primario); }
.motivo { margin: 4px 0 0; white-space: pre-line; }
</style>
