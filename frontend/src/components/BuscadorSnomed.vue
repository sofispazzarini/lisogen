<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'

type Concepto = Esquemas['Concepto']

/**
 * Buscador de síntomas SNOMED CT: autocompleta con las sugerencias de la API de terminología (el backend
 * guarda la clave). `v-model` = conceptos elegidos; el médico sólo elige entre las sugerencias.
 */
const props = withDefaults(defineProps<{ origen?: 'medico' | 'gerente'; multiple?: boolean; etiqueta?: string }>(), {
  origen: 'medico',
  multiple: true,
  etiqueta: 'Síntomas (SNOMED CT)',
})
const elegidos = defineModel<Concepto[]>({ default: () => [] })

const MIN_LETRAS = 3 // la API de SNOMED no busca con menos
const texto = ref('')
const resultados = ref<Concepto[]>([])
const sinResultados = ref(false)
let espera: ReturnType<typeof setTimeout> | null = null

async function buscar(q: string): Promise<void> {
  const consulta = q.trim()
  sinResultados.value = false
  if (consulta.length < MIN_LETRAS) {
    resultados.value = []
    return
  }
  const params = { query: { q: consulta } }
  try {
    const encontrados =
      props.origen === 'medico'
        ? await ok(api.GET('/medico/snomed', { params }))
        : await ok(api.GET('/gerente/snomed', { params }))
    if (texto.value.trim() !== consulta) return // el médico siguió escribiendo: llegó tarde
    resultados.value = encontrados
    sinResultados.value = encontrados.length === 0
  } catch {
    resultados.value = []
  }
}

watch(texto, (q) => {
  if (espera) clearTimeout(espera)
  espera = setTimeout(() => void buscar(q), 400)
})


function elegir(c: Concepto): void {
  if (elegidos.value.some((e) => e.concept_id === c.concept_id)) return
  elegidos.value = props.multiple ? [...elegidos.value, c] : [c]
  texto.value = ''
  resultados.value = []
}

function quitar(id: number): void {
  elegidos.value = elegidos.value.filter((e) => e.concept_id !== id)
}
</script>

<template>
  <div class="campo buscador">
    <span>{{ etiqueta }}</span>
    <div v-if="elegidos.length" class="fila">
      <span v-for="c in elegidos" :key="c.concept_id" class="chip">
        {{ c.termino }} <small>{{ c.concept_id }}</small>
        <button type="button" :aria-label="`Quitar ${c.termino}`" @click="quitar(c.concept_id)">×</button>
      </span>
    </div>
    <input v-model="texto" type="search" placeholder="Escribí al menos 3 letras, p. ej. «cefal» o «me falta el aire»" autocomplete="off" />
    <ul v-if="resultados.length" class="opciones lista-plana" role="listbox">
      <li v-for="c in resultados" :key="c.concept_id">
        <button type="button" class="opcion" @click="elegir(c)">{{ c.termino }} <small class="suave">{{ c.concept_id }}</small></button>
      </li>
    </ul>
    <p v-if="sinResultados" class="suave" role="status">No encontramos ese síntoma en SNOMED.</p>
  </div>
</template>

<style scoped>
.buscador { position: relative; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 4px 2px 10px; border-radius: 999px; background: var(--color-primario-suave); font-size: 0.85rem; }
.chip small { color: var(--color-texto-suave); }
.chip button { border: 0; background: none; cursor: pointer; font-size: 1rem; color: inherit; }
.opciones { position: absolute; top: 100%; left: 0; right: 0; z-index: 20; background: var(--color-superficie); border: 1px solid var(--color-borde); border-radius: var(--radio-chico); box-shadow: var(--sombra); max-height: 240px; overflow-y: auto; gap: 0; }
.opcion { all: unset; display: block; width: 100%; box-sizing: border-box; padding: 8px 10px; cursor: pointer; }
.opcion:hover, .opcion:focus-visible { background: var(--color-primario-suave); }
</style>
