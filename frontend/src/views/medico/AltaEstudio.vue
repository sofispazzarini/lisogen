<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { usd } from '@/utils/formato'

const route = useRoute()
const router = useRouter()
const { datos: pacientes } = usarCarga(() => ok(api.POST('/medico/pacientes/buscar', { body: { texto: '' } })))
const { datos: patologias } = usarCarga(() => ok(api.GET('/medico/patologias')))
const { enCurso, error, ejecutar } = usarAccion()

const form = reactive({
  paciente_id: route.query.paciente ? Number(route.query.paciente) : (null as number | null),
  patologia_ids: [] as number[],
  evalua_hallazgos_secundarios: false,
})
const manuales = ref('')
const sugeridos = ref<Record<number, Esquemas['GenesSugeridos']>>({})

/** E4 ep. 2: el sistema obtiene de la API de bioinformática los genes de cada Patología elegida. */
watch(
  () => [...form.patologia_ids],
  async (ids) => {
    for (const id of ids) {
      if (sugeridos.value[id]) continue
      try {
        sugeridos.value[id] = await ok(api.GET('/medico/patologias/{patologia_id}/genes', { params: { path: { patologia_id: id } } }))
      } catch {
        /* la API de bioinformática no respondió: el backend vuelve a consultarla al guardar */
      }
    }
  },
)

const genesApi = computed(() => [...new Set(form.patologia_ids.flatMap((id) => sugeridos.value[id]?.genes ?? []))])
const genesManuales = computed(() =>
  [...new Set(manuales.value.toUpperCase().split(/[\s,;]+/).filter(Boolean))].filter((g) => !genesApi.value.includes(g)),
)
const hallazgos = computed(() => Object.values(sugeridos.value)[0]?.hallazgos_secundarios ?? [])

/** Estimación del Presupuesto (E16): USD 500 hasta 5 genes + USD 30 por gen adicional; los hallazgos no suman. */
const estimado = computed(() => {
  const n = genesApi.value.length + genesManuales.value.length
  return n ? 500 + 30 * Math.max(0, n - 5) : 0
})

async function enviar(): Promise<void> {
  const estudio = await ejecutar(() =>
    ok(
      api.POST('/medico/estudios', {
        body: {
          paciente_id: form.paciente_id!,
          patologia_ids: form.patologia_ids,
          genes_manuales: genesManuales.value,
          evalua_hallazgos_secundarios: form.evalua_hallazgos_secundarios,
        },
      }),
    ),
  )
  if (estudio) await router.push(`/medico/estudios/${estudio.id}?alta=1`)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Alta Estudio</h1>
        <p>E4. Exoma clínico: genes de la API por cada Patología, más los que agregues a mano.</p>
      </div>
    </div>
    <form class="pagina" @submit.prevent="enviar">
      <div class="tarjeta formulario">
        <label class="campo">
          <span>Paciente</span>
          <select v-model="form.paciente_id" required>
            <option :value="null" disabled>Elegí un Paciente</option>
            <option v-for="p in pacientes ?? []" :key="p.id" :value="p.id">{{ p.nombre_completo }} · DNI {{ p.dni }}</option>
          </select>
          <small>¿No está? <RouterLink to="/medico/pacientes/nuevo">Dalo de alta</RouterLink>.</small>
        </label>
        <fieldset class="campo">
          <legend>Patologías sospechadas</legend>
          <label v-for="p in patologias ?? []" :key="p.id" class="fila">
            <input v-model="form.patologia_ids" type="checkbox" :value="p.id" /> {{ p.nombre }}
            <span v-if="sugeridos[p.id]" class="suave">· {{ sugeridos[p.id]!.genes.join(', ') }}</span>
          </label>
        </fieldset>
        <label class="campo">
          <span>Genes manuales</span>
          <input v-model="manuales" placeholder="Símbolos HGNC separados por coma, p. ej. TP53, MYH7" />
        </label>
        <label class="fila">
          <input v-model="form.evalua_hallazgos_secundarios" type="checkbox" />
          Evaluar hallazgos secundarios<span v-if="hallazgos.length" class="suave"> ({{ hallazgos.join(', ') }}; no suman al Presupuesto)</span>
        </label>
      </div>
      <div class="tarjeta">
        <h2>Resumen</h2>
        <dl>
          <div class="dato"><dt>Genes de la API</dt><dd>{{ genesApi.join(', ') || '—' }}</dd></div>
          <div class="dato"><dt>Genes manuales</dt><dd>{{ genesManuales.join(', ') || '—' }}</dd></div>
          <div class="dato"><dt>Presupuesto estimado</dt><dd class="monto">{{ estimado ? usd(`${estimado}.00`) : '—' }}</dd></div>
        </dl>
        <p class="suave">El Administrativo emite el Presupuesto definitivo con la cobertura de la Obra Social.</p>
      </div>
      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <div class="fila">
        <button class="boton boton--primario" type="submit" :disabled="enCurso || !form.paciente_id || !form.patologia_ids.length">Dar de alta el Estudio</button>
        <RouterLink to="/medico" class="boton">Cancelar</RouterLink>
      </div>
    </form>
  </section>
</template>
