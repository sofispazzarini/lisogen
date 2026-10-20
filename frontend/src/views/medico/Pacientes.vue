<script setup lang="ts">
import { ref } from 'vue'
import { api, ok } from '@/api/cliente'
import Estado from '@/components/Estado.vue'
import { usarCarga } from '@/utils/composables'
import { fecha } from '@/utils/formato'

const texto = ref('')
// Búsqueda por POST: el DNI o el apellido no quedan en la URL (Ley 25.326).
const { datos, cargando, error, recargar } = usarCarga(() =>
  ok(api.POST('/medico/pacientes/buscar', { body: { texto: texto.value } })),
)
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Pacientes</h1>
        <p>Tus Pacientes: los que diste de alta o los que tienen Estudios tuyos.</p>
      </div>
      <RouterLink to="/medico/pacientes/nuevo" class="boton boton--primario">Alta Paciente</RouterLink>
    </div>
    <div class="tarjeta pagina">
      <form class="fila" @submit.prevent="recargar">
        <input v-model="texto" type="search" placeholder="Buscar por apellido, nombre o DNI" aria-label="Buscar Paciente" style="flex: 1" />
        <button class="boton" type="submit">Buscar</button>
      </form>
      <Estado :cargando="cargando" :error="error">
        <div class="tabla-contenedor">
          <table v-if="datos?.length" class="tabla">
            <thead><tr><th>Paciente</th><th>DNI</th><th>Nacimiento</th><th>Obra Social</th><th>Estudios</th></tr></thead>
            <tbody>
              <tr v-for="p in datos" :key="p.id">
                <td><RouterLink :to="`/medico/pacientes/${p.id}`">{{ p.nombre_completo }}</RouterLink></td>
                <td>{{ p.dni }}</td>
                <td>{{ fecha(p.fecha_nacimiento) }}</td>
                <td>{{ p.obra_social ?? 'Particular' }}</td>
                <td>{{ p.cantidad_estudios }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="vacio">No encontramos Pacientes.</p>
        </div>
      </Estado>
    </div>
  </section>
</template>
