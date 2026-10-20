<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import BuscadorSnomed from '@/components/BuscadorSnomed.vue'
import FormFamiliares from '@/components/FormFamiliares.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

type Concepto = Esquemas['Concepto']
type TipoSospecha = Esquemas['TipoSospecha']

const router = useRouter()
const { datos: patologias } = usarCarga(() => ok(api.GET('/medico/patologias')))
const { datos: obrasSociales } = usarCarga(() => ok(api.GET('/medico/obras-sociales')))
const { enCurso, error, ejecutar } = usarAccion()

const form = reactive({
  dni: '',
  nombre: '',
  apellido: '',
  fecha_nacimiento: '',
  telefono: '',
  email: '',
  obra_social_id: null as number | null,
  nro_afiliado: '',
  resumen_historia_clinica: '',
})
const sintomas = ref<Concepto[]>([])
const diagnostico = reactive({ patologia_id: null as number | null, tipo_sospecha: 'CLINICA' as TipoSospecha })
const familiares = ref<Esquemas['FamiliarEntrada'][]>([])

/** Menor de edad (E2): se registra el mail de un padre o madre, que hace el proceso en su nombre. */
const esMenor = computed(() => {
  if (!form.fecha_nacimiento) return false
  const nac = new Date(`${form.fecha_nacimiento}T12:00:00`)
  const mayoria = new Date(nac)
  mayoria.setFullYear(nac.getFullYear() + 18)
  return mayoria > new Date()
})

const patologia = computed(() => patologias.value?.find((p) => p.id === diagnostico.patologia_id) ?? null)

/** Vista previa de Validar Diagnóstico (E2): síntoma cardinal o dos secundarios. La regla la aplica el backend. */
const validacion = computed(() => {
  const p = patologia.value
  if (!p) return null
  const ids = new Set(sintomas.value.map((s) => s.concept_id))
  const cardinal = ids.has(p.sintoma_cardinal.concept_id)
  const secundarios = p.secundarios.filter((s) => ids.has(s.concept_id)).length
  return { valida: cardinal || secundarios >= 2, cardinal, secundarios }
})

async function enviar(): Promise<void> {
  if (!diagnostico.patologia_id) return
  const paciente = await ejecutar(() =>
    ok(
      api.POST('/medico/pacientes', {
        body: {
          ...form,
          obra_social_id: form.obra_social_id,
          nro_afiliado: form.obra_social_id ? form.nro_afiliado || null : null,
          sintomas: sintomas.value.map((s) => s.concept_id),
          diagnosticos: [{ patologia_id: diagnostico.patologia_id!, tipo_sospecha: diagnostico.tipo_sospecha }],
          familiares: familiares.value.filter((f) => f.nombre.trim()),
        },
      }),
    ),
  )
  if (paciente) await router.push(`/medico/pacientes/${paciente.id}?alta=1`)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Alta Paciente</h1>
        <p>E2 y E3. Al confirmar, el Paciente recibe por mail su usuario y una contraseña provisoria.</p>
      </div>
    </div>
    <form class="pagina" @submit.prevent="enviar">
      <div class="tarjeta formulario">
        <h2>Datos personales</h2>
        <div class="grilla-2">
          <label class="campo"><span>DNI</span><input v-model="form.dni" inputmode="numeric" pattern="\d{7,8}" required /></label>
          <label class="campo"><span>Fecha de nacimiento</span><input v-model="form.fecha_nacimiento" type="date" required /></label>
          <label class="campo"><span>Nombre</span><input v-model="form.nombre" required /></label>
          <label class="campo"><span>Apellido</span><input v-model="form.apellido" required /></label>
          <label class="campo"><span>Teléfono</span><input v-model="form.telefono" type="tel" required /></label>
          <label class="campo">
            <span>{{ esMenor ? 'Mail del padre, madre o tutor' : 'Mail' }}</span>
            <input v-model="form.email" type="email" required />
            <small v-if="esMenor">El Paciente es menor de edad: la cuenta queda a nombre de su padre, madre o tutor.</small>
          </label>
          <label class="campo">
            <span>Obra Social</span>
            <select v-model="form.obra_social_id">
              <option :value="null">Particular (sin Obra Social)</option>
              <option v-for="o in obrasSociales ?? []" :key="o.id" :value="o.id">{{ o.nombre }}</option>
            </select>
          </label>
          <label v-if="form.obra_social_id" class="campo"><span>Número de afiliado</span><input v-model="form.nro_afiliado" /></label>
        </div>
      </div>

      <div class="tarjeta formulario">
        <h2>Diagnóstico presuntivo</h2>
        <div class="grilla-2">
          <label class="campo">
            <span>Patología sospechada</span>
            <select v-model="diagnostico.patologia_id" required>
              <option :value="null" disabled>Elegí una Patología</option>
              <option v-for="p in patologias ?? []" :key="p.id" :value="p.id">{{ p.nombre }}</option>
            </select>
          </label>
          <fieldset class="campo">
            <legend>Tipo de sospecha</legend>
            <label class="fila"><input v-model="diagnostico.tipo_sospecha" type="radio" value="CLINICA" /> Clínica</label>
            <label class="fila"><input v-model="diagnostico.tipo_sospecha" type="radio" value="FAMILIAR" /> Familiar</label>
          </fieldset>
        </div>
        <p v-if="patologia" class="suave">
          Síntoma cardinal: <strong>{{ patologia.sintoma_cardinal.termino }}</strong>. Secundarios:
          {{ patologia.secundarios.map((s) => s.termino).join(', ') }}.
        </p>
        <label class="campo">
          <span>Resumen de historia clínica</span>
          <textarea v-model="form.resumen_historia_clinica" required></textarea>
        </label>
        <BuscadorSnomed v-model="sintomas" />
        <Alerta v-if="validacion && !validacion.valida" tipo="error">
          Para {{ patologia?.nombre }} hace falta el síntoma cardinal o al menos dos secundarios
          (cargaste {{ validacion.secundarios }} secundario{{ validacion.secundarios === 1 ? '' : 's' }}).
        </Alerta>
        <Alerta v-else-if="validacion?.valida" tipo="exito">Los síntomas validan el diagnóstico presuntivo.</Alerta>
      </div>

      <div class="tarjeta formulario">
        <h2>Familiograma <small class="suave">(opcional)</small></h2>
        <FormFamiliares v-model="familiares" :patologias="patologias ?? []" />
      </div>

      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <div class="fila">
        <button class="boton boton--primario" type="submit" :disabled="enCurso || !sintomas.length || !diagnostico.patologia_id">
          {{ enCurso ? 'Dando de alta…' : 'Dar de alta al Paciente' }}
        </button>
        <RouterLink to="/medico/pacientes" class="boton">Cancelar</RouterLink>
      </div>
    </form>
  </section>
</template>
