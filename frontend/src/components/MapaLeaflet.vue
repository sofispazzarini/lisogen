<script setup lang="ts">
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface Marcador {
  id: number | string
  lat: number
  lon: number
  titulo: string
  detalle?: string
  destacado?: boolean
}

const props = withDefaults(defineProps<{ marcadores: Marcador[]; zoom?: number; ruta?: boolean }>(), {
  zoom: 5,
  ruta: false,
})
const emit = defineEmits<{ seleccionar: [id: Marcador['id']] }>()

const contenedor = ref<HTMLElement | null>(null)
let mapa: L.Map | null = null
let capa: L.LayerGroup | null = null

/** Popup armado con nodos de texto: los datos nunca se interpretan como HTML. */
function popup(m: Marcador): HTMLElement {
  const div = document.createElement('div')
  const t = document.createElement('strong')
  t.textContent = m.titulo
  div.append(t)
  if (m.detalle) {
    div.append(document.createElement('br'), document.createTextNode(m.detalle))
  }
  return div
}

function pintar(): void {
  if (!mapa || !capa) return
  capa.clearLayers()
  for (const m of props.marcadores) {
    const punto = L.circleMarker([m.lat, m.lon], {
      radius: m.destacado ? 11 : 8,
      color: m.destacado ? '#c62828' : '#1d4e89',
      weight: 2,
      fillOpacity: 0.85,
    })
    punto.bindTooltip(m.titulo).bindPopup(popup(m))
    punto.on('click', () => emit('seleccionar', m.id))
    capa.addLayer(punto)
  }
  if (props.ruta && props.marcadores.length > 1) {
    capa.addLayer(L.polyline(props.marcadores.map((m) => [m.lat, m.lon] as [number, number]), { color: '#0f8a6c', dashArray: '6 6' }))
  }
  if (props.marcadores.length === 1) {
    const m = props.marcadores[0]!
    mapa.setView([m.lat, m.lon], 13)
  } else if (props.marcadores.length > 1) {
    mapa.fitBounds(L.latLngBounds(props.marcadores.map((m) => [m.lat, m.lon] as [number, number])), { padding: [30, 30] })
  }
}

onMounted(() => {
  if (!contenedor.value) return
  mapa = L.map(contenedor.value).setView([-38.4, -63.6], props.zoom) // Argentina
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap',
  }).addTo(mapa)
  capa = L.layerGroup().addTo(mapa)
  pintar()
})

watch(() => props.marcadores, pintar, { deep: true })
onBeforeUnmount(() => mapa?.remove())
</script>

<template>
  <div ref="contenedor" class="mapa" role="region" aria-label="Mapa"></div>
</template>
