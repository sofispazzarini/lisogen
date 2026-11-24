<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

/** Panel que entra desde la derecha sobre un velo (perfil, etc.). Se cierra con Escape, con el botón o
 * tocando el velo, y al cerrarse devuelve el foco a donde estaba. */
defineProps<{ titulo: string }>()
const abierto = defineModel<boolean>({ default: false })

const idTitulo = `panel-${useId()}`
const cerrar = ref<HTMLButtonElement | null>(null)
let focoPrevio: HTMLElement | null = null

function alTeclear(e: KeyboardEvent): void {
  if (e.key === 'Escape') abierto.value = false
}

watch(abierto, async (ahora) => {
  if (ahora) {
    focoPrevio = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.addEventListener('keydown', alTeclear)
    await nextTick()
    cerrar.value?.focus()
  } else {
    document.removeEventListener('keydown', alTeclear)
    focoPrevio?.focus()
    focoPrevio = null
  }
})

onBeforeUnmount(() => document.removeEventListener('keydown', alTeclear))
</script>

<template>
  <Teleport to="body">
    <div class="velo" :class="{ abierto }" aria-hidden="true" @click="abierto = false" />
    <aside class="panel-lateral" :class="{ abierto }" role="dialog" aria-modal="true" :aria-labelledby="idTitulo" :inert="!abierto || undefined">
      <div class="cabecera">
        <h2 :id="idTitulo">{{ titulo }}</h2>
        <button ref="cerrar" class="boton boton--chico" type="button" @click="abierto = false">Cerrar</button>
      </div>
      <slot />
    </aside>
  </Teleport>
</template>

<style scoped>
.velo {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgb(23 38 43 / 28%);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
.velo.abierto { opacity: 1; pointer-events: auto; }
.panel-lateral {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  width: min(420px, 100%);
  overflow: auto;
  padding: 28px;
  background: var(--color-superficie);
  border-left: 1px solid var(--color-borde);
  box-shadow: var(--sombra-flotante);
  transform: translateX(100%);
  visibility: hidden;
  transition: transform 0.25s ease, visibility 0.25s;
}
/* Al abrir, visible al instante (si no, en el primer cuadro no se puede enfocar nada adentro); al cerrar,
   la visibilidad espera a que termine de deslizarse */
.panel-lateral.abierto { transform: none; visibility: visible; transition: transform 0.25s ease, visibility 0s; }
.cabecera { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 24px; }
.cabecera h2 { margin: 0; font-size: 22px; }

@media (prefers-reduced-motion: reduce) {
  .velo,
  .panel-lateral { transition: none; }
}
@media (max-width: 640px) {
  .panel-lateral { padding: 20px 16px; }
}
</style>
