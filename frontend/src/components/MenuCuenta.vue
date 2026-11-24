<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/** Avatar con las iniciales que despliega las acciones de la cuenta (no de trabajo): Ver perfil y Cerrar
 * sesión. Se cierra al tocar afuera o con Escape. */
const props = defineProps<{ nombre: string; apellido: string }>()
const emit = defineEmits<{ perfil: []; salir: [] }>()

const abierto = ref(false)
const raiz = ref<HTMLElement | null>(null)
const boton = ref<HTMLButtonElement | null>(null)
const iniciales = computed(() => `${props.nombre.charAt(0)}${props.apellido.charAt(0)}`.toUpperCase())

function cerrar(devolverFoco = false): void {
  abierto.value = false
  if (devolverFoco) boton.value?.focus()
}

function clicAfuera(e: MouseEvent): void {
  if (raiz.value && !raiz.value.contains(e.target as Node)) cerrar()
}

function teclear(e: KeyboardEvent): void {
  if (e.key === 'Escape') cerrar(true)
}

watch(abierto, (ahora) => {
  if (ahora) {
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

/** El foco vuelve al avatar antes de abrir el perfil: así el panel lo recuerda y lo devuelve al cerrarse. */
function elegir(accion: 'perfil' | 'salir'): void {
  cerrar(true)
  if (accion === 'perfil') emit('perfil')
  else emit('salir')
}
</script>

<template>
  <div ref="raiz" class="cuenta">
    <button
      ref="boton"
      class="avatar-boton"
      type="button"
      aria-haspopup="true"
      :aria-expanded="abierto"
      :aria-label="`Cuenta de ${nombre} ${apellido}`"
      @click.stop="abierto = !abierto"
    >
      <span class="avatar" aria-hidden="true">{{ iniciales }}</span>
    </button>
    <div v-if="abierto" class="menu-cuenta" role="menu">
      <button class="item" type="button" role="menuitem" @click="elegir('perfil')">
        <strong>Ver perfil</strong>
        <span>Tus datos y tu contraseña</span>
      </button>
      <button class="item item--peligro" type="button" role="menuitem" @click="elegir('salir')">
        <strong>Cerrar sesión</strong>
      </button>
    </div>
  </div>
</template>

<style scoped>
.cuenta { position: relative; }
.avatar-boton {
  display: flex;
  align-items: center;
  padding: 4px;
  border: 0;
  border-radius: 10px;
  background: none;
  cursor: pointer;
}
.avatar-boton:hover { background: var(--color-fondo); }
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--color-primario);
  color: var(--color-sobre-primario);
  font-weight: 600;
  font-size: 13px;
}
.menu-cuenta {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 600;
  min-width: 240px;
  padding: 8px;
  background: var(--color-superficie);
  border: 1px solid var(--color-borde);
  border-radius: var(--radio-panel);
  box-shadow: var(--sombra-flotante);
}
.item {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  border-radius: var(--radio-chico);
  background: none;
  color: var(--color-texto);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.item:hover { background: var(--color-fondo); }
.item strong { display: block; font-weight: 500; }
.item span { display: block; font-size: 12.5px; color: var(--color-texto-suave); }
.item--peligro { color: var(--color-urgente); }
</style>
