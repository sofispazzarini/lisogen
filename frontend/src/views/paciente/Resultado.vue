<script setup lang="ts">
import { computed } from 'vue'
import { api, ok } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import ResultadoVista from '@/components/ResultadoVista.vue'
import { usarCarga } from '@/utils/composables'

const props = defineProps<{ id: string }>()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
// E13: cada lectura del Resultado queda auditada en el backend.
const { datos, cargando, error } = usarCarga(() => ok(api.GET('/paciente/estudios/{estudio_id}/resultado', path.value)))
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Resultado del Estudio</h1>
        <p>Tu Médico Tratante también lo recibió para explicártelo en la próxima consulta.</p>
      </div>
      <RouterLink :to="`/paciente/estudios/${id}`" class="boton">Volver al Estudio</RouterLink>
    </div>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <ResultadoVista v-if="datos" :resultado="datos" />
      </Estado>
    </div>
  </section>
</template>
