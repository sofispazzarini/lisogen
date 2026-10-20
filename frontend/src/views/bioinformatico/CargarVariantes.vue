<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BadgeUrgente from '@/components/BadgeUrgente.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { titulo } from '@/utils/formato'

type Clasif = Esquemas['ClasifVariante']
const CLASIFICACIONES: Clasif[] = ['PATOGENICA', 'SIGNIFICADO_INCIERTO', 'BENIGNA']

const props = defineProps<{ id: string }>()
const router = useRouter()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
const { datos: estudio, cargando, error } = usarCarga(() => ok(api.GET('/bioinformatico/estudios/{estudio_id}', path.value)))

const catalogo = ref<Record<string, Esquemas['VarianteCatalogo'][]>>({})
const seleccion = reactive({ gen: '', nomenclatura: '', clasificacion: 'PATOGENICA' as Clasif })
const variantes = ref<Esquemas['VarianteEntrada'][]>([])
const consulta = usarAccion()
const confirmacion = usarAccion()

/** E28 ep. 1–2: el sistema obtiene de la API de bioinformática las Variantes del gen elegido. */
async function elegirGen(gen: string): Promise<void> {
  seleccion.gen = gen
  seleccion.nomenclatura = ''
  if (catalogo.value[gen]) return
  const r = await consulta.ejecutar(() =>
    ok(api.GET('/bioinformatico/estudios/{estudio_id}/genes/{simbolo}/variantes', { params: { path: { estudio_id: Number(props.id), simbolo: gen } } })),
  )
  if (r) catalogo.value[gen] = r
}

function agregar(): void {
  if (!seleccion.gen || !seleccion.nomenclatura) return
  if (variantes.value.some((v) => v.gen === seleccion.gen && v.nomenclatura === seleccion.nomenclatura)) return
  variantes.value = [...variantes.value, { ...seleccion }]
  seleccion.nomenclatura = ''
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
            <Alerta v-if="consulta.error.value" tipo="error">{{ consulta.error.value }}</Alerta>
            <template v-if="seleccion.gen && catalogo[seleccion.gen]">
              <h2>2. Variante encontrada y clasificación</h2>
              <label class="campo">
                <span>Variante en {{ seleccion.gen }} (API de bioinformática)</span>
                <select v-model="seleccion.nomenclatura">
                  <option value="" disabled>Elegí la Variante</option>
                  <option v-for="v in catalogo[seleccion.gen]" :key="v.nomenclatura" :value="v.nomenclatura">{{ v.nomenclatura }}</option>
                </select>
              </label>
              <fieldset class="campo">
                <legend>Clasificación</legend>
                <label v-for="c in CLASIFICACIONES" :key="c" class="fila"><input v-model="seleccion.clasificacion" type="radio" :value="c" /> {{ titulo(c) }}</label>
              </fieldset>
              <button class="boton" type="button" :disabled="!seleccion.nomenclatura" @click="agregar">Agregar Variante</button>
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
