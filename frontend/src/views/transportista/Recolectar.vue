<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const props = defineProps<{ id: string }>()
const router = useRouter()
const { datos: orden, cargando, error } = usarCarga(() => ok(api.GET('/transportista/orden-del-dia')))
const parada = computed(() => orden.value?.paradas.find((p) => p.id === Number(props.id)) ?? null)
const { enCurso, error: errorRecolectar, ejecutar } = usarAccion()

/** E24: retira las Muestras, marca el Centro como recogido y las Muestras pasan a En camino. */
async function recolectar(): Promise<void> {
  const r = await ejecutar(() =>
    ok(api.POST('/transportista/paradas/{parada_id}/recolectar', { params: { path: { parada_id: Number(props.id) } } })),
  )
  if (r) await router.push('/transportista')
}
</script>

<template>
  <section class="pagina movil">
    <Estado :cargando="cargando" :error="error">
      <template v-if="parada">
        <div class="tarjeta pagina">
          <small class="suave">Parada {{ parada.posicion }} de {{ orden?.paradas.length }}</small>
          <h1>{{ parada.centro.nombre }}</h1>
          <p>{{ parada.centro.direccion }}</p>
          <a
            class="boton"
            :href="`https://www.openstreetmap.org/directions?to=${parada.centro.latitud}%2C${parada.centro.longitud}`"
            target="_blank"
            rel="noopener"
          >Cómo llegar</a>
          <p class="cantidad"><strong>{{ parada.muestras_listas }}</strong> Muestras listas para retirar</p>
          <Alerta v-if="errorRecolectar" tipo="error">{{ errorRecolectar }}</Alerta>
          <button
            v-if="parada.estado === 'PENDIENTE'"
            class="boton boton--primario grande"
            type="button"
            :disabled="enCurso"
            @click="recolectar"
          >
            Retiré las Muestras: marcar como recogido
          </button>
          <Alerta v-else tipo="exito">Este Centro ya está recogido.</Alerta>
        </div>
        <RouterLink to="/transportista" class="boton">Volver a la Orden del Día</RouterLink>
      </template>
      <Alerta v-else tipo="error">Esa parada no está en tu Orden del Día de hoy.</Alerta>
    </Estado>
  </section>
</template>

<style scoped>
.movil { max-width: 640px; margin: 0 auto; }
.grande { min-height: 56px; font-size: 1.05rem; }
.cantidad strong { font-size: 2rem; color: var(--color-primario); }
</style>
