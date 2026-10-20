<script setup lang="ts">
import type { Esquemas } from '@/api/cliente'
import { fecha } from '@/utils/formato'
import BadgeEstado from './BadgeEstado.vue'
import BadgeUrgente from './BadgeUrgente.vue'

type Estudio = Esquemas['EstudioResumen']

withDefaults(
  defineProps<{
    estudios: Estudio[]
    enlace?: (e: Estudio) => string
    mostrarPaciente?: boolean
    mostrarMedico?: boolean
    vacio?: string
  }>(),
  { enlace: undefined, mostrarPaciente: true, mostrarMedico: false, vacio: 'No hay Estudios para mostrar.' },
)
</script>

<template>
  <div class="tabla-contenedor">
    <table v-if="estudios.length" class="tabla">
      <thead>
        <tr>
          <th>Estudio</th>
          <th v-if="mostrarPaciente">Paciente</th>
          <th v-if="mostrarMedico">Médico Tratante</th>
          <th>Patologías</th>
          <th>Estado</th>
          <th>Alta</th>
          <th v-if="$slots.acciones"><span class="sr">Acciones</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in estudios" :key="e.id" :data-estudio="e.id">
          <td>
            <RouterLink v-if="enlace" :to="enlace(e)">{{ e.codigo }}</RouterLink>
            <span v-else>{{ e.codigo }}</span>
            <span v-if="e.tipo === 'REANALISIS'" class="suave"> · Reanálisis</span>
            <BadgeUrgente v-if="e.urgente" class="ml" />
          </td>
          <td v-if="mostrarPaciente">{{ e.paciente.nombre_completo }}</td>
          <td v-if="mostrarMedico">{{ e.medico_tratante.nombre_completo }}</td>
          <td>{{ e.patologias.join(', ') || '—' }}</td>
          <td><BadgeEstado :estado="e.estado" /></td>
          <td>{{ fecha(e.created_at) }}</td>
          <td v-if="$slots.acciones"><slot name="acciones" :estudio="e" /></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="vacio">{{ vacio }}</p>
  </div>
</template>

<style scoped>
.ml { margin-left: 6px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
