<script setup lang="ts">
import { api, ok } from '@/api/cliente'
import BadgeEstado from '@/components/BadgeEstado.vue'
import BadgeUrgente from '@/components/BadgeUrgente.vue'
import Estado from '@/components/Estado.vue'
import LineaPasos from '@/components/LineaPasos.vue'
import { usarCarga } from '@/utils/composables'
import { accionPaciente } from '@/utils/estados'
import { fecha } from '@/utils/formato'

const { datos, cargando, error } = usarCarga(() => ok(api.GET('/paciente/estudios')))
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Mis Estudios</h1>
        <p>Seguí cada paso de tu Estudio genético. Te avisamos por mail en cada cambio.</p>
      </div>
    </div>
    <Estado :cargando="cargando" :error="error">
      <p v-if="!datos?.length" class="tarjeta vacio">Todavía no tenés Estudios. Tu Médico Tratante los da de alta en la consulta.</p>
      <article v-for="e in datos ?? []" :key="e.id" class="tarjeta pagina">
        <div class="encabezado">
          <div>
            <h2>
              <RouterLink :to="`/paciente/estudios/${e.id}`">Estudio {{ e.codigo }}</RouterLink>
              <BadgeUrgente v-if="e.urgente" />
            </h2>
            <p>{{ e.patologias.join(', ') }} · Dr./Dra. {{ e.medico_tratante.nombre_completo }} · {{ fecha(e.created_at) }}</p>
          </div>
          <BadgeEstado :estado="e.estado" />
        </div>
        <LineaPasos :estado="e.estado" :tipo="e.tipo" />
        <div class="fila">
          <RouterLink v-if="accionPaciente(e.estado)" :to="`/paciente/estudios/${e.id}/${accionPaciente(e.estado)!.ruta}`" class="boton boton--primario">
            {{ accionPaciente(e.estado)!.texto }}
          </RouterLink>
          <RouterLink :to="`/paciente/estudios/${e.id}`" class="boton">Ver detalle</RouterLink>
        </div>
      </article>
    </Estado>
  </section>
</template>
