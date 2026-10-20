<script setup lang="ts">
import { ref } from 'vue'
import { useAvisosStore } from '@/stores/avisos'
import { fechaHora } from '@/utils/formato'

const avisos = useAvisosStore()
const abierta = ref(false)
</script>

<template>
  <div class="bandeja">
    <button
      class="boton boton--chico campana"
      type="button"
      :aria-expanded="abierta"
      :aria-label="`Avisos: ${avisos.noLeidos} sin leer`"
      @click="abierta = !abierta"
    >
      <span aria-hidden="true">🔔</span> Avisos
      <span v-if="avisos.noLeidos" class="contador">{{ avisos.noLeidos }}</span>
    </button>
    <div v-if="abierta" class="panel tarjeta" role="dialog" aria-label="Bandeja de Avisos">
      <div class="fila cabecera">
        <strong>Avisos</strong>
        <button v-if="avisos.noLeidos" class="boton boton--chico" type="button" @click="avisos.marcarTodos()">Marcar todos como leídos</button>
      </div>
      <ul v-if="avisos.avisos.length" class="lista-plana">
        <li v-for="a in avisos.avisos" :key="a.id" class="aviso" :class="{ 'aviso--nuevo': !a.leida }">
          <button type="button" class="aviso-boton" @click="!a.leida && avisos.marcarLeido(a.id)">
            <strong>{{ a.asunto }}</strong>
            <span class="cuerpo">{{ a.cuerpo }}</span>
            <small class="suave">{{ fechaHora(a.created_at) }}</small>
          </button>
        </li>
      </ul>
      <p v-else class="vacio">No tenés Avisos.</p>
    </div>
  </div>
</template>

<style scoped>
.bandeja { position: relative; }
.contador { background: var(--color-urgente); color: #fff; border-radius: 999px; padding: 0 7px; font-size: 0.75rem; }
.panel { position: absolute; right: 0; top: calc(100% + 8px); width: min(380px, calc(100vw - 32px)); max-height: 70vh; overflow-y: auto; z-index: 1000; padding: 12px; }
.cabecera { justify-content: space-between; margin-bottom: 8px; }
.aviso-boton { all: unset; display: grid; gap: 2px; padding: 8px; border-radius: var(--radio-chico); cursor: pointer; width: 100%; box-sizing: border-box; }
.aviso-boton:hover { background: var(--color-superficie-2); }
.aviso--nuevo .aviso-boton { background: var(--color-primario-suave); }
.cuerpo { white-space: pre-line; font-size: 0.875rem; }
</style>
