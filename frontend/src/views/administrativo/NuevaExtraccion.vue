<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import Reextraccion from '@/components/Reextraccion.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarCarga } from '@/utils/composables'

const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/administrativo/estudios', { params: { query: { estado: 'EN_VIAJE_COREA' } } })),
)
const exito = ref<string | null>(null)
const errorPedido = ref<string | null>(null)

async function hecho(mensaje: string): Promise<void> {
  errorPedido.value = null
  exito.value = mensaje
  await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Solicitar nueva extracción</h1>
        <p>
          E22. Cuando la Muestra llegó mal a Corea: ADN desnaturalizado o mala calidad (por ejemplo, con menos de 2 ml).
          Las Muestras con poco volumen siguen su curso; el aviso aparece en el detalle del Estudio y en Seguir Muestra.
        </p>
      </div>
    </div>
    <Alerta v-if="errorPedido" tipo="error">{{ errorPedido }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" :enlace="(e) => `/administrativo/estudios/${e.id}`" vacio="No hay Estudios con Muestras en Corea.">
          <template #acciones="{ estudio }">
            <Reextraccion :estudio-id="estudio.id" :codigo="estudio.codigo" @hecho="hecho" @error="(m) => (errorPedido = m)" />
          </template>
        </TablaEstudios>
      </Estado>
    </div>
  </section>
</template>
