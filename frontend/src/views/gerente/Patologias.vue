<script setup lang="ts">
import { ref } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BuscadorSnomed from '@/components/BuscadorSnomed.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

type Patologia = Esquemas['PatologiaSalida']
type Concepto = Esquemas['Concepto']

const { datos: patologias, cargando, error, recargar } = usarCarga(() => ok(api.GET('/gerente/patologias')))
const { enCurso, error: errorGuardar, exito, ejecutar } = usarAccion()

const editando = ref<Patologia | null>(null)
const abierto = ref(false)
const nombre = ref('')
const esPompe = ref(false)
const cardinal = ref<Concepto[]>([])
const secundarios = ref<Concepto[]>([])

function abrir(p: Patologia | null): void {
  editando.value = p
  abierto.value = true
  nombre.value = p?.nombre ?? ''
  esPompe.value = p?.es_pompe ?? false
  cardinal.value = p ? [p.sintoma_cardinal] : []
  secundarios.value = p ? [...p.secundarios] : []
  exito.value = null
}

/** E30 (alta) y E31 (modificación): síntoma cardinal y al menos dos secundarios. */
async function guardar(): Promise<void> {
  const body = {
    nombre: nombre.value,
    sintoma_cardinal_id: cardinal.value[0]!.concept_id,
    secundarios_ids: secundarios.value.map((s) => s.concept_id),
    es_pompe: esPompe.value,
  }
  const r = await ejecutar(
    () =>
      editando.value
        ? ok(api.PUT('/gerente/patologias/{patologia_id}', { params: { path: { patologia_id: editando.value.id } }, body }))
        : ok(api.POST('/gerente/patologias', { body })),
    editando.value ? 'Patología modificada.' : 'Patología dada de alta.',
  )
  if (r) {
    abierto.value = false
    await recargar()
  }
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Patologías</h1>
        <p>E30 y E31. Los síntomas definen Validar Diagnóstico en el alta de Pacientes.</p>
      </div>
      <button class="boton boton--primario" type="button" @click="abrir(null)">Nueva Patología</button>
    </div>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>

    <form v-if="abierto" class="tarjeta formulario" @submit.prevent="guardar">
      <h2>{{ editando ? `Modificar ${editando.nombre}` : 'Nueva Patología' }}</h2>
      <label class="campo"><span>Nombre</span><input v-model="nombre" required /></label>
      <BuscadorSnomed v-model="cardinal" origen="gerente" :multiple="false" etiqueta="Síntoma cardinal" />
      <BuscadorSnomed v-model="secundarios" origen="gerente" etiqueta="Síntomas secundarios (al menos dos)" />
      <label class="fila"><input v-model="esPompe" type="checkbox" /> Es Pompe (activa la regla de Urgente en menores de 4 meses)</label>
      <Alerta v-if="errorGuardar" tipo="error">{{ errorGuardar }}</Alerta>
      <div class="fila">
        <button class="boton boton--primario" type="submit" :disabled="enCurso || !cardinal.length || secundarios.length < 2 || !nombre.trim()">Guardar</button>
        <button class="boton" type="button" @click="abierto = false">Cancelar</button>
      </div>
    </form>

    <Estado :cargando="cargando" :error="error">
      <div class="grilla-2">
        <article v-for="p in patologias ?? []" :key="p.id" class="tarjeta">
          <div class="encabezado">
            <h2>{{ p.nombre }} <small v-if="p.es_pompe" class="suave">· regla de Urgente</small></h2>
            <button class="boton boton--chico" type="button" @click="abrir(p)">Modificar</button>
          </div>
          <dl>
            <div class="dato"><dt>Síntoma cardinal</dt><dd>{{ p.sintoma_cardinal.termino }}</dd></div>
            <div class="dato"><dt>Secundarios</dt><dd>{{ p.secundarios.map((s) => s.termino).join(', ') }}</dd></div>
            <div class="dato"><dt>Genes (API)</dt><dd>{{ p.genes.join(', ') || '—' }}</dd></div>
          </dl>
        </article>
      </div>
    </Estado>
  </section>
</template>
