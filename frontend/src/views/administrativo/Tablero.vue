<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ok, type Esquemas } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import TablaEstudios from '@/components/TablaEstudios.vue'
import { usarCarga } from '@/utils/composables'
import { ETIQUETA, type EstadoEstudio } from '@/utils/estados'

const filtro = ref<EstadoEstudio | ''>('')
const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.GET('/administrativo/estudios', { params: { query: filtro.value ? { estado: filtro.value } : {} } })),
)
watch(filtro, () => void recargar())

/** Contadores por Estado: qué está esperando una acción del Laboratorio. */
const PENDIENTES: { estado: EstadoEstudio; ruta: string }[] = [
  { estado: 'CREADO', ruta: '/administrativo/presupuestos' },
  { estado: 'PENDIENTE_AUTORIZACION', ruta: '/administrativo/autorizaciones' },
  { estado: 'EN_ESPERA_RETIRO', ruta: '/administrativo/lotes' },
  { estado: 'EN_VIAJE_COREA', ruta: '/administrativo/datos-crudos' },
]
const todos = usarCarga(() => ok(api.GET('/administrativo/estudios')))
const conteo = computed(() => {
  const c: Partial<Record<EstadoEstudio, number>> = {}
  for (const e of (todos.datos.value ?? []) as Esquemas['EstudioResumen'][]) c[e.estado] = (c[e.estado] ?? 0) + 1
  return c
})
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Tablero</h1>
        <p>Todos los Estudios del Laboratorio. Los Urgentes aparecen primero.</p>
      </div>
    </div>
    <div class="contadores">
      <RouterLink v-for="p in PENDIENTES" :key="p.estado" :to="p.ruta" class="tarjeta contador">
        <strong>{{ conteo[p.estado] ?? 0 }}</strong>
        <span>{{ ETIQUETA[p.estado] }}</span>
      </RouterLink>
    </div>
    <div class="tarjeta pagina">
      <label class="campo" style="max-width: 320px">
        <span>Filtrar por Estado</span>
        <select v-model="filtro">
          <option value="">Todos</option>
          <option v-for="(etiqueta, estado) in ETIQUETA" :key="estado" :value="estado">{{ etiqueta }}</option>
        </select>
      </label>
      <Estado :cargando="cargando" :error="error">
        <TablaEstudios :estudios="datos ?? []" mostrar-medico :enlace="(e) => `/administrativo/estudios/${e.id}`" />
      </Estado>
    </div>
  </section>
</template>

<style scoped>
.contadores { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.contador { display: grid; gap: 2px; text-decoration: none; color: inherit; }
.contador strong { font-size: 1.8rem; color: var(--color-primario); }
.contador:hover { border-color: var(--color-primario); }
</style>
