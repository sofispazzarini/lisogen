<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { fechaHora, titulo } from '@/utils/formato'

const { datos: lotes, cargando, error, recargar } = usarCarga(() => ok(api.GET('/administrativo/lotes')))
const { enCurso, error: errorRetiro, exito, ejecutar } = usarAccion()
const momento = ref<Record<number, string>>({})

/** E20: día y hora de retiro (L–V 9 a 18, sin feriados), también con Urgentes. Hora Argentina. */
async function programar(id: number, codigo: string): Promise<void> {
  const local = momento.value[id]
  if (!local) return
  const r = await ejecutar(
    () =>
      ok(api.POST('/administrativo/lotes/{lote_id}/retiro', { params: { path: { lote_id: id } }, body: { fecha_hora: `${local}:00-03:00` } })),
    `Retiro del Lote ${codigo} programado con FedEx.`,
  )
  if (r) await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Lotes y retiro de FedEx</h1>
        <p>E20 y E25. Un Lote se sella con 10 Muestras o con un Urgente y viaja a Corea con la autorización del Ministerio de Salud.</p>
      </div>
    </div>
    <Alerta v-if="errorRetiro" tipo="error">{{ errorRetiro }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <Estado :cargando="cargando" :error="error">
      <p v-if="!lotes?.length" class="tarjeta vacio">Todavía no hay Lotes.</p>
      <article v-for="l in lotes ?? []" :key="l.id" class="tarjeta pagina">
        <div class="encabezado">
          <div>
            <h2>{{ l.codigo }} <span v-if="l.incluye_urgente" class="urgente">Urgente</span></h2>
            <p>{{ l.cantidad_muestras }} Muestra{{ l.cantidad_muestras === 1 ? '' : 's' }}: {{ l.estudios.join(', ') }}</p>
          </div>
          <strong>{{ titulo(l.estado) }}</strong>
        </div>
        <div class="fila">
          <span v-if="l.sellado_at" class="suave">Sellado {{ fechaHora(l.sellado_at) }}</span>
          <a v-if="l.csv_url" :href="l.csv_url" class="boton boton--chico" target="_blank" rel="noopener">CSV al Ministerio</a>
          <a v-if="l.autorizacion_url" :href="l.autorizacion_url" class="boton boton--chico" target="_blank" rel="noopener">Autorización del Ministerio (PDF)</a>
        </div>
        <p v-if="l.retiro_programado_at" class="suave">
          Retiro programado: <strong>{{ fechaHora(l.retiro_programado_at) }}</strong>
          <template v-if="l.fedex_confirmado_at"> · FedEx confirmó el {{ fechaHora(l.fedex_confirmado_at) }}</template>
        </p>
        <form v-if="l.estado === 'EN_ESPERA_RETIRO'" class="fila" @submit.prevent="programar(l.id, l.codigo)">
          <label class="campo">
            <span>{{ l.retiro_programado_at ? 'Reprogramar retiro' : 'Día y hora del retiro' }}</span>
            <input v-model="momento[l.id]" type="datetime-local" step="900" required />
          </label>
          <button class="boton boton--primario" type="submit" :disabled="enCurso || !momento[l.id]">Programar con FedEx</button>
        </form>
      </article>
    </Estado>
  </section>
</template>

<style scoped>
.urgente { background: var(--color-urgente); color: #fff; border-radius: 999px; padding: 1px 8px; font-size: 0.75rem; vertical-align: middle; }
form .campo { min-width: 240px; }
</style>
