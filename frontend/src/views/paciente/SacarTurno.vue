<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import MapaLeaflet, { type Marcador } from '@/components/MapaLeaflet.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { diaLargo, hora, isoDiaAR, sumarDias } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const router = useRouter()
const estudioId = computed(() => Number(props.id))

const estudio = usarCarga(() => ok(api.GET('/paciente/estudios/{estudio_id}', { params: { path: { estudio_id: estudioId.value } } })))
const { datos: centros, cargando, error } = usarCarga(() => ok(api.GET('/paciente/centros')))
const habilitado = computed(() => ['PAGADO', 'AUTORIZADO'].includes(estudio.datos.value?.estado ?? ''))

const centroId = ref<number | null>(null)
const hoy = isoDiaAR(new Date())
const dia = ref(sumarDias(hoy, 1))
const agenda = ref<Esquemas['AgendaDia'] | null>(null)
const elegido = ref<string | null>(null)
const centro = computed(() => centros.value?.find((c) => c.id === centroId.value) ?? null)

const marcadores = computed<Marcador[]>(() =>
  (centros.value ?? []).map((c) => ({
    id: c.id,
    lat: Number(c.latitud),
    lon: Number(c.longitud),
    titulo: c.nombre,
    detalle: `${c.direccion} · ${c.provincia}`,
    destacado: c.id === centroId.value,
  })),
)

async function cargarAgenda(): Promise<void> {
  elegido.value = null
  if (!centroId.value) return
  agenda.value = await ok(
    api.GET('/paciente/centros/{centro_id}/agenda', { params: { path: { centro_id: centroId.value }, query: { fecha: dia.value } } }),
  )
}
watch([centroId, dia], () => void cargarAgenda())

const { enCurso, error: errorReserva, ejecutar } = usarAccion()
/** E11: reserva el Turno; se generan la orden de extracción y el consentimiento informado. */
async function reservar(): Promise<void> {
  if (!centroId.value || !elegido.value) return
  const r = await ejecutar(() =>
    ok(api.POST('/paciente/turnos', { body: { estudio_id: estudioId.value, centro_id: centroId.value!, inicio: elegido.value! } })),
  )
  if (r) await router.push(`/paciente/estudios/${props.id}/mi-turno?nuevo=1`)
  else await cargarAgenda()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Sacar Turno</h1>
        <p>E11. Turnos de 15 minutos, de lunes a viernes de 9 a 18, sin feriados.</p>
      </div>
      <RouterLink :to="`/paciente/estudios/${id}`" class="boton">Volver al Estudio</RouterLink>
    </div>
    <Alerta v-if="estudio.datos.value && !habilitado" tipo="info">
      Podés sacar Turno cuando el Estudio está Pagado o Autorizado por tu Obra Social.
    </Alerta>
    <Estado v-else :cargando="cargando" :error="error">
      <div class="grilla-2">
        <div class="tarjeta pagina">
          <h2>1. Elegí el Centro de Extracción</h2>
          <MapaLeaflet :marcadores="marcadores" @seleccionar="(id) => (centroId = Number(id))" />
          <label class="campo">
            <span>Centro</span>
            <select v-model="centroId">
              <option :value="null" disabled>Elegí en el mapa o en la lista</option>
              <option v-for="c in centros ?? []" :key="c.id" :value="c.id">{{ c.provincia }} · {{ c.nombre }}</option>
            </select>
          </label>
          <p v-if="centro" class="suave">{{ centro.direccion }}</p>
        </div>
        <div class="tarjeta pagina">
          <h2>2. Elegí el día y el horario</h2>
          <div class="fila">
            <button class="boton boton--chico" type="button" :disabled="dia <= hoy" @click="dia = sumarDias(dia, -1)">‹ Anterior</button>
            <input v-model="dia" type="date" :min="hoy" :max="sumarDias(hoy, 30)" aria-label="Día" style="width: auto" />
            <button class="boton boton--chico" type="button" :disabled="dia >= sumarDias(hoy, 30)" @click="dia = sumarDias(dia, 1)">Siguiente ›</button>
          </div>
          <p v-if="!centroId" class="suave">Primero elegí un Centro.</p>
          <template v-else-if="agenda">
            <p v-if="!agenda.slots.length" class="vacio">No hay Turnos ese día (fin de semana, feriado o fuera de la ventana de 30 días).</p>
            <template v-else>
              <p class="suave">{{ diaLargo(agenda.slots[0]!.inicio) }}</p>
              <div class="slots" role="radiogroup" aria-label="Horarios">
                <button
                  v-for="s in agenda.slots"
                  :key="s.inicio"
                  type="button"
                  class="slot"
                  :class="{ elegido: elegido === s.inicio }"
                  :disabled="!s.libre"
                  role="radio"
                  :aria-checked="elegido === s.inicio"
                  @click="elegido = s.inicio"
                >
                  {{ hora(s.inicio) }}
                </button>
              </div>
            </template>
          </template>
          <Alerta v-if="errorReserva" tipo="error">{{ errorReserva }}</Alerta>
          <button class="boton boton--primario" type="button" :disabled="enCurso || !elegido" @click="reservar">
            {{ elegido ? `Reservar ${hora(elegido)} en ${centro?.nombre}` : 'Reservar Turno' }}
          </button>
        </div>
      </div>
    </Estado>
  </section>
</template>

<style scoped>
.slots { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 6px; }
.slot { min-height: 36px; border: 1px solid var(--color-borde); border-radius: var(--radio-chico); background: var(--color-superficie); color: var(--color-texto); font: inherit; cursor: pointer; }
.slot:hover:not(:disabled) { border-color: var(--color-primario); }
.slot:disabled { text-decoration: line-through; opacity: 0.45; cursor: not-allowed; }
.slot.elegido { background: var(--color-primario); border-color: var(--color-primario); color: #fff; font-weight: 700; }
</style>
