<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import MapaLeaflet, { type Marcador } from '@/components/MapaLeaflet.vue'
import { usarCarga } from '@/utils/composables'
import { fecha } from '@/utils/formato'

const { datos: orden, cargando, error } = usarCarga(() => ok(api.GET('/transportista/orden-del-dia')))
const siguiente = computed(() => orden.value?.paradas.find((p) => p.estado === 'PENDIENTE') ?? null)
const terminado = computed(() => !!orden.value && !siguiente.value)

const marcadores = computed<Marcador[]>(() =>
  (orden.value?.paradas ?? []).map((p) => ({
    id: p.id,
    lat: Number(p.centro.latitud),
    lon: Number(p.centro.longitud),
    titulo: `${p.posicion}. ${p.centro.nombre}`,
    detalle: `${p.centro.direccion} · ${p.muestras_listas} Muestras`,
    destacado: p.id === siguiente.value?.id,
  })),
)

/** Envío de posición para Seguir Muestra (E19): cada 60 s mientras la pantalla está abierta. */
const posicion = ref<'activa' | 'denegada' | 'no-disponible' | null>(null)
let vigilancia: number | null = null
let ultimoEnvio = 0
onMounted(() => {
  if (!('geolocation' in navigator)) {
    posicion.value = 'no-disponible'
    return
  }
  vigilancia = navigator.geolocation.watchPosition(
    (p) => {
      posicion.value = 'activa'
      if (Date.now() - ultimoEnvio < 60_000) return
      ultimoEnvio = Date.now()
      void api.POST('/transportista/posicion', {
        body: { latitud: p.coords.latitude.toFixed(6), longitud: p.coords.longitude.toFixed(6) },
      })
    },
    () => (posicion.value = 'denegada'),
    { enableHighAccuracy: true, maximumAge: 30_000 },
  )
})
onBeforeUnmount(() => vigilancia !== null && navigator.geolocation.clearWatch(vigilancia))
</script>

<template>
  <section class="pagina movil">
    <div class="encabezado">
      <div>
        <h1>Orden del Día</h1>
        <p v-if="orden">{{ fecha(orden.fecha) }} · {{ orden.provincia }} · recorrido fijo</p>
      </div>
    </div>
    <Estado :cargando="cargando" :error="error">
      <template v-if="orden">
        <Alerta v-if="posicion === 'denegada'" tipo="info">Activá la ubicación para que el Laboratorio pueda seguir las Muestras.</Alerta>
        <MapaLeaflet :marcadores="marcadores" ruta />
        <RouterLink v-if="siguiente" :to="`/transportista/paradas/${siguiente.id}`" class="boton boton--primario grande">
          Ir a la parada {{ siguiente.posicion }}: {{ siguiente.centro.nombre }}
        </RouterLink>
        <RouterLink v-else-if="!orden.llegada_lab_at" to="/transportista/llegada" class="boton boton--primario grande">
          Confirmar llegada al Laboratorio Central ({{ orden.muestras_en_camino }} Muestras)
        </RouterLink>
        <Alerta v-else tipo="exito">Entregaste las Muestras de hoy. ¡Gracias!</Alerta>
        <ol class="lista-plana paradas">
          <li v-for="p in orden.paradas" :key="p.id" class="tarjeta parada" :class="{ hecha: p.estado === 'RECOGIDO' }">
            <span class="numero">{{ p.estado === 'RECOGIDO' ? '✓' : p.posicion }}</span>
            <div>
              <strong>{{ p.centro.nombre }}</strong>
              <div class="suave">{{ p.centro.direccion }}</div>
              <small>{{ p.estado === 'RECOGIDO' ? 'Recogido' : `${p.muestras_listas} Muestras listas para retirar` }}</small>
            </div>
          </li>
        </ol>
        <p v-if="terminado && orden.llegada_lab_at === null" class="suave">Recolectaste todos los Centros.</p>
      </template>
    </Estado>
  </section>
</template>

<style scoped>
.movil { max-width: 640px; margin: 0 auto; }
.grande { min-height: 52px; font-size: 1.05rem; text-align: center; }
.paradas { gap: 10px; }
.parada { display: flex; gap: 12px; align-items: center; padding: 12px; }
.parada.hecha { opacity: 0.6; }
.numero { width: 34px; height: 34px; flex: none; border-radius: 50%; display: grid; place-items: center; background: var(--color-primario); color: #fff; font-weight: 700; }
.hecha .numero { background: var(--color-acento); }
</style>
