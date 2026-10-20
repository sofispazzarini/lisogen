<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Alerta from '@/components/Alerta.vue'
import PantallaAuth from '@/components/PantallaAuth.vue'
import { useAuthStore } from '@/stores/auth'
import { usarAccion } from '@/utils/composables'
import { destinoDe } from '@/utils/ingreso'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { enCurso, error, exito, ejecutar } = usarAccion()

/** Obligatorio en el primer ingreso (desafío de E7) o voluntario con la sesión iniciada. */
const obligatorio = computed(() => auth.desafio !== null)
const actual = ref('')
const nueva = ref('')
const repetida = ref('')

const robusta = computed(() => nueva.value.length >= 10 && /\d/.test(nueva.value) && /[a-zA-Z]/.test(nueva.value))
const coinciden = computed(() => nueva.value === repetida.value)

async function enviar(): Promise<void> {
  const eraObligatorio = obligatorio.value
  const estado = await ejecutar(
    () => auth.cambiarPassword(nueva.value, eraObligatorio ? undefined : actual.value),
    'Listo, cambiaste tu contraseña.',
  )
  if (estado === 'OK' && eraObligatorio) {
    await router.push(destinoDe(route.query, auth.inicio))
  } else if (estado === 'OK') {
    actual.value = nueva.value = repetida.value = ''
  }
}
</script>

<template>
  <component
    :is="obligatorio ? PantallaAuth : 'section'"
    titulo="Elegí tu contraseña"
    subtitulo="Es tu primer ingreso: cambiá la contraseña provisoria que recibiste por mail."
    :class="{ 'tarjeta pagina': !obligatorio }"
  >
    <h1 v-if="!obligatorio">Cambiar contraseña</h1>
    <form class="formulario" @submit.prevent="enviar">
      <label v-if="!obligatorio" class="campo">
        <span>Contraseña actual</span>
        <input v-model="actual" type="password" autocomplete="current-password" required />
      </label>
      <label class="campo">
        <span>Contraseña nueva</span>
        <input v-model="nueva" type="password" autocomplete="new-password" required />
        <small>Al menos 10 caracteres, con letras y números.</small>
      </label>
      <label class="campo">
        <span>Repetí la contraseña nueva</span>
        <input v-model="repetida" type="password" autocomplete="new-password" required />
        <small v-if="repetida && !coinciden" class="error">No coinciden.</small>
      </label>
      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
      <button class="boton boton--primario" type="submit" :disabled="enCurso || !robusta || !coinciden">Guardar contraseña</button>
    </form>
  </component>
</template>

<style scoped>
.error { color: var(--tono-error-texto); }
</style>
