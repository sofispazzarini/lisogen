<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import FormFamiliares from '@/components/FormFamiliares.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { etiquetaParentesco, fecha, titulo } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const route = useRoute()
const router = useRouter()
const pid = computed(() => Number(props.id))

const { datos: ficha, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/medico/pacientes/{paciente_id}', { params: { path: { paciente_id: pid.value } } })),
)
const { datos: patologias } = usarCarga(() => ok(api.GET('/medico/patologias')))

// E3: agregar familiares y regenerar el Familiograma
const familiares = ref<Esquemas['FamiliarEntrada'][]>([])
const familiograma = usarAccion()
async function cargarFamiliograma(): Promise<void> {
  const r = await familiograma.ejecutar(
    () =>
      ok(
        api.POST('/medico/pacientes/{paciente_id}/familiograma', {
          params: { path: { paciente_id: pid.value } },
          body: { familiares: familiares.value.filter((f) => f.nombre.trim()) },
        }),
      ),
    'Familiograma actualizado.',
  )
  if (r) {
    familiares.value = []
    await recargar()
  }
}

// Historial de la familia (SUPUESTO S41): unir al Paciente a la familia de otro con su número
const familia = reactive({ codigo: '', editando: false })
const accionFamilia = usarAccion()
async function vincularFamilia(): Promise<void> {
  const r = await accionFamilia.ejecutar(
    () =>
      ok(
        api.PUT('/medico/pacientes/{paciente_id}/familia', {
          params: { path: { paciente_id: pid.value } },
          body: { familia_codigo: familia.codigo.trim() },
        }),
      ),
    'Paciente vinculado a la familia.',
  )
  if (r) {
    familia.codigo = ''
    familia.editando = false
    await recargar()
  }
}

// E6: Reanálisis de un Estudio Finalizado
const finalizados = computed(() => (ficha.value?.estudios ?? []).filter((e) => e.estado === 'FINALIZADO'))
const reanalisis = reactive({ estudio_id: null as number | null, patologia_ids: [] as number[], genes: '' })
const accionReanalisis = usarAccion()
async function solicitarReanalisis(): Promise<void> {
  if (!reanalisis.estudio_id) return
  const nuevo = await accionReanalisis.ejecutar(() =>
    ok(
      api.POST('/medico/estudios/{estudio_id}/reanalisis', {
        params: { path: { estudio_id: reanalisis.estudio_id! } },
        body: {
          patologia_ids: reanalisis.patologia_ids,
          genes_manuales: reanalisis.genes.split(/[\s,;]+/).filter(Boolean),
        },
      }),
    ),
  )
  if (nuevo) await router.push(`/medico/estudios/${nuevo.id}`)
}
</script>

<template>
  <section class="pagina">
    <Estado :cargando="cargando" :error="error">
      <template v-if="ficha">
        <div class="encabezado">
          <div>
            <h1>{{ ficha.nombre }} {{ ficha.apellido }}</h1>
            <p>DNI {{ ficha.dni }} · {{ ficha.obra_social ?? 'Particular' }}<template v-if="ficha.nro_afiliado"> · Afiliado {{ ficha.nro_afiliado }}</template></p>
          </div>
          <RouterLink :to="`/medico/estudios/nuevo?paciente=${ficha.id}`" class="boton boton--primario">Alta Estudio</RouterLink>
        </div>
        <Alerta v-if="route.query.alta" tipo="exito">Paciente dado de alta. Le enviamos por mail sus credenciales de acceso.</Alerta>

        <div class="grilla-2">
          <div class="tarjeta">
            <h2>Datos</h2>
            <dl>
              <div class="dato">
                <dt>Familia</dt>
                <dd>
                  <strong>{{ ficha.familia_codigo }}</strong> ·
                  <RouterLink :to="`/medico/familias/${ficha.familia_codigo}`">Ver historial de la familia</RouterLink> ·
                  <button class="enlace" type="button" @click="familia.editando = !familia.editando">Vincular a otra familia</button>
                </dd>
              </div>
              <form v-if="familia.editando" class="fila" @submit.prevent="vincularFamilia">
                <input v-model="familia.codigo" placeholder="FAM-000123" aria-label="Número de familia" pattern="\s*[Ff][Aa][Mm]-\d{6}\s*" required />
                <button class="boton boton--chico" type="submit" :disabled="accionFamilia.enCurso.value">Vincular</button>
              </form>
              <Alerta v-if="accionFamilia.error.value" tipo="error">{{ accionFamilia.error.value }}</Alerta>
              <Alerta v-if="accionFamilia.exito.value" tipo="exito">{{ accionFamilia.exito.value }}</Alerta>
              <div class="dato"><dt>Nacimiento</dt><dd>{{ fecha(ficha.fecha_nacimiento) }}<template v-if="ficha.es_menor_al_alta"> (menor de edad al alta)</template></dd></div>
              <div class="dato"><dt>Teléfono</dt><dd>{{ ficha.telefono }}</dd></div>
              <div class="dato"><dt>Mail de contacto</dt><dd>{{ ficha.email_contacto }}</dd></div>
              <div class="dato">
                <dt>Diagnóstico presuntivo</dt>
                <dd>{{ ficha.diagnosticos.map((d) => `${d.patologia} (sospecha ${titulo(d.tipo_sospecha).toLowerCase()})`).join(', ') }}</dd>
              </div>
              <div class="dato"><dt>Síntomas</dt><dd>{{ ficha.sintomas.map((s) => s.termino).join(', ') }}</dd></div>
            </dl>
            <h2 style="margin-top: 16px">Historia clínica</h2>
            <p style="white-space: pre-line">{{ ficha.resumen_historia_clinica }}</p>
          </div>

          <div class="tarjeta formulario">
            <h2>Familiograma</h2>
            <template v-if="ficha.familiograma_url">
              <!-- SVG saneado en el backend; en <img> además no ejecuta scripts -->
              <img v-if="ficha.familiograma_mime === 'image/svg+xml'" :src="ficha.familiograma_url" alt="Familiograma del Paciente" class="familiograma" />
              <a :href="ficha.familiograma_url" class="boton boton--chico" rel="noopener">
                {{ ficha.familiograma_mime === 'image/svg+xml' ? 'Descargar Familiograma (SVG)' : 'Ver Familiograma (PDF)' }}
              </a>
            </template>
            <Alerta v-for="(a, i) in ficha.familiograma_advertencias" :key="`adv-${i}`" tipo="info">{{ a.mensaje }}</Alerta>
            <ul v-if="ficha.familiares.length" class="lista-plana">
              <li v-for="(f, i) in ficha.familiares" :key="i">
                <strong>{{ etiquetaParentesco(f.parentesco, f.lado) }}</strong>: {{ [f.nombre, f.apellido].filter(Boolean).join(' ') }}
                <span v-if="f.patologia_diagnosticada" class="suave"> · diagnóstico de {{ f.patologia_diagnosticada }}</span>
                <span v-if="f.sintomas" class="suave"> · {{ f.sintomas }}</span>
              </li>
            </ul>
            <p v-else class="suave">Sin familiares cargados.</p>
            <FormFamiliares v-model="familiares" :patologias="patologias ?? []" />
            <Alerta v-if="familiograma.error.value" tipo="error">{{ familiograma.error.value }}</Alerta>
            <Alerta v-if="familiograma.exito.value" tipo="exito">{{ familiograma.exito.value }}</Alerta>
            <button v-if="familiares.length" class="boton" type="button" :disabled="familiograma.enCurso.value" @click="cargarFamiliograma">
              Guardar familiares y generar Familiograma
            </button>
            <button v-else-if="ficha.familiares.length" class="boton boton--chico" type="button" :disabled="familiograma.enCurso.value" @click="cargarFamiliograma">
              Generar Familiograma de nuevo
            </button>
          </div>
        </div>

        <div class="tarjeta">
          <h2>Historial de Estudios</h2>
          <TablaEstudios :estudios="ficha.estudios" :mostrar-paciente="false" :enlace="(e) => `/medico/estudios/${e.id}`" vacio="El Paciente todavía no tiene Estudios." />
        </div>

        <form v-if="finalizados.length" class="tarjeta formulario" @submit.prevent="solicitarReanalisis">
          <h2>Solicitar Reanálisis <small class="suave">(E6)</small></h2>
          <p class="suave">Analiza otros genes del mismo exoma, sin nueva extracción: pasa directo a bioinformática.</p>
          <label class="campo">
            <span>Estudio Finalizado</span>
            <select v-model="reanalisis.estudio_id" required>
              <option :value="null" disabled>Elegí el Estudio</option>
              <option v-for="e in finalizados" :key="e.id" :value="e.id">{{ e.codigo }} · {{ e.patologias.join(', ') }}</option>
            </select>
          </label>
          <fieldset class="campo">
            <legend>Nueva sospecha (opcional): suma los genes de la API</legend>
            <label v-for="p in patologias ?? []" :key="p.id" class="fila"><input v-model="reanalisis.patologia_ids" type="checkbox" :value="p.id" /> {{ p.nombre }}</label>
          </fieldset>
          <label class="campo">
            <span>Genes a analizar</span>
            <input v-model="reanalisis.genes" placeholder="Símbolos HGNC separados por coma, p. ej. NPC1, NPC2" />
            <small>Los genes ya analizados en este exoma se descartan.</small>
          </label>
          <Alerta v-if="accionReanalisis.error.value" tipo="error">{{ accionReanalisis.error.value }}</Alerta>
          <button class="boton boton--primario" type="submit" :disabled="accionReanalisis.enCurso.value">Solicitar Reanálisis</button>
        </form>
      </template>
    </Estado>
  </section>
</template>

<style scoped>
.enlace { background: none; border: 0; padding: 0; font: inherit; color: var(--color-primario); text-decoration: underline; cursor: pointer; }
.familiograma { display: block; max-width: 100%; height: auto; background: #fff; border: 1px solid var(--color-borde); border-radius: var(--radio-chico); }
</style>
