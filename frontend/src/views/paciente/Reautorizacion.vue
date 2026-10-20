<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, multipart, ok, sinSerializar } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const props = defineProps<{ id: string }>()
const router = useRouter()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))
const estudio = usarCarga(() => ok(api.GET('/paciente/estudios/{estudio_id}', path.value)))
const archivo = ref<File | null>(null)
const { enCurso, error, ejecutar } = usarAccion()

/** E10: adjuntar la decisión judicial (PDF) y pedir la reautorización a la Obra Social. */
async function enviar(): Promise<void> {
  if (!archivo.value) return
  const r = await ejecutar(() =>
    ok(
      api.POST('/paciente/estudios/{estudio_id}/reautorizacion', {
        ...path.value,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        body: multipart({ archivo: archivo.value }) as any,
        ...sinSerializar,
      }),
    ),
  )
  if (r) await router.push(`/paciente/estudios/${props.id}`)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Solicitar reautorización</h1>
        <p>E10. Si obtuviste una decisión judicial favorable, adjuntala en PDF.</p>
      </div>
    </div>
    <Estado :cargando="estudio.cargando.value" :error="estudio.error.value">
      <Alerta v-if="estudio.datos.value?.estado !== 'RECHAZADO'" tipo="info">
        Este Estudio no está Rechazado: no hace falta pedir reautorización.
      </Alerta>
      <form v-else class="tarjeta formulario" @submit.prevent="enviar">
        <Alerta tipo="error">Motivo del rechazo: {{ estudio.datos.value?.rechazo_motivo ?? 'sin detalle' }}</Alerta>
        <label class="campo">
          <span>Decisión judicial (PDF, hasta 10 MB)</span>
          <input type="file" accept="application/pdf" required @change="archivo = ($event.target as HTMLInputElement).files?.[0] ?? null" />
        </label>
        <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
        <button class="boton boton--primario" type="submit" :disabled="enCurso || !archivo">Solicitar reautorización</button>
      </form>
    </Estado>
  </section>
</template>
