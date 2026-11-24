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
    <header class="encabezado">
      <div>
        <h1>Lotes y retiro de FedEx</h1>
        <p>E20 y E25. Un Lote se sella con 10 Muestras o con un Urgente y viaja a Corea con la autorización del Ministerio de Salud.</p>
      </div>
    </header>
    <Alerta v-if="errorRetiro" tipo="error">{{ errorRetiro }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <Estado :cargando="cargando" :error="error">
      <p v-if="!lotes?.length" class="tarjeta vacio">Todavía no hay Lotes.</p>
      <section v-else class="lotes" aria-label="Lotes">
        <!-- La franja lateral marca el Lote urgente de un vistazo -->
        <article
          v-for="l in lotes"
          :key="l.id"
          class="tarjeta tarjeta--franja lote"
          :class="{ 'tarjeta--urgente': l.incluye_urgente, 'tarjeta--neutra': !l.incluye_urgente && l.estado === 'EN_FORMACION' }"
        >
          <div class="lote-principal">
            <div class="lote-id">
              <h2>{{ l.codigo }}</h2>
              <span v-if="l.incluye_urgente" class="etiqueta-urgente">Urgente</span>
            </div>
            <p class="muestras">
              {{ l.cantidad_muestras }} muestra{{ l.cantidad_muestras === 1 ? '' : 's' }}
              <span v-for="e in l.estudios" :key="e" class="codigo">{{ e }}</span>
            </p>
            <div v-if="l.csv_url || l.autorizacion_url" class="fila">
              <a v-if="l.csv_url" :href="l.csv_url" class="boton" target="_blank" rel="noopener">CSV al Ministerio</a>
              <a v-if="l.autorizacion_url" :href="l.autorizacion_url" class="boton" target="_blank" rel="noopener">Autorización del Ministerio (PDF)</a>
            </div>
            <form v-if="l.estado === 'EN_ESPERA_RETIRO' && !l.retiro_programado_at" class="fila programar" @submit.prevent="programar(l.id, l.codigo)">
              <label class="campo">
                <span>Día y hora del retiro</span>
                <input v-model="momento[l.id]" type="datetime-local" step="900" required />
              </label>
              <button class="boton boton--primario" type="submit" :disabled="enCurso || !momento[l.id]">Programar con FedEx</button>
            </form>
          </div>

          <aside class="lote-lateral">
            <span class="estado-lote" :class="`estado-lote--${l.estado.toLowerCase()}`">{{ titulo(l.estado) }}</span>
            <dl class="datos-lote">
              <div v-if="l.sellado_at"><dt>Sellado</dt><dd>{{ fechaHora(l.sellado_at) }}</dd></div>
              <div v-if="l.retiro_programado_at" class="clave"><dt>Retiro programado</dt><dd>{{ fechaHora(l.retiro_programado_at) }}</dd></div>
              <div v-if="l.fedex_confirmado_at"><dt>FedEx confirmó</dt><dd>{{ fechaHora(l.fedex_confirmado_at) }}</dd></div>
            </dl>
            <a v-if="l.seguimiento_url" :href="l.seguimiento_url" class="seguimiento" target="_blank" rel="noopener">Seguimiento en FedEx</a>
          </aside>
        </article>
      </section>
    </Estado>
  </section>
</template>

<style scoped>
.lotes { display: grid; gap: 16px; }
.lote { display: grid; grid-template-columns: 1fr auto; gap: 24px; }
.lote-id { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 0 0 10px; }
.lote-id h2 { margin: 0; font-size: 21px; font-variant-numeric: tabular-nums; }
.muestras { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 18px; font-size: 14px; color: var(--color-texto-suave); }
.programar { margin-top: 16px; align-items: end; }
.programar .campo { min-width: min(240px, 100%); }
.lote-lateral { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; min-width: 230px; text-align: right; }
.estado-lote { font-weight: 600; color: var(--color-primario); }
.estado-lote--recibido { color: var(--color-acento); }
.estado-lote--en_formacion { color: var(--color-texto-suave); }
.datos-lote { display: grid; gap: 6px; width: 100%; margin: 0; font-size: 14px; }
.datos-lote div { display: flex; justify-content: space-between; gap: 16px; }
.datos-lote dt { color: var(--color-texto-suave); }
.datos-lote dd { margin: 0; font-variant-numeric: tabular-nums; }
/* La fecha de retiro es lo que hay que cumplir */
.datos-lote .clave dd { color: var(--color-primario); font-weight: 600; }
.seguimiento { font-size: 14px; font-weight: 500; }

@media (max-width: 860px) {
  .lote { grid-template-columns: 1fr; }
  .lote-lateral { align-items: flex-start; text-align: left; min-width: 0; }
  .datos-lote div { justify-content: flex-start; flex-wrap: wrap; }
}
</style>
