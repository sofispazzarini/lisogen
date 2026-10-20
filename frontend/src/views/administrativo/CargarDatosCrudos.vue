<script setup lang="ts">
import { ref } from 'vue'
import { api, multipart, ok, sinSerializar } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/administrativo/estudios', { params: { query: { estado: 'EN_VIAJE_COREA' } } })),
)
const archivos = ref<Record<number, File | null>>({})
const { enCurso, error: errorCarga, exito, ejecutar } = usarAccion()

/** E21: el archivo llegó de Corea por mail. Al cargarlo, el Estudio pasa a bioinformática. */
async function cargar(id: number, codigo: string): Promise<void> {
  const archivo = archivos.value[id]
  if (!archivo) return
  const r = await ejecutar(
    () =>
      ok(
        api.POST('/administrativo/estudios/{estudio_id}/datos-crudos', {
          params: { path: { estudio_id: id } },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          body: multipart({ archivo }) as any,
          ...sinSerializar,
        }),
      ),
    `Datos crudos de ${codigo} cargados. Avisamos a los Bioinformáticos.`,
  )
  if (r) await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Cargar datos crudos de Corea</h1>
        <p>E21. Los resultados de secuenciación son individuales por Estudio (hasta 200 MB por archivo).</p>
      </div>
    </div>
    <Alerta v-if="errorCarga" tipo="error">{{ errorCarga }}</Alerta>
    <Alerta v-if="exito" tipo="exito">{{ exito }}</Alerta>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" :enlace="(e) => `/administrativo/estudios/${e.id}`" vacio="No hay Estudios en Corea esperando datos crudos.">
          <template #acciones="{ estudio }">
            <form class="fila" @submit.prevent="cargar(estudio.id, estudio.codigo)">
              <input type="file" :aria-label="`Datos crudos de ${estudio.codigo}`" @change="archivos[estudio.id] = ($event.target as HTMLInputElement).files?.[0] ?? null" />
              <button class="boton boton--chico boton--primario" type="submit" :disabled="enCurso || !archivos[estudio.id]">Cargar</button>
            </form>
          </template>
        </TablaEstudios>
      </Estado>
      <p class="suave">Si el ADN llegó desnaturalizado, no cargues datos crudos: <RouterLink to="/administrativo/reextracciones">solicitá una nueva extracción</RouterLink>.</p>
    </div>
  </section>
</template>
