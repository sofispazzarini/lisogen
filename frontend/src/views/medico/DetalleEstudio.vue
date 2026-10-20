<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BadgeEstado from '@/components/BadgeEstado.vue'
import BadgeUrgente from '@/components/BadgeUrgente.vue'
import Estado from '@/components/Estado.vue'
import Historial from '@/components/Historial.vue'
import LineaPasos from '@/components/LineaPasos.vue'
import ResultadoVista from '@/components/ResultadoVista.vue'
import { usarCarga } from '@/utils/composables'
import { titulo } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const route = useRoute()
const eid = computed(() => Number(props.id))
const path = computed(() => ({ params: { path: { estudio_id: eid.value } } }))

const { datos: estudio, cargando, error } = usarCarga(async () => {
  const e = await ok(api.GET('/medico/estudios/{estudio_id}', path.value))
  if (e.estado === 'FINALIZADO') void cargarResultado()
  return e
})
const resultado = usarCarga(() => ok(api.GET('/medico/estudios/{estudio_id}/resultado', path.value)), false)
const cargarResultado = resultado.recargar
</script>

<template>
  <section class="pagina">
    <Estado :cargando="cargando" :error="error">
      <template v-if="estudio">
        <div class="encabezado">
          <div>
            <h1>Estudio {{ estudio.codigo }} <BadgeUrgente v-if="estudio.urgente" /></h1>
            <p>
              <RouterLink :to="`/medico/pacientes/${estudio.paciente.id}`">{{ estudio.paciente.nombre_completo }}</RouterLink>
              · {{ estudio.patologias.join(', ') }}
              <template v-if="estudio.estudio_origen_codigo"> · Reanálisis de {{ estudio.estudio_origen_codigo }}</template>
            </p>
          </div>
          <BadgeEstado :estado="estudio.estado" />
        </div>
        <Alerta v-if="route.query.alta" tipo="exito">Estudio dado de alta. El Administrativo del Laboratorio va a emitir el Presupuesto.</Alerta>
        <div class="tarjeta"><LineaPasos :estado="estudio.estado" :tipo="estudio.tipo" /></div>

        <div v-if="estudio.estado === 'FINALIZADO'" class="tarjeta">
          <h2>Resultado</h2>
          <Estado :cargando="resultado.cargando.value" :error="resultado.error.value">
            <ResultadoVista v-if="resultado.datos.value" :resultado="resultado.datos.value" />
          </Estado>
        </div>

        <div class="grilla-2">
          <div class="tarjeta">
            <h2>Genes</h2>
            <ul class="lista-plana">
              <li v-for="g in estudio.genes" :key="g.simbolo">
                <strong>{{ g.simbolo }}</strong>
                <span class="suave"> · {{ titulo(g.origen) }}<template v-if="g.patologia"> ({{ g.patologia }})</template></span>
              </li>
            </ul>
          </div>
          <div class="tarjeta">
            <h2>Historial</h2>
            <Historial :items="estudio.historial" />
          </div>
        </div>
      </template>
    </Estado>
  </section>
</template>
