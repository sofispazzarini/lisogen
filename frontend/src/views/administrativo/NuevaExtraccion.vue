<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/administrativo/estudios', { params: { query: { estado: 'EN_VIAJE_COREA' } } })),
)
const detalles = ref<Record<number, string>>({})
const { enCurso, error: errorPedido, exito, ejecutar } = usarAccion()

/** E22: mismo Estudio, sin costo; el Paciente vuelve a sacar Turno y se avisa a él y al Médico Tratante. */
async function solicitar(id: number, codigo: string): Promise<void> {
  if (!window.confirm(`¿Solicitás una nueva extracción para ${codigo}? El Paciente tendrá que sacar otro Turno.`)) return
  const r = await ejecutar(
    () =>
      ok(
        api.POST('/administrativo/estudios/{estudio_id}/reextraccion', {
          params: { path: { estudio_id: id } },
          body: { motivo: 'DESNATURALIZADA', detalle: detalles.value[id] || null },
        }),
      ),
    `Nueva extracción solicitada para ${codigo}. Avisamos al Paciente y al Médico Tratante.`,
  )
  if (r) await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Solicitar nueva extracción</h1>
        <p>E22. Cuando el ADN llegó desnaturalizado. Las Muestras de menos de 2 ml piden nueva extracción solas al llegar al Laboratorio Central.</p>
      </div>
    </div>
    <Alerta v-if="errorPedido" tipo="error">{{ errorPedido }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" :enlace="(e) => `/administrativo/estudios/${e.id}`" vacio="No hay Estudios con Muestras en Corea.">
          <template #acciones="{ estudio }">
            <form class="fila" @submit.prevent="solicitar(estudio.id, estudio.codigo)">
              <input v-model="detalles[estudio.id]" placeholder="Detalle (opcional)" :aria-label="`Detalle para ${estudio.codigo}`" />
              <button class="boton boton--chico boton--peligro" type="submit" :disabled="enCurso">ADN desnaturalizado</button>
            </form>
          </template>
        </TablaEstudios>
      </Estado>
    </div>
  </section>
</template>
