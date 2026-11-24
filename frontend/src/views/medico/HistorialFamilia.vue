<script setup lang="ts">
import { api, ok, type Esquemas } from '@/api/cliente'
import BadgeEstado from '@/components/BadgeEstado.vue'
import Estado from '@/components/Estado.vue'
import { usarCarga } from '@/utils/composables'
import { etiquetaParentesco, fecha } from '@/utils/formato'

/** Historial de la familia (SUPUESTO S41): los Pacientes con el mismo número de familia, sus Estudios y
 * resultados, y los familiares que declararon. Sin datos de contacto; cada consulta queda auditada. */
const props = defineProps<{ codigo: string }>()
const { datos, cargando, error } = usarCarga(() =>
  ok(api.GET('/medico/familias/{familia_codigo}', { params: { path: { familia_codigo: props.codigo } } })),
)

const RESULTADO: Record<Esquemas['TipoResultado'], string> = {
  POSITIVO: 'Positivo',
  NEGATIVO: 'Negativo',
  NO_CONCLUYENTE: 'No concluyente',
}

function parentesco(f: Esquemas['FamiliarSalida']): string {
  return etiquetaParentesco(f.parentesco, f.lado)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Historial de la familia {{ codigo }}</h1>
        <p>Pacientes de LisoGen con este número de familia, sus Estudios y los familiares que declararon. La consulta queda registrada.</p>
      </div>
    </div>
    <Estado :cargando="cargando" :error="error">
      <template v-if="datos">
        <div v-for="(m, i) in datos.miembros" :key="i" class="tarjeta">
          <div class="encabezado">
            <div>
              <h2>
                <RouterLink v-if="m.paciente_id" :to="`/medico/pacientes/${m.paciente_id}`">{{ m.nombre_completo }}</RouterLink>
                <template v-else>{{ m.nombre_completo }}</template>
              </h2>
              <p class="suave">
                Nacimiento: {{ fecha(m.fecha_nacimiento) }}
                <template v-if="!m.paciente_id"> · Paciente de otro Médico</template>
              </p>
            </div>
          </div>
          <div v-if="m.estudios.length" class="tabla-contenedor">
            <table class="tabla tabla--apilable">
              <thead><tr><th>Estudio</th><th>Patologías</th><th>Estado</th><th>Resultado</th><th>Fecha</th></tr></thead>
              <tbody>
                <tr v-for="e in m.estudios" :key="e.codigo">
                  <td>{{ e.codigo }}<template v-if="e.tipo === 'REANALISIS'"> (reanálisis)</template></td>
                  <td data-etiqueta="Patologías">{{ e.patologias.join(', ') || '—' }}</td>
                  <td data-etiqueta="Estado"><BadgeEstado :estado="e.estado" /></td>
                  <td data-etiqueta="Resultado">{{ e.resultado ? RESULTADO[e.resultado] : '—' }}</td>
                  <td data-etiqueta="Fecha">{{ fecha(e.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="suave">Sin Estudios.</p>
          <template v-if="m.familiares_declarados.length">
            <h3>Familiares declarados</h3>
            <ul class="lista-plana">
              <li v-for="(f, j) in m.familiares_declarados" :key="j">
                <strong>{{ parentesco(f) }}</strong>: {{ [f.nombre, f.apellido].filter(Boolean).join(' ') }}
                <span v-if="f.patologia_diagnosticada" class="suave"> · diagnóstico de {{ f.patologia_diagnosticada }}</span>
                <span v-if="f.sintomas" class="suave"> · {{ f.sintomas }}</span>
              </li>
            </ul>
          </template>
        </div>
      </template>
    </Estado>
  </section>
</template>
