<script setup lang="ts">
import { api, ok } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarCarga } from '@/utils/composables'

const { datos, cargando, error } = usarCarga(() => ok(api.GET('/bioinformatico/estudios')))
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Mis análisis</h1>
        <p>Estudios que tomaste y todavía no tienen Resultado.</p>
      </div>
    </div>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" :enlace="(e) => `/bioinformatico/estudios/${e.id}`" vacio="No tenés Estudios en análisis." />
      </Estado>
    </div>
  </section>
</template>
