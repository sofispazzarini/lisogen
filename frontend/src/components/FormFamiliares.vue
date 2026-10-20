<script setup lang="ts">
import type { Esquemas } from '@/api/cliente'

type Familiar = Esquemas['FamiliarEntrada']
type Parentesco = Esquemas['Parentesco']

/** E3: parentesco, nombre, síntomas y diagnóstico de cada familiar (la sección puede quedar vacía). */
defineProps<{ patologias: { id: number; nombre: string }[] }>()
const familiares = defineModel<Familiar[]>({ default: () => [] })

const PARENTESCOS: Parentesco[] = ['PADRE', 'MADRE', 'HERMANO', 'HERMANA', 'HIJO', 'HIJA', 'ABUELO', 'ABUELA', 'TIO', 'TIA', 'PRIMO', 'PRIMA', 'OTRO']
const etiqueta = (p: Parentesco) => (p === 'TIO' ? 'Tío' : p === 'TIA' ? 'Tía' : p.charAt(0) + p.slice(1).toLowerCase())

function agregar(): void {
  familiares.value = [...familiares.value, { parentesco: 'MADRE', nombre: '', sintomas: null, patologia_diagnosticada_id: null }]
}

function quitar(i: number): void {
  familiares.value = familiares.value.filter((_, j) => j !== i)
}
</script>

<template>
  <div class="familiares">
    <p v-if="!familiares.length" class="suave">Sin familiares cargados. Si el Paciente no brinda información, dejá la sección vacía.</p>
    <div v-for="(f, i) in familiares" :key="i" class="familiar">
      <label class="campo">
        <span>Parentesco</span>
        <select v-model="f.parentesco">
          <option v-for="p in PARENTESCOS" :key="p" :value="p">{{ etiqueta(p) }}</option>
        </select>
      </label>
      <label class="campo"><span>Nombre</span><input v-model="f.nombre" required /></label>
      <label class="campo"><span>Síntomas</span><input v-model="f.sintomas" placeholder="Opcional" /></label>
      <label class="campo">
        <span>Diagnóstico previo</span>
        <select v-model="f.patologia_diagnosticada_id">
          <option :value="null">Ninguno</option>
          <option v-for="p in patologias" :key="p.id" :value="p.id">{{ p.nombre }}</option>
        </select>
      </label>
      <button class="boton boton--chico boton--peligro" type="button" @click="quitar(i)">Quitar</button>
    </div>
    <button class="boton boton--chico" type="button" @click="agregar">+ Agregar familiar</button>
  </div>
</template>

<style scoped>
.familiares { display: grid; gap: 10px; }
.familiar { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; align-items: end; padding: 10px; border: 1px dashed var(--color-borde); border-radius: var(--radio-chico); }
</style>
