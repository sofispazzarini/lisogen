<script setup lang="ts">
import { api, ok } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarCarga } from '@/utils/composables'

const { datos, cargando, error } = usarCarga(() => ok(api.GET('/medico/estudios')))
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Mis Estudios</h1>
        <p>Los Estudios que solicitaste, con su Estado. Los Urgentes aparecen primero.</p>
      </div>
      <div class="fila">
        <RouterLink to="/medico/pacientes/nuevo" class="boton">Alta Paciente</RouterLink>
        <RouterLink to="/medico/estudios/nuevo" class="boton boton--primario">Alta Estudio</RouterLink>
      </div>
    </div>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" :enlace="(e) => `/medico/estudios/${e.id}`" vacio="Todavía no solicitaste Estudios." />
      </Estado>
    </div>
  </section>
</template>
