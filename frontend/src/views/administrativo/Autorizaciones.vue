<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { fechaHora } from '@/utils/formato'

const pendientes = usarCarga(() => ok(api.GET('/administrativo/estudios', { params: { query: { estado: 'PENDIENTE_AUTORIZACION' } } })))
const reautorizaciones = usarCarga(() => ok(api.GET('/administrativo/reautorizaciones')))
const { enCurso, error, exito, ejecutar } = usarAccion()
const motivos = ref<Record<number, string>>({})
const rechazando = ref<number | null>(null)

async function refrescar(): Promise<void> {
  await Promise.all([pendientes.recargar(), reautorizaciones.recargar()])
}

/** E17: la Obra Social autorizó (por teléfono). Autorizado equivale a pagado. */
async function autorizar(id: number, codigo: string): Promise<void> {
  const r = await ejecutar(
    () => ok(api.POST('/administrativo/estudios/{estudio_id}/autorizacion', { params: { path: { estudio_id: id } } })),
    `Autorización del Estudio ${codigo} registrada.`,
  )
  if (r) await refrescar()
}

/** E18: el rechazo habilita al Paciente a pedir la reautorización con una decisión judicial (E10). */
async function rechazar(id: number, codigo: string): Promise<void> {
  const r = await ejecutar(
    () =>
      ok(api.POST('/administrativo/estudios/{estudio_id}/rechazo', { params: { path: { estudio_id: id } }, body: { motivo: motivos.value[id] ?? '' } })),
    `Rechazo del Estudio ${codigo} registrado.`,
  )
  if (r) {
    rechazando.value = null
    await refrescar()
  }
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Autorizaciones de Obra Social</h1>
        <p>E17 y E18. Gestioná la autorización por teléfono y registrá la respuesta.</p>
      </div>
    </div>
    <Alerta v-if="error" tipo="error">{{ error }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>

    <div class="tarjeta">
      <h2>Reautorizaciones con decisión judicial</h2>
      <Estado :cargando="reautorizaciones.cargando.value" :error="reautorizaciones.error.value">
        <ul v-if="reautorizaciones.datos.value?.length" class="lista-plana">
          <li v-for="r in reautorizaciones.datos.value" :key="r.id" class="fila">
            <RouterLink :to="`/administrativo/estudios/${r.estudio_id}`">{{ r.estudio_codigo }}</RouterLink>
            <span>{{ r.paciente }} · pedida el {{ fechaHora(r.created_at) }}</span>
            <a v-if="r.decision_judicial_url" :href="r.decision_judicial_url" target="_blank" rel="noopener" class="boton boton--chico">Ver decisión judicial</a>
          </li>
        </ul>
        <p v-else class="suave">No hay pedidos de reautorización.</p>
      </Estado>
    </div>

    <div class="tarjeta">
      <h2>Pendientes de Autorización</h2>
      <Estado :cargando="pendientes.cargando.value" :error="pendientes.error.value">
        <TablaEstudios :estudios="pendientes.datos.value ?? []" :enlace="(e) => `/administrativo/estudios/${e.id}`" vacio="No hay Estudios esperando autorización.">
          <template #acciones="{ estudio }">
            <div v-if="rechazando === estudio.id" class="fila">
              <input v-model="motivos[estudio.id]" placeholder="Motivo del rechazo" aria-label="Motivo del rechazo" />
              <button class="boton boton--chico boton--peligro" type="button" :disabled="enCurso || (motivos[estudio.id] ?? '').trim().length < 3" @click="rechazar(estudio.id, estudio.codigo)">Confirmar rechazo</button>
              <button class="boton boton--chico" type="button" @click="rechazando = null">Cancelar</button>
            </div>
            <div v-else class="fila">
              <button class="boton boton--chico boton--primario" type="button" :disabled="enCurso" @click="autorizar(estudio.id, estudio.codigo)">Autorizar</button>
              <button class="boton boton--chico boton--peligro" type="button" @click="rechazando = estudio.id">Rechazar</button>
            </div>
          </template>
        </TablaEstudios>
      </Estado>
    </div>
  </section>
</template>
