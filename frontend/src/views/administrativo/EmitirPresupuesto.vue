<script setup lang="ts">
import { ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { titulo, usd } from '@/utils/formato'

const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/administrativo/estudios', { params: { query: { estado: 'CREADO' } } })),
)
const elegido = ref<Esquemas['EstudioResumen'] | null>(null)
const previo = ref<Esquemas['PresupuestoPrevio'] | null>(null)
const calculo = usarAccion()
const emision = usarAccion()

/** E16 ep. 2–3: calcula el monto por genes y consulta la cobertura a la API de obras sociales. */
async function calcular(e: Esquemas['EstudioResumen']): Promise<void> {
  elegido.value = e
  previo.value = null
  emision.exito.value = null
  previo.value =
    (await calculo.ejecutar(() =>
      ok(api.GET('/administrativo/estudios/{estudio_id}/presupuesto/previo', { params: { path: { estudio_id: e.id } } })),
    )) ?? null
}

async function emitir(): Promise<void> {
  if (!elegido.value) return
  const codigo = elegido.value.codigo
  const r = await emision.ejecutar(() =>
    ok(api.POST('/administrativo/estudios/{estudio_id}/presupuesto', { params: { path: { estudio_id: elegido.value!.id } } })),
  )
  if (r) {
    emision.exito.value = `Presupuesto del Estudio ${codigo} emitido: ${
      r.modalidad === 'PARTICULAR' ? 'queda Por Pagar.' : 'queda Pendiente de Autorización de la Obra Social.'
    }`
    elegido.value = null
    previo.value = null
    await recargar()
  }
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Emitir Presupuesto</h1>
        <p>E16. USD 500 hasta 5 genes y USD 30 por gen adicional; los hallazgos secundarios no suman.</p>
      </div>
    </div>
    <Alerta v-if="emision.exito.value" tipo="exito">{{ emision.exito.value }}</Alerta>
    <div class="grilla-2">
      <div class="tarjeta">
        <h2>Estudios en estado Creado</h2>
        <Estado :cargando="cargando" :error="error">
          <TablaEstudios :estudios="datos ?? []" vacio="No hay Estudios esperando Presupuesto.">
            <template #acciones="{ estudio }">
              <button class="boton boton--chico" type="button" @click="calcular(estudio)">Calcular</button>
            </template>
          </TablaEstudios>
        </Estado>
      </div>
      <div class="tarjeta formulario">
        <h2>Presupuesto {{ elegido ? `de ${elegido.codigo}` : '' }}</h2>
        <p v-if="!elegido" class="suave">Elegí un Estudio para calcular el Presupuesto.</p>
        <Alerta v-if="calculo.error.value" tipo="error">{{ calculo.error.value }}</Alerta>
        <template v-if="previo">
          <dl>
            <div class="dato"><dt>Genes</dt><dd>{{ previo.cantidad_genes }}</dd></div>
            <div class="dato"><dt>Monto</dt><dd class="monto">{{ usd(previo.monto_base_usd) }}</dd></div>
            <div class="dato"><dt>Modalidad</dt><dd>{{ titulo(previo.modalidad) }}</dd></div>
            <div v-if="previo.obra_social" class="dato"><dt>{{ previo.obra_social }}</dt><dd class="monto">{{ previo.cobertura_pct }}% · {{ usd(previo.monto_obra_social_usd) }}</dd></div>
            <div class="dato"><dt>A cargo del Paciente</dt><dd class="monto">{{ usd(previo.monto_a_pagar_usd) }}</dd></div>
          </dl>
          <Alerta v-if="emision.error.value" tipo="error">{{ emision.error.value }}</Alerta>
          <button class="boton boton--primario" type="button" :disabled="emision.enCurso.value" @click="emitir">Emitir Presupuesto</button>
        </template>
      </div>
    </div>
  </section>
</template>
