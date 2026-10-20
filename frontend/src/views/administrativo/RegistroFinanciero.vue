<script setup lang="ts">
import { api, ok } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import { usarCarga } from '@/utils/composables'
import { fechaHora, titulo, usd } from '@/utils/formato'

const { datos, cargando, error } = usarCarga(() => ok(api.GET('/administrativo/movimientos')))
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Registro financiero</h1>
        <p>Pagos de Pacientes (simulados), pagos de Obras Sociales y pérdidas por inasistencias.</p>
      </div>
    </div>
    <Estado :cargando="cargando" :error="error">
      <template v-if="datos">
        <div class="contadores">
          <div class="tarjeta"><small class="suave">Pacientes</small><strong class="monto">{{ usd(datos.total_pacientes_usd) }}</strong></div>
          <div class="tarjeta"><small class="suave">Obras Sociales</small><strong class="monto">{{ usd(datos.total_obras_sociales_usd) }}</strong></div>
          <div class="tarjeta"><small class="suave">Pérdidas por inasistencias</small><strong class="monto">{{ usd(datos.total_perdidas_usd) }}</strong></div>
        </div>
        <div class="tarjeta tabla-contenedor">
          <table v-if="datos.movimientos.length" class="tabla">
            <thead><tr><th>Fecha</th><th>Estudio</th><th>Concepto</th><th>Obra Social</th><th style="text-align: right">Monto</th></tr></thead>
            <tbody>
              <tr v-for="m in datos.movimientos" :key="m.id">
                <td>{{ fechaHora(m.created_at) }}</td>
                <td>{{ m.estudio_codigo }}</td>
                <td>{{ titulo(m.concepto) }}</td>
                <td>{{ m.obra_social ?? '—' }}</td>
                <td class="monto" style="text-align: right">{{ usd(m.monto_usd) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="vacio">Todavía no hay movimientos.</p>
        </div>
      </template>
    </Estado>
  </section>
</template>

<style scoped>
.contadores { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.contadores .tarjeta { display: grid; gap: 4px; }
.contadores strong { font-size: 1.35rem; }
</style>
