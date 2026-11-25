<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FormCambioPassword from '@/components/FormCambioPassword.vue'
import PantallaAuth from '@/components/PantallaAuth.vue'
import { useAuthStore } from '@/stores/auth'
import { destinoDe } from '@/utils/ingreso'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

/** Obligatorio en el primer ingreso (desafío de E7) o voluntario con la sesión iniciada. */
const obligatorio = computed(() => auth.desafio !== null)

/** Después del cambio obligatorio (`desafio` ya quedó en null) se entra al sistema; el voluntario se queda. */
async function cambiada(): Promise<void> {
  if (route.name === 'cambiar-password') await router.push(destinoDe(route.query, auth.inicio))
}
</script>

<template>
  <PantallaAuth
    v-if="obligatorio"
    titulo="Elegí tu contraseña"
    subtitulo="Es tu primer ingreso: cambiá la contraseña provisoria que recibiste por mail."
  >
    <FormCambioPassword obligatorio @cambiada="cambiada" />
  </PantallaAuth>
  <section v-else class="pagina">
    <header class="encabezado">
      <div>
        <h1>Cambiar contraseña</h1>
        <p>También podés cambiarla desde tu perfil, tocando tu avatar arriba a la derecha.</p>
      </div>
    </header>
    <div class="tarjeta">
      <FormCambioPassword />
    </div>
  </section>
</template>
