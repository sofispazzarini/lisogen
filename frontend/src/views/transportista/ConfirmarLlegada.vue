<script setup lang="ts">
import { ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const { datos: orden, cargando, error, recargar } = usarCarga(() => ok(api.GET('/transportista/orden-del-dia')))
const { enCurso, error: errorLlegada, ejecutar } = usarAccion()
const resultado = ref<Esquemas['LlegadaSalida'] | null>(null)

/** E25: entrega en el Laboratorio Central; las Muestras entran al Lote y se sella con 10 o un Urgente. */
async function confirmar(): Promise<void> {
  resultado.value = (await ejecutar(() => ok(api.POST('/transportista/llegada')))) ?? null
  if (resultado.value) await recargar()
}
</script>

<template>
  <section class="pagina movil">
    <div class="encabezado">
      <div>
        <h1>Confirmar llegada</h1>
        <p>Al Laboratorio Central, con todas las Muestras recolectadas.</p>
      </div>
    </div>
    <Estado :cargando="cargando" :error="error">
      <template v-if="orden">
        <div v-if="resultado" class="tarjeta pagina">
          <Alerta tipo="exito">Recibimos {{ resultado.recibidas }} Muestra{{ resultado.recibidas === 1 ? '' : 's' }}.</Alerta>
          <Alerta v-if="resultado.volumen_insuficiente.length" tipo="info">
            Con menos de 2 ml (se pidió nueva extracción): {{ resultado.volumen_insuficiente.join(', ') }}.
          </Alerta>
          <p v-if="resultado.lotes_sellados.length">Lotes sellados: <strong>{{ resultado.lotes_sellados.join(', ') }}</strong>.</p>
          <p v-if="resultado.lote_en_formacion" class="suave">Lote en formación: {{ resultado.lote_en_formacion }}.</p>
        </div>
        <Alerta v-else-if="orden.llegada_lab_at" tipo="exito">Ya confirmaste la llegada de hoy.</Alerta>
        <div v-else class="tarjeta pagina">
          <p class="cantidad"><strong>{{ orden.muestras_en_camino }}</strong> Muestras en camino</p>
          <p v-if="orden.paradas.some((p) => p.estado === 'PENDIENTE')" class="suave">
            Todavía te quedan Centros por recolectar.
          </p>
          <Alerta v-if="errorLlegada" tipo="error">{{ errorLlegada }}</Alerta>
          <button class="boton boton--primario grande" type="button" :disabled="enCurso || !orden.muestras_en_camino" @click="confirmar">
            Confirmar llegada con todas las Muestras
          </button>
        </div>
      </template>
    </Estado>
  </section>
</template>

<style scoped>
.movil { max-width: 640px; margin: 0 auto; }
.grande { min-height: 56px; font-size: 1.05rem; }
.cantidad strong { font-size: 2rem; color: var(--color-primario); }
</style>
