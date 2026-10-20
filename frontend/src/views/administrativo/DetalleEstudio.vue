<script setup lang="ts">
import { computed } from 'vue'
import { api, ok } from '@/api/cliente'
import BadgeEstado from '@/components/BadgeEstado.vue'
import BadgeUrgente from '@/components/BadgeUrgente.vue'
import Estado from '@/components/Estado.vue'
import Historial from '@/components/Historial.vue'
import LineaPasos from '@/components/LineaPasos.vue'
import { usarCarga } from '@/utils/composables'
import { fechaHora, titulo, usd } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
const { datos: e, cargando, error } = usarCarga(() => ok(api.GET('/administrativo/estudios/{estudio_id}', path.value)))

/** Acceso directo a la acción que el Estudio espera del Laboratorio. */
const accion = computed(() => {
  switch (e.value?.estado) {
    case 'CREADO':
      return { texto: 'Emitir Presupuesto', ruta: '/administrativo/presupuestos' }
    case 'PENDIENTE_AUTORIZACION':
      return { texto: 'Registrar Autorización o Rechazo', ruta: '/administrativo/autorizaciones' }
    case 'EN_ESPERA_RETIRO':
      return { texto: 'Programar retiro con FedEx', ruta: '/administrativo/lotes' }
    case 'EN_VIAJE_COREA':
      return { texto: 'Cargar datos crudos', ruta: '/administrativo/datos-crudos' }
    default:
      return null
  }
})
</script>

<template>
  <section class="pagina">
    <Estado :cargando="cargando" :error="error">
      <template v-if="e">
        <div class="encabezado">
          <div>
            <h1>Estudio {{ e.codigo }} <BadgeUrgente v-if="e.urgente" /></h1>
            <p>{{ e.paciente.nombre_completo }} · {{ e.patologias.join(', ') }} · Médico Tratante: {{ e.medico_tratante.nombre_completo }}</p>
          </div>
          <div class="fila">
            <BadgeEstado :estado="e.estado" />
            <RouterLink v-if="accion" :to="accion.ruta" class="boton boton--primario">{{ accion.texto }}</RouterLink>
          </div>
        </div>
        <div class="tarjeta"><LineaPasos :estado="e.estado" :tipo="e.tipo" /></div>
        <div class="grilla-2">
          <div class="tarjeta">
            <h2>Presupuesto</h2>
            <dl v-if="e.presupuesto">
              <div class="dato"><dt>Modalidad</dt><dd>{{ titulo(e.presupuesto.modalidad) }}<template v-if="e.presupuesto.obra_social"> · {{ e.presupuesto.obra_social }} ({{ e.presupuesto.cobertura_pct }}%)</template></dd></div>
              <div class="dato"><dt>Genes presupuestados</dt><dd>{{ e.presupuesto.cantidad_genes }}</dd></div>
              <div class="dato"><dt>Monto</dt><dd class="monto">{{ usd(e.presupuesto.monto_base_usd) }}</dd></div>
              <div class="dato"><dt>Paciente</dt><dd class="monto">{{ usd(e.presupuesto.monto_a_pagar_usd) }} · {{ e.presupuesto.pagado ? 'pagado' : 'pendiente' }}</dd></div>
            </dl>
            <p v-else class="suave">Sin Presupuesto.</p>
            <template v-if="e.turno">
              <h2 style="margin-top: 16px">Turno</h2>
              <p>{{ fechaHora(e.turno.inicio) }} · {{ e.turno.centro_nombre }}</p>
            </template>
            <h2 style="margin-top: 16px">Genes</h2>
            <p>{{ e.genes.map((g) => g.simbolo + (g.origen === 'HALLAZGO_SECUNDARIO' ? '*' : '')).join(', ') }}</p>
            <small class="suave">* hallazgo secundario (no suma al Presupuesto)</small>
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
