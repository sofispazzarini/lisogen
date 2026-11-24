<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BadgeUrgente from '@/components/BadgeUrgente.vue'
import Estado from '@/components/Estado.vue'
import { mensajeDeError, usarAccion, usarCarga } from '@/utils/composables'
import { titulo } from '@/utils/formato'

type Clasif = Esquemas['ClasifVariante']
const CLASIFICACIONES: Clasif[] = ['PATOGENICA', 'SIGNIFICADO_INCIERTO', 'BENIGNA']
const TAMANO_PAGINA = 20

const props = defineProps<{ id: string }>()
const router = useRouter()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
const { datos: estudio, cargando, error } = usarCarga(() => ok(api.GET('/bioinformatico/estudios/{estudio_id}', path.value)))

const catalogo = ref<Esquemas['VarianteCatalogo'][]>([])
const seleccion = reactive({ gen: '', nomenclatura: '', clasificacion: null as Clasif | null })
const variantes = ref<Esquemas['VarianteEntrada'][]>([])
const confirmacion = usarAccion()
const filtro = ref('')
const textoBuscado = ref('')
const offset = ref(0)
const hayMas = ref(false)
const buscando = ref(false)
const errorBusqueda = ref<string | null>(null)
let consultaActual = 0

/** E28 ep. 1–2: el sistema obtiene de la API de bioinformática las Variantes del gen elegido. */
async function elegirGen(gen: string): Promise<void> {
  seleccion.gen = gen
  filtro.value = ''
  await buscar()
}

async function buscar(): Promise<void> {
  textoBuscado.value = filtro.value.trim()
  await cargarPagina(0)
}

async function cargarPagina(posicion: number): Promise<void> {
  const consulta = ++consultaActual
  offset.value = posicion
  seleccion.nomenclatura = ''
  seleccion.clasificacion = null
  catalogo.value = []
  hayMas.value = false
  errorBusqueda.value = null
  buscando.value = true
  try {
    const pagina = await ok(api.GET('/bioinformatico/estudios/{estudio_id}/genes/{simbolo}/variantes', {
      params: {
        path: { estudio_id: Number(props.id), simbolo: seleccion.gen },
        query: { q: textoBuscado.value, limite: TAMANO_PAGINA + 1, offset: posicion },
      },
    }))
    if (consulta !== consultaActual) return
    catalogo.value = pagina.slice(0, TAMANO_PAGINA)
    hayMas.value = pagina.length > TAMANO_PAGINA
  } catch (e) {
    if (consulta === consultaActual) errorBusqueda.value = mensajeDeError(e)
  } finally {
    if (consulta === consultaActual) buscando.value = false
  }
}

function agregar(): void {
  const { gen, nomenclatura, clasificacion } = seleccion
  if (!gen || !nomenclatura || !clasificacion) return
  if (variantes.value.some((v) => v.gen === gen && v.nomenclatura === nomenclatura)) return
  variantes.value = [...variantes.value, { gen, nomenclatura, clasificacion }]
  seleccion.nomenclatura = ''
  seleccion.clasificacion = null
}

const esHallazgo = (gen: string) => estudio.value?.genes.find((g) => g.simbolo === gen)?.origen === 'HALLAZGO_SECUNDARIO'

/** Vista previa del tipo de Resultado (la regla la aplica el backend; los hallazgos secundarios no cuentan). */
const tipoPrevisto = computed(() => {
  const c = variantes.value.filter((v) => !esHallazgo(v.gen)).map((v) => v.clasificacion)
  if (c.includes('PATOGENICA')) return 'POSITIVO'
  if (c.includes('SIGNIFICADO_INCIERTO')) return 'NO_CONCLUYENTE'
  return 'NEGATIVO'
})

async function confirmar(): Promise<void> {
  if (!window.confirm(`¿Confirmás el Resultado ${titulo(tipoPrevisto.value)}? Se genera el PDF y se avisa al Médico Tratante y al Paciente.`)) return
  const r = await confirmacion.ejecutar(() =>
    ok(api.POST('/bioinformatico/estudios/{estudio_id}/resultado', { ...path.value, body: { variantes: variantes.value } })),
  )
  if (r) await router.push('/bioinformatico/mis-estudios')
}
</script>

<template>
  <section class="pagina">
    <Estado :cargando="cargando" :error="error">
      <template v-if="estudio">
        <div class="encabezado">
          <div>
            <h1>Cargar Variantes · {{ estudio.codigo }} <BadgeUrgente v-if="estudio.urgente" /></h1>
            <p>
              E28. {{ estudio.patologias.join(', ') }}
              <template v-if="estudio.estudio_origen_codigo"> · Reanálisis del exoma {{ estudio.estudio_origen_codigo }}</template>
            </p>
          </div>
          <a v-if="estudio.datos_crudos_url" :href="estudio.datos_crudos_url" class="boton" target="_blank" rel="noopener">Descargar datos crudos</a>
        </div>
        <Alerta v-if="!estudio.tomado_por_mi" tipo="info">Este Estudio todavía no lo tomaste.</Alerta>
        <div class="grilla-2">
          <div class="tarjeta formulario">
            <h2>1. Gen analizado</h2>
            <div class="fila">
              <button
                v-for="g in estudio.genes"
                :key="g.simbolo"
                type="button"
                class="boton boton--chico"
                :class="{ 'boton--primario': seleccion.gen === g.simbolo }"
                @click="elegirGen(g.simbolo)"
              >
                {{ g.simbolo }}<small v-if="g.origen === 'HALLAZGO_SECUNDARIO'">&nbsp;(hallazgo)</small>
              </button>
            </div>
            <template v-if="seleccion.gen">
              <h2>2. Variante encontrada y clasificación</h2>
              <form class="fila" @submit.prevent="buscar">
                <label class="campo">
                  <span>Buscar por nomenclatura</span>
                  <input v-model="filtro" type="search" placeholder="Ej. c.-32-13T>G" maxlength="120" />
                </label>
                <button class="boton" type="submit">Buscar</button>
              </form>
              <p v-if="buscando" role="status">Buscando variantes…</p>
              <template v-else-if="errorBusqueda">
                <Alerta tipo="error">{{ errorBusqueda }}</Alerta>
                <button class="boton" type="button" @click="cargarPagina(offset)">Reintentar</button>
              </template>
              <p v-else-if="!catalogo.length" role="status">No se encontraron variantes.</p>
              <label v-else class="campo">
                <span>Variante en {{ seleccion.gen }} (API de bioinformática)</span>
                <select v-model="seleccion.nomenclatura" @change="seleccion.clasificacion = null">
                  <option value="" disabled>Elegí la Variante</option>
                  <option v-for="v in catalogo" :key="v.nomenclatura" :value="v.nomenclatura">{{ v.nomenclatura }}</option>
                </select>
              </label>
              <div v-if="!buscando && !errorBusqueda && (offset || hayMas)" class="fila">
                <button class="boton boton--chico" type="button" :disabled="offset === 0" @click="cargarPagina(offset - TAMANO_PAGINA)">Anterior</button>
                <span>Página {{ offset / TAMANO_PAGINA + 1 }}</span>
                <button class="boton boton--chico" type="button" :disabled="!hayMas" @click="cargarPagina(offset + TAMANO_PAGINA)">Siguiente</button>
              </div>
              <fieldset class="campo">
                <legend>Clasificación</legend>
                <label v-for="c in CLASIFICACIONES" :key="c" class="fila"><input v-model="seleccion.clasificacion" type="radio" :value="c" /> {{ titulo(c) }}</label>
              </fieldset>
              <button class="boton" type="button" :disabled="!seleccion.nomenclatura || !seleccion.clasificacion" @click="agregar">Agregar Variante</button>
            </template>
          </div>
          <div class="tarjeta formulario">
            <h2>3. Resultado</h2>
            <ul v-if="variantes.length" class="lista-plana">
              <li v-for="(v, i) in variantes" :key="i" class="fila">
                <strong>{{ v.gen }}</strong> <code>{{ v.nomenclatura }}</code> · {{ titulo(v.clasificacion) }}
                <span v-if="esHallazgo(v.gen)" class="suave">(hallazgo secundario)</span>
                <button class="boton boton--chico" type="button" @click="variantes = variantes.filter((_, j) => j !== i)">Quitar</button>
              </li>
            </ul>
            <p v-else class="suave">Sin Variantes: el Resultado es negativo.</p>
            <p>Resultado previsto: <strong>{{ titulo(tipoPrevisto) }}</strong></p>
            <Alerta v-if="confirmacion.error.value" tipo="error">{{ confirmacion.error.value }}</Alerta>
            <button class="boton boton--primario" type="button" :disabled="confirmacion.enCurso.value || !estudio.tomado_por_mi" @click="confirmar">
              Confirmar Resultado
            </button>
          </div>
        </div>
      </template>
    </Estado>
  </section>
</template>
