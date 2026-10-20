<script setup lang="ts">
import { useRouter } from 'vue-router'
import { api, ok, type Esquemas } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarAccion, usarCarga } from '@/utils/composables'

const router = useRouter()
const { datos, cargando, error, recargar } = usarCarga(() => ok(api.GET('/bioinformatico/pendientes')))
const { enCurso, error: errorTomar, ejecutar } = usarAccion()

/** E27: se envía la `version` que se vio en la lista; si otro Bioinformático lo tomó antes, responde 409. */
async function tomar(e: Esquemas['EstudioResumen']): Promise<void> {
  const r = await ejecutar(() =>
    ok(api.POST('/bioinformatico/estudios/{estudio_id}/tomar', { params: { path: { estudio_id: e.id } }, body: { version: e.version } })),
  )
  if (r) await router.push(`/bioinformatico/estudios/${e.id}`)
  else await recargar()
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Estudios pendientes</h1>
        <p>E27. Con datos crudos de Corea, sin tomar. Los Urgentes (Pompe en menores de 4 meses) primero.</p>
      </div>
      <button class="boton" type="button" @click="recargar">Actualizar</button>
    </div>
    <Alerta v-if="errorTomar" tipo="error">{{ errorTomar }} Actualizamos la lista.</Alerta>
    <div class="tarjeta">
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" mostrar-medico vacio="No hay Estudios esperando análisis.">
          <template #acciones="{ estudio }">
            <button class="boton boton--chico boton--primario" type="button" :disabled="enCurso" @click="tomar(estudio)">Tomar</button>
          </template>
        </TablaEstudios>
      </Estado>
    </div>
  </section>
</template>
