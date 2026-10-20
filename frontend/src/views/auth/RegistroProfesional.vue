<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import PantallaAuth from '@/components/PantallaAuth.vue'
import { NOMBRE_ROL } from '@/stores/auth'
import { usarAccion, usarCarga } from '@/utils/composables'

type RolRegistro = Esquemas['RegistroEntrada']['rol']

const ROLES: RolRegistro[] = ['MEDICO_TRATANTE', 'ADMINISTRATIVO', 'BIOINFORMATICO', 'GERENTE_MEDICO']

const router = useRouter()
const { datos: especialidades } = usarCarga(() => ok(api.GET('/auth/especialidades')))
const { enCurso, error, exito, ejecutar } = usarAccion()

const form = reactive({
  rol: 'MEDICO_TRATANTE' as RolRegistro,
  nombre: '',
  apellido: '',
  telefono: '',
  email: '',
  password: '',
  matricula: '',
  especialidad_ids: [] as number[],
})

/** E1 / E29: Médico Tratante y Gerente Médico cargan matrícula y especialidades. */
const conMatricula = computed(() => form.rol === 'MEDICO_TRATANTE' || form.rol === 'GERENTE_MEDICO')

async function enviar(): Promise<void> {
  const r = await ejecutar(
    () =>
      ok(
        api.POST('/auth/registro', {
          body: {
            ...form,
            matricula: conMatricula.value ? form.matricula : null,
            especialidad_ids: conMatricula.value ? form.especialidad_ids : [],
          },
        }),
      ),
    'Listo, ya podés ingresar con tu mail y contraseña.',
  )
  if (r) setTimeout(() => void router.push('/ingresar'), 1500)
}
</script>

<template>
  <PantallaAuth titulo="Registro de profesionales" subtitulo="E1, E15, E26 y E29: todos los datos son obligatorios.">
    <form class="formulario" @submit.prevent="enviar">
      <label class="campo">
        <span>Rol</span>
        <select v-model="form.rol" required>
          <option v-for="r in ROLES" :key="r" :value="r">{{ NOMBRE_ROL[r] }}</option>
        </select>
      </label>
      <div class="grilla-2">
        <label class="campo"><span>Nombre</span><input v-model="form.nombre" required autocomplete="given-name" /></label>
        <label class="campo"><span>Apellido</span><input v-model="form.apellido" required autocomplete="family-name" /></label>
      </div>
      <label class="campo"><span>Teléfono</span><input v-model="form.telefono" type="tel" required autocomplete="tel" /></label>
      <label class="campo"><span>Mail</span><input v-model="form.email" type="email" required autocomplete="email" /></label>
      <label class="campo">
        <span>Contraseña</span>
        <input v-model="form.password" type="password" required autocomplete="new-password" minlength="10" />
        <small>Al menos 10 caracteres, con letras y números.</small>
      </label>
      <template v-if="conMatricula">
        <label class="campo"><span>Matrícula</span><input v-model="form.matricula" required placeholder="MN 123456" /></label>
        <fieldset class="campo especialidades">
          <legend>Especialidades</legend>
          <label v-for="e in especialidades ?? []" :key="e.id" class="opcion">
            <input v-model="form.especialidad_ids" type="checkbox" :value="e.id" /> {{ e.nombre }}
          </label>
        </fieldset>
      </template>
      <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
      <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
      <button class="boton boton--primario" type="submit" :disabled="enCurso">Registrarme</button>
    </form>
    <RouterLink to="/ingresar">Ya tengo cuenta</RouterLink>
  </PantallaAuth>
</template>

<style scoped>
.especialidades { border: 1px solid var(--color-borde); border-radius: var(--radio-chico); padding: 10px; display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }
.especialidades legend { font-weight: 600; font-size: 0.9rem; padding: 0 4px; }
.opcion { display: flex; gap: 6px; align-items: center; }
</style>
