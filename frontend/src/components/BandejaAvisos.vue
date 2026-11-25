<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useAvisosStore } from '@/stores/avisos'
import { fechaHora } from '@/utils/formato'

const avisos = useAvisosStore()
const abierta = ref(false)
const raiz = ref<HTMLElement | null>(null)
const boton = ref<HTMLButtonElement | null>(null)
/** En el celular el panel ocupa el ancho de la pantalla, justo debajo del botón. */
const topCelular = ref(64)

function clicAfuera(e: MouseEvent): void {
  if (raiz.value && !raiz.value.contains(e.target as Node)) abierta.value = false
}

function teclear(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    abierta.value = false
    boton.value?.focus()
  }
}

watch(abierta, (ahora) => {
  if (ahora) {
    topCelular.value = Math.round((boton.value?.getBoundingClientRect().bottom ?? 56) + 8)
    document.addEventListener('click', clicAfuera)
    document.addEventListener('keydown', teclear)
  } else {
    document.removeEventListener('click', clicAfuera)
    document.removeEventListener('keydown', teclear)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', clicAfuera)
  document.removeEventListener('keydown', teclear)
})
</script>

<template>
  <div ref="raiz" class="bandeja" :style="{ '--top-celular': `${topCelular}px` }">
    <button
      ref="boton"
      class="campana"
      type="button"
      :aria-expanded="abierta"
      :aria-label="`Avisos: ${avisos.noLeidos} sin leer`"
      @click.stop="abierta = !abierta"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
        <path d="M6 8a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 14 6 8Z" />
        <path d="M10 19a2 2 0 0 0 4 0" />
      </svg>
      <span class="texto">Avisos</span>
      <span v-if="avisos.noLeidos" class="contador">{{ avisos.noLeidos }}</span>
    </button>
    <div v-if="abierta" class="panel" role="dialog" aria-label="Bandeja de Avisos">
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
.campana {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--radio-chico);
  background: none;
  color: var(--color-texto-suave);
  font: inherit;
  cursor: pointer;
}
.campana:hover { background: var(--color-fondo); }
.contador {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-urgente);
  color: var(--color-sobre-urgente);
  font: 600 12px/20px var(--fuente);
  text-align: center;
}
.panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  z-index: 600;
  width: min(380px, calc(100vw - 32px));
  max-height: 70vh;
  overflow-y: auto;
  padding: 12px;
  background: var(--color-superficie);
  border: 1px solid var(--color-borde);
  border-radius: var(--radio-panel);
  box-shadow: var(--sombra-flotante);
}
.cabecera { justify-content: space-between; margin-bottom: 8px; }
.aviso-boton { all: unset; display: grid; gap: 2px; padding: 8px; border-radius: var(--radio-chico); cursor: pointer; width: 100%; box-sizing: border-box; }
.aviso-boton:hover { background: var(--color-fondo); }
.aviso--nuevo .aviso-boton { background: var(--color-primario-suave); }
.cuerpo { white-space: pre-line; font-size: 0.875rem; }

/* Celular: el botón no está pegado al borde; el panel ocupa el ancho, debajo del botón */
@media (max-width: 860px) {
  .panel { position: fixed; top: var(--top-celular); left: 12px; right: 12px; width: auto; max-height: calc(100vh - var(--top-celular) - 16px); }
}
@media (max-width: 640px) {
  .campana .texto { display: none; }
}
</style>
