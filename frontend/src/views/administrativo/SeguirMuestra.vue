<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import MapaLeaflet, { type Marcador } from '@/components/MapaLeaflet.vue'
import { usarAccion } from '@/utils/composables'
import { fechaHora, titulo } from '@/utils/formato'

const texto = ref('')
const muestras = ref<Esquemas['MuestraSalida'][] | null>(null)
const ubicacion = ref<Esquemas['UbicacionMuestra'] | null>(null)
const elegida = ref<Esquemas['MuestraSalida'] | null>(null)
const busqueda = usarAccion()
const mapa = usarAccion()
let refresco: ReturnType<typeof setInterval> | null = null

/** E19 ep. 1: búsqueda por Paciente (por POST: el DNI o el apellido no van en la URL). */
async function buscar(): Promise<void> {
  muestras.value = (await busqueda.ejecutar(() => ok(api.POST('/administrativo/muestras/buscar', { body: { texto: texto.value } })))) ?? null
}

async function ubicar(m: Esquemas['MuestraSalida']): Promise<void> {
  elegida.value = m
  ubicacion.value =
    (await mapa.ejecutar(() =>
      ok(api.GET('/administrativo/muestras/{muestra_id}/ubicacion', { params: { path: { muestra_id: m.id } } })),
    )) ?? null
  if (refresco) clearInterval(refresco)
  // En camino, la posición del Transportista se actualiza sola cada 30 segundos.
  if (m.estado === 'EN_CAMINO_LAB_CENTRAL') refresco = setInterval(() => void ubicar(m), 30_000)
}
onBeforeUnmount(() => refresco && clearInterval(refresco))

const marcadores = computed<Marcador[]>(() =>
  ubicacion.value
    ? [{ id: ubicacion.value.muestra_id, lat: Number(ubicacion.value.latitud), lon: Number(ubicacion.value.longitud), titulo: ubicacion.value.descripcion, destacado: true }]
    : [],
)
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Seguir Muestra en mapa</h1>
        <p>E19. Buscá por Paciente o por código de Estudio.</p>
      </div>
    </div>
    <div class="tarjeta pagina">
      <form class="fila" @submit.prevent="buscar">
        <input v-model="texto" type="search" placeholder="Apellido, DNI o código de Estudio" aria-label="Buscar Muestra" style="flex: 1" />
        <button class="boton boton--primario" type="submit" :disabled="busqueda.enCurso.value">Buscar</button>
      </form>
      <Alerta v-if="busqueda.error.value" tipo="error">{{ busqueda.error.value }}</Alerta>
      <div v-if="muestras" class="tabla-contenedor">
        <table v-if="muestras.length" class="tabla">
          <thead><tr><th>Estudio</th><th>Paciente</th><th>Extracción</th><th>Centro</th><th>Estado</th><th></th></tr></thead>
          <tbody>
            <tr v-for="m in muestras" :key="m.id">
              <td>{{ m.estudio_codigo }}</td>
              <td>{{ m.paciente }}</td>
              <td>N.º {{ m.nro_extraccion }} · {{ m.volumen_ml }} ml</td>
              <td>{{ m.centro }}</td>
              <td>{{ titulo(m.estado) }}<template v-if="m.lote_codigo"> · {{ m.lote_codigo }}</template></td>
              <td><button class="boton boton--chico" type="button" @click="ubicar(m)">Ver en el mapa</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="vacio">No encontramos Muestras.</p>
      </div>
    </div>
    <div v-if="elegida" class="grilla-2">
      <MapaLeaflet :marcadores="marcadores" />
      <div class="tarjeta">
        <h2>Muestra de {{ elegida.estudio_codigo }}</h2>
        <Alerta v-if="mapa.error.value" tipo="error">{{ mapa.error.value }}</Alerta>
        <dl v-if="ubicacion">
          <div class="dato"><dt>Dónde está</dt><dd>{{ ubicacion.descripcion }}</dd></div>
          <div class="dato"><dt>Transportista</dt><dd>{{ ubicacion.transportista ?? '—' }}</dd></div>
          <div class="dato"><dt>Actualizado</dt><dd>{{ fechaHora(ubicacion.actualizada_at) }}</dd></div>
        </dl>
      </div>
    </div>
  </section>
</template>
