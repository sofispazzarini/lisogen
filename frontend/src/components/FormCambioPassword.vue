<script setup lang="ts">
import { computed, ref } from 'vue'
import Alerta from '@/components/Alerta.vue'
import { useAuthStore } from '@/stores/auth'
import { usarAccion } from '@/utils/composables'

/** E7: cambio de contraseña. `obligatorio`: primer ingreso con la contraseña provisoria (no se pide la
 * actual). Se usa en la pantalla del primer ingreso, en /cuenta/password y en el panel de perfil. */
const props = defineProps<{ obligatorio?: boolean }>()
const emit = defineEmits<{ cambiada: [] }>()

const auth = useAuthStore()
const { enCurso, error, exito, ejecutar } = usarAccion()

const actual = ref('')
const nueva = ref('')
const repetida = ref('')

const robusta = computed(() => nueva.value.length >= 10 && /\d/.test(nueva.value) && /[a-zA-Z]/.test(nueva.value))
const coinciden = computed(() => nueva.value === repetida.value)

async function enviar(): Promise<void> {
  const estado = await ejecutar(
    () => auth.cambiarPassword(nueva.value, props.obligatorio ? undefined : actual.value),
    'Listo, cambiaste tu contraseña.',
  )
  if (estado === 'OK') {
    actual.value = nueva.value = repetida.value = ''
    emit('cambiada')
  }
}
</script>

<template>
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
</template>

<style scoped>
.error { color: var(--tono-error-texto); }
</style>
