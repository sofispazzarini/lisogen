<script setup lang="ts">
import { ref } from 'vue'
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

const email = ref('')
const password = ref('')

async function enviar(): Promise<void> {
  const estado = await ejecutar(() => auth.ingresar(email.value.trim(), password.value))
  await seguirIngreso(router, estado, destinoDe(route.query, auth.inicio))
}
</script>

<template>
  <PantallaAuth titulo="Ingresar" subtitulo="Usá el mail y la contraseña de tu cuenta.">
    <Alerta v-if="route.query.vencida" tipo="info">Tu sesión venció. Ingresá de nuevo.</Alerta>
    <form class="formulario" @submit.prevent="enviar">
      <label class="campo">
        <span>Mail</span>
        <input v-model="email" type="email" autocomplete="username" required />
      </label>
      <label class="campo">
        <span>Contraseña</span>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <button class="boton boton--primario" type="submit" :disabled="enCurso">{{ enCurso ? 'Ingresando…' : 'Ingresar' }}</button>
    </form>
    <p class="suave">
      ¿Sos Médico Tratante, Administrativo, Bioinformático o Gerente Médico y no tenés cuenta?
      <RouterLink to="/registro">Registrate</RouterLink>.
    </p>
    <p class="suave">Los Pacientes reciben sus credenciales por mail cuando su Médico Tratante los da de alta.</p>
  </PantallaAuth>
</template>
