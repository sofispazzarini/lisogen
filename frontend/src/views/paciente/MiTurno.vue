<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import MapaLeaflet from '@/components/MapaLeaflet.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { diaLargo, hora } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const route = useRoute()
const router = useRouter()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
const { datos: turno, cargando, error } = usarCarga(() => ok(api.GET('/paciente/estudios/{estudio_id}/turno', path.value)))
const { datos: centros } = usarCarga(() => ok(api.GET('/paciente/centros')))
const centro = computed(() => centros.value?.find((c) => c.id === turno.value?.centro_id) ?? null)

const cancelacion = usarAccion()
/** E12: libera el horario y el Estudio vuelve a Pagado o Autorizado. */
async function cancelar(): Promise<void> {
  if (!turno.value || !window.confirm('¿Cancelás el Turno? Vas a poder sacar otro.')) return
  const r = await cancelacion.ejecutar(() =>
    ok(api.POST('/paciente/turnos/{turno_id}/cancelar', { params: { path: { turno_id: turno.value!.id } } })),
  )
  if (r) await router.push(`/paciente/estudios/${props.id}/turno`)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Mi Turno</h1>
        <p>Llevá tu DNI, la orden de extracción y el consentimiento informado firmado.</p>
      </div>
      <RouterLink :to="`/paciente/estudios/${id}`" class="boton">Volver al Estudio</RouterLink>
    </div>
    <Alerta v-if="route.query.nuevo" tipo="exito">Reservamos tu Turno. Te vamos a mandar un recordatorio el día anterior.</Alerta>
    <Estado :cargando="cargando" :error="error">
      <div v-if="turno" class="grilla-2">
        <div class="tarjeta pagina">
          <h2>{{ diaLargo(turno.inicio) }} · {{ hora(turno.inicio) }} h</h2>
          <p><strong>{{ turno.centro_nombre }}</strong><br />{{ turno.centro_direccion }}</p>
          <div class="fila">
            <a v-if="turno.orden_extraccion_url" class="boton" :href="turno.orden_extraccion_url" target="_blank" rel="noopener">Orden de extracción (PDF)</a>
            <a v-if="turno.consentimiento_url" class="boton" :href="turno.consentimiento_url" target="_blank" rel="noopener">Consentimiento informado (PDF)</a>
          </div>
          <Alerta v-if="cancelacion.error.value" tipo="error">{{ cancelacion.error.value }}</Alerta>
          <button class="boton boton--peligro" type="button" :disabled="cancelacion.enCurso.value" @click="cancelar">Cancelar Turno</button>
        </div>
        <MapaLeaflet
          v-if="centro"
          :marcadores="[{ id: centro.id, lat: Number(centro.latitud), lon: Number(centro.longitud), titulo: centro.nombre, detalle: centro.direccion, destacado: true }]"
        />
      </div>
    </Estado>
  </section>
</template>
