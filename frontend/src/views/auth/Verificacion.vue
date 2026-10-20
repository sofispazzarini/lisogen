<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Alerta from '@/components/Alerta.vue'
import PantallaAuth from '@/components/PantallaAuth.vue'
import { useAuthStore } from '@/stores/auth'
import { usarAccion } from '@/utils/composables'
import { destinoDe, seguirIngreso } from '@/utils/ingreso'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { enCurso, error, ejecutar } = usarAccion()
const codigo = ref('')

onMounted(() => {
  if (!auth.desafio) void router.replace({ name: 'ingresar' })
})

async function enviar(): Promise<void> {
  const estado = await ejecutar(() => auth.verificar(codigo.value.trim()))
  await seguirIngreso(router, estado, destinoDe(route.query, auth.inicio))
}
</script>

<template>
  <PantallaAuth
    titulo="Verificá que sos vos"
    subtitulo="Ingresaste desde un equipo que no usaste antes. Te mandamos un código de 6 dígitos por mail; vence en 10 minutos."
  >
    <form class="formulario" @submit.prevent="enviar">
      <label class="campo">
        <span>Código de verificación</span>
        <input
          v-model="codigo"
          inputmode="numeric"
          autocomplete="one-time-code"
          pattern="\d{6}"
          maxlength="6"
          placeholder="000000"
          required
        />
      </label>
      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <button class="boton boton--primario" type="submit" :disabled="enCurso || codigo.length !== 6">Verificar</button>
    </form>
    <RouterLink to="/ingresar">Volver a ingresar para recibir otro código</RouterLink>
  </PantallaAuth>
</template>
