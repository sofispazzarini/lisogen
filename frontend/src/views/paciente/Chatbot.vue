<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const { datos: mensajes, cargando, error } = usarCarga(() => ok(api.GET('/paciente/chatbot')))
const { enCurso, error: errorEnvio, ejecutar } = usarAccion()
const pregunta = ref('')
const conversacion = ref<HTMLElement | null>(null)

const SUGERENCIAS = ['¿Qué es la enfermedad de Fabry?', '¿Qué es Pompe?', '¿Cómo saco Turno?', '¿Cuándo tengo el Resultado?']

/** E14: el chatbot responde sobre las cinco Patologías y no deriva a una persona. */
async function enviar(texto = pregunta.value): Promise<void> {
  if (!texto.trim()) return
  const m = await ejecutar(() => ok(api.POST('/paciente/chatbot', { body: { pregunta: texto.trim() } })))
  if (m) {
    mensajes.value = [...(mensajes.value ?? []), m]
    pregunta.value = ''
    await nextTick()
    conversacion.value?.scrollTo({ top: conversacion.value.scrollHeight })
  }
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Chatbot</h1>
        <p>Preguntá sobre Fabry, Pompe, MPS 1, Gaucher, ASMD o sobre tu Estudio. Es información general.</p>
      </div>
    </div>
    <div class="tarjeta chat">
      <Estado :cargando="cargando" :error="error">
        <div ref="conversacion" class="conversacion" aria-live="polite">
          <p v-if="!mensajes?.length" class="vacio">Escribí tu primera pregunta.</p>
          <template v-for="m in mensajes ?? []" :key="m.id">
            <p class="burbuja yo">{{ m.pregunta }}</p>
            <p class="burbuja bot">{{ m.respuesta }}</p>
          </template>
        </div>
      </Estado>
      <div class="fila">
        <button v-for="s in SUGERENCIAS" :key="s" class="boton boton--chico" type="button" :disabled="enCurso" @click="enviar(s)">{{ s }}</button>
      </div>
      <form class="fila" @submit.prevent="enviar()">
        <input v-model="pregunta" maxlength="500" placeholder="Escribí tu pregunta" aria-label="Pregunta" style="flex: 1" />
        <button class="boton boton--primario" type="submit" :disabled="enCurso || !pregunta.trim()">Enviar</button>
      </form>
      <Alerta v-if="errorEnvio" tipo="error">{{ errorEnvio }}</Alerta>
    </div>
  </section>
</template>

<style scoped>
.chat { display: grid; gap: 12px; }
.conversacion { display: grid; gap: 8px; max-height: 55vh; overflow-y: auto; padding-right: 4px; }
.burbuja { margin: 0; padding: 10px 14px; border-radius: 14px; max-width: 80%; white-space: pre-line; }
.yo { justify-self: end; background: var(--color-primario); color: #fff; border-bottom-right-radius: 4px; }
.bot { justify-self: start; background: var(--color-superficie-2); border: 1px solid var(--color-borde); border-bottom-left-radius: 4px; }
</style>
