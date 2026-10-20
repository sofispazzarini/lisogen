<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BadgeEstado from '@/components/BadgeEstado.vue'
import Estado from '@/components/Estado.vue'
import Historial from '@/components/Historial.vue'
import LineaPasos from '@/components/LineaPasos.vue'
import { usarCarga } from '@/utils/composables'
import { accionPaciente } from '@/utils/estados'
import { fechaHora, usd } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const route = useRoute()
const eid = computed(() => Number(props.id))
const { datos: e, cargando, error } = usarCarga(() =>
  ok(api.GET('/paciente/estudios/{estudio_id}', { params: { path: { estudio_id: eid.value } } })),
)
const accion = computed(() => (e.value ? accionPaciente(e.value.estado) : null))
</script>

<template>
  <section class="pagina">
    <Estado :cargando="cargando" :error="error">
      <template v-if="e">
        <div class="encabezado">
          <div>
            <h1>Estudio {{ e.codigo }}</h1>
            <p>{{ e.patologias.join(', ') }} · Médico Tratante: {{ e.medico_tratante.nombre_completo }}</p>
          </div>
          <BadgeEstado :estado="e.estado" />
        </div>
        <Alerta v-if="route.query.pagado" tipo="exito">¡Listo! Registramos tu pago. Ya podés sacar Turno para la extracción.</Alerta>
        <div class="tarjeta pagina">
          <LineaPasos :estado="e.estado" :tipo="e.tipo" />
          <Alerta v-if="e.estado === 'RECHAZADO'" tipo="error">
            La Obra Social rechazó el Estudio<template v-if="e.rechazo_motivo">: {{ e.rechazo_motivo }}</template>. Podés pedir la reautorización con una decisión judicial.
          </Alerta>
          <Alerta v-if="e.reautorizacion_pendiente" tipo="info">Tu pedido de reautorización está en revisión.</Alerta>
          <Alerta v-if="e.inasistencias" tipo="info">
            Registramos {{ e.inasistencias }} inasistencia{{ e.inasistencias > 1 ? 's' : '' }}. Con 5 se pierde el pago y hay que volver a pagar.
          </Alerta>
          <div v-if="accion" class="fila">
            <RouterLink :to="`/paciente/estudios/${e.id}/${accion.ruta}`" class="boton boton--primario">{{ accion.texto }}</RouterLink>
          </div>
        </div>
        <div class="grilla-2">
          <div class="tarjeta">
            <h2>Presupuesto</h2>
            <dl v-if="e.presupuesto">
              <div class="dato"><dt>Monto del Estudio</dt><dd class="monto">{{ usd(e.presupuesto.monto_base_usd) }}</dd></div>
              <div v-if="e.presupuesto.obra_social" class="dato"><dt>Cubre {{ e.presupuesto.obra_social }}</dt><dd class="monto">{{ usd(e.presupuesto.monto_obra_social_usd) }} ({{ e.presupuesto.cobertura_pct }}%)</dd></div>
              <div v-if="e.presupuesto.cupon_codigo" class="dato"><dt>Cupón {{ e.presupuesto.cupon_codigo }}</dt><dd class="monto">-{{ usd(e.presupuesto.descuento_cupon_usd) }}</dd></div>
              <div class="dato"><dt>A tu cargo</dt><dd class="monto">{{ usd(e.presupuesto.monto_a_pagar_usd) }} {{ e.presupuesto.pagado ? '· pagado' : '' }}</dd></div>
            </dl>
            <p v-else class="suave">El Laboratorio todavía no emitió el Presupuesto.</p>
            <template v-if="e.turno">
              <h2 style="margin-top: 16px">Turno</h2>
              <p><strong>{{ fechaHora(e.turno.inicio) }}</strong> en {{ e.turno.centro_nombre }} ({{ e.turno.centro_direccion }})</p>
            </template>
          </div>
          <div class="tarjeta">
            <h2>Historial</h2>
            <Historial :items="e.historial" />
          </div>
        </div>
      </template>
    </Estado>
  </section>
</template>
