<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { fecha, titulo } from '@/utils/formato'

const { datos: cupones, cargando, error, recargar } = usarCarga(() => ok(api.GET('/medico/cupones')))
const { datos: pacientes } = usarCarga(() => ok(api.POST('/medico/pacientes/buscar', { body: { texto: '' } })))
const { enCurso, error: errorAsignar, exito, ejecutar } = usarAccion()

const disponibles = computed(() => (cupones.value ?? []).filter((c) => c.estado === 'ASIGNADO_MEDICO'))
const paraPaciente = ref<Record<number, number | null>>({})

/** E5: el Cupón pasa al Paciente y deja de estar disponible para el Médico. */
async function asignar(cuponId: number): Promise<void> {
  const pacienteId = paraPaciente.value[cuponId]
  if (!pacienteId) return
  const r = await ejecutar(
    () => ok(api.POST('/medico/cupones/{cupon_id}/asignar', { params: { path: { cupon_id: cuponId } }, body: { paciente_id: pacienteId } })),
    'Cupón asignado. El Paciente lo ve al pagar su Presupuesto.',
  )
  if (r) await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Mis Cupones</h1>
        <p>E5. Cupones que te asignó el Gerente Médico. Cada uno se usa una sola vez.</p>
      </div>
    </div>
    <Alerta v-if="errorAsignar" tipo="error">{{ errorAsignar }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <p v-if="!disponibles.length" class="vacio">No tenés Cupones disponibles para asignar.</p>
        <div v-else class="tabla-contenedor">
          <table class="tabla">
            <thead><tr><th>Código</th><th>Descuento</th><th>Vence</th><th>Asignar a</th></tr></thead>
            <tbody>
              <tr v-for="c in disponibles" :key="c.id">
                <td><code>{{ c.codigo }}</code></td>
                <td>{{ c.descuento_pct }}%</td>
                <td>{{ c.vence_at ? fecha(c.vence_at) : 'Sin vencimiento' }}</td>
                <td>
                  <form class="fila" @submit.prevent="asignar(c.id)">
                    <select v-model="paraPaciente[c.id]" required aria-label="Paciente">
                      <option :value="undefined" disabled>Elegí un Paciente</option>
                      <option v-for="p in pacientes ?? []" :key="p.id" :value="p.id">{{ p.nombre_completo }}</option>
                    </select>
                    <button class="boton boton--primario boton--chico" type="submit" :disabled="enCurso || !paraPaciente[c.id]">Asignar</button>
                  </form>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Estado>
    </div>
    <div v-if="cupones && cupones.length > disponibles.length" class="tarjeta">
      <h2>Ya asignados</h2>
      <ul class="lista-plana">
        <li v-for="c in cupones.filter((x) => x.estado !== 'ASIGNADO_MEDICO')" :key="c.id">
          <code>{{ c.codigo }}</code> · {{ c.descuento_pct }}% · {{ c.paciente ?? '—' }} · {{ titulo(c.estado) }}
        </li>
      </ul>
    </div>
  </section>
</template>
