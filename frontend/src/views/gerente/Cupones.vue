<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { fecha, titulo } from '@/utils/formato'

const cupones = usarCarga(() => ok(api.GET('/gerente/cupones')))
const medicos = usarCarga(() => ok(api.GET('/gerente/medicos')))
const generacion = usarAccion()
const asignacion = usarAccion()

const nuevo = reactive({ descuento_pct: 20, cantidad: 5, vence: '' })
const seleccion = ref<number[]>([])
const medicoId = ref<number | null>(null)
const disponibles = computed(() => (cupones.datos.value ?? []).filter((c) => c.estado === 'DISPONIBLE'))

/** E32: el módulo de cupones genera los códigos (PDF con QR o, si falla, código numérico). */
async function generar(): Promise<void> {
  const r = await generacion.ejecutar(
    () =>
      ok(
        api.POST('/gerente/cupones', {
          body: {
            descuento_pct: nuevo.descuento_pct,
            cantidad: nuevo.cantidad,
            vence_at: nuevo.vence ? `${nuevo.vence}T23:59:59-03:00` : null,
          },
        }),
      ),
    'Cupones generados.',
  )
  if (r) await cupones.recargar()
}

/** E33: los Cupones elegidos pasan a estar disponibles para el Médico Tratante. */
async function asignar(): Promise<void> {
  if (!medicoId.value || !seleccion.value.length) return
  const r = await asignacion.ejecutar(
    () => ok(api.POST('/gerente/cupones/asignar', { body: { cupon_ids: seleccion.value, medico_id: medicoId.value! } })),
    'Cupones asignados. El Médico Tratante recibió un Aviso.',
  )
  if (r) {
    seleccion.value = []
    await Promise.all([cupones.recargar(), medicos.recargar()])
  }
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Cupones</h1>
        <p>E32 y E33. Cada Cupón se usa una sola vez y aplica su descuento sobre lo que paga el Paciente.</p>
      </div>
    </div>
    <div class="grilla-2">
      <form class="tarjeta formulario" @submit.prevent="generar">
        <h2>Generar Cupones</h2>
        <div class="grilla-2">
          <label class="campo"><span>Descuento (%)</span><input v-model.number="nuevo.descuento_pct" type="number" min="1" max="100" required /></label>
          <label class="campo"><span>Cantidad</span><input v-model.number="nuevo.cantidad" type="number" min="1" max="100" required /></label>
        </div>
        <label class="campo"><span>Vencimiento (opcional)</span><input v-model="nuevo.vence" type="date" /></label>
        <Alerta v-if="generacion.error.value" tipo="error">{{ generacion.error.value }}</Alerta>
        <Alerta v-if="generacion.exito.value" tipo="exito">{{ generacion.exito.value }}</Alerta>
        <button class="boton boton--primario" type="submit" :disabled="generacion.enCurso.value">Generar</button>
      </form>
      <form class="tarjeta formulario" @submit.prevent="asignar">
        <h2>Asignar a un Médico Tratante</h2>
        <label class="campo">
          <span>Médico Tratante</span>
          <select v-model="medicoId" required>
            <option :value="null" disabled>Elegí un Médico</option>
            <option v-for="m in medicos.datos.value ?? []" :key="m.id" :value="m.id">
              {{ m.nombre_completo }} · {{ m.matricula }} ({{ m.cupones_disponibles }} disponibles)
            </option>
          </select>
        </label>
        <p class="suave">{{ seleccion.length }} Cupón(es) elegidos de {{ disponibles.length }} disponibles. Elegilos en la tabla.</p>
        <Alerta v-if="asignacion.error.value" tipo="error">{{ asignacion.error.value }}</Alerta>
        <Alerta v-if="asignacion.exito.value" tipo="exito">{{ asignacion.exito.value }}</Alerta>
        <button class="boton boton--primario" type="submit" :disabled="asignacion.enCurso.value || !medicoId || !seleccion.length">Asignar</button>
      </form>
    </div>
    <div class="tarjeta">
      <Estado :cargando="cupones.cargando.value" :error="cupones.error.value">
        <div class="tabla-contenedor">
          <table v-if="cupones.datos.value?.length" class="tabla">
            <thead><tr><th></th><th>Código</th><th>Descuento</th><th>Estado</th><th>Médico</th><th>Paciente</th><th>Vence</th><th>QR</th></tr></thead>
            <tbody>
              <tr v-for="c in cupones.datos.value" :key="c.id">
                <td><input v-if="c.estado === 'DISPONIBLE'" v-model="seleccion" type="checkbox" :value="c.id" :aria-label="`Elegir ${c.codigo}`" /></td>
                <td><code>{{ c.codigo }}</code></td>
                <td>{{ c.descuento_pct }}%</td>
                <td>{{ titulo(c.estado) }}</td>
                <td>{{ c.medico ?? '—' }}</td>
                <td>{{ c.paciente ?? '—' }}</td>
                <td>{{ c.vence_at ? fecha(c.vence_at) : '—' }}</td>
                <td><a v-if="c.qr_url" :href="c.qr_url" target="_blank" rel="noopener">PDF</a><span v-else class="suave">Código numérico</span></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="vacio">Todavía no generaste Cupones.</p>
        </div>
      </Estado>
    </div>
  </section>
</template>
