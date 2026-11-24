<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import { usarAccion } from '@/utils/composables'

/** E22 / SUPUESTOS S10 y S42: el Administrativo vuelve el Estudio atrás porque la Muestra llegó mal a Corea
 * (ADN desnaturalizado o mala calidad, por ejemplo con menos de 2 ml). Mismo Estudio, sin costo. */
const props = defineProps<{ estudioId: number; codigo: string }>()
const emit = defineEmits<{ hecho: [mensaje: string]; error: [mensaje: string] }>()

type Motivo = 'DESNATURALIZADA' | 'MALA_CALIDAD'
const ETIQUETAS: Record<Motivo, string> = { DESNATURALIZADA: 'ADN desnaturalizado', MALA_CALIDAD: 'Mala calidad' }

const detalle = ref('')
const { enCurso, error, ejecutar } = usarAccion()

async function solicitar(motivo: Motivo): Promise<void> {
  const pregunta = `¿Solicitás una nueva extracción para ${props.codigo} por ${ETIQUETAS[motivo].toLowerCase()}? El Paciente tendrá que sacar otro Turno (sin costo).`
  if (!window.confirm(pregunta)) return
  const r = await ejecutar(() =>
    ok(
      api.POST('/administrativo/estudios/{estudio_id}/reextraccion', {
        params: { path: { estudio_id: props.estudioId } },
        body: { motivo, detalle: detalle.value.trim() || null },
      }),
    ),
  )
  if (r) {
    detalle.value = ''
    emit('hecho', `Nueva extracción solicitada para ${props.codigo}. Avisamos al Paciente y al Médico Tratante.`)
  } else if (error.value) {
    emit('error', error.value)
  }
}
</script>

<template>
  <form class="fila" @submit.prevent>
    <input v-model="detalle" placeholder="Detalle (opcional)" maxlength="500" :aria-label="`Detalle para ${codigo}`" />
    <button class="boton boton--chico boton--peligro" type="button" :disabled="enCurso" @click="solicitar('MALA_CALIDAD')">
      Mala calidad
    </button>
    <button class="boton boton--chico boton--peligro" type="button" :disabled="enCurso" @click="solicitar('DESNATURALIZADA')">
      ADN desnaturalizado
    </button>
  </form>
</template>
