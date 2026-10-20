<script setup lang="ts">
import type { Esquemas } from '@/api/cliente'
import { fechaHora, titulo } from '@/utils/formato'

defineProps<{ resultado: Esquemas['ResultadoSalida'] }>()

const TEXTO: Record<Esquemas['TipoResultado'], string> = {
  POSITIVO: 'Se identificaron variantes patogénicas compatibles con la sospecha clínica.',
  NEGATIVO: 'No se identificaron variantes patogénicas en los genes analizados.',
  NO_CONCLUYENTE: 'Se identificaron variantes de significado incierto. Tu Médico Tratante te va a orientar sobre los próximos pasos.',
}
</script>

<template>
  <div class="resultado">
    <div class="tipo" :class="`tipo--${resultado.tipo}`">
      <strong>{{ titulo(resultado.tipo) }}</strong>
      <span>{{ TEXTO[resultado.tipo] }}</span>
    </div>
    <p class="suave">Confirmado el {{ fechaHora(resultado.confirmado_at) }}.</p>
    <div class="tabla-contenedor">
      <table v-if="resultado.variantes.length" class="tabla">
        <thead><tr><th>Gen</th><th>Variante</th><th>Clasificación</th><th></th></tr></thead>
        <tbody>
          <tr v-for="v in resultado.variantes" :key="`${v.gen}-${v.nomenclatura}`">
            <td><strong>{{ v.gen }}</strong></td>
            <td><code>{{ v.nomenclatura }}</code></td>
            <td>{{ titulo(v.clasificacion) }}</td>
            <td><span v-if="v.hallazgo_secundario" class="suave">Hallazgo secundario</span></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="suave">No se identificaron Variantes en los genes analizados.</p>
    </div>
    <a v-if="resultado.pdf_url" class="boton boton--primario" :href="resultado.pdf_url" target="_blank" rel="noopener">Descargar el informe (PDF)</a>
    <small class="suave">El enlace de descarga es privado y vence en pocos minutos.</small>
  </div>
</template>

<style scoped>
.resultado { display: grid; gap: 12px; justify-items: start; }
.resultado .tabla-contenedor { width: 100%; }
.tipo { display: grid; gap: 2px; padding: 14px; border-radius: var(--radio); width: 100%; }
.tipo strong { font-size: 1.2rem; }
.tipo--POSITIVO { background: var(--tono-alerta-fondo); color: var(--tono-alerta-texto); }
.tipo--NEGATIVO { background: var(--tono-exito-fondo); color: var(--tono-exito-texto); }
.tipo--NO_CONCLUYENTE { background: var(--tono-accion-fondo); color: var(--tono-accion-texto); }
</style>
