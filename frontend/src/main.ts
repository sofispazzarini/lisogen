import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { eventosSesion } from '@/api/cliente'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
// Fuentes servidas por LisoGen (sin pedidos a Google): IBM Plex Sans para el texto, Source Serif 4 para títulos
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/source-serif-4/500.css'
import '@fontsource/source-serif-4/600.css'
import './styles/base.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Si la sesión vence y no se puede renovar, se vuelve al ingreso conservando la ruta.
eventosSesion.addEventListener('vencida', () => {
  useAuthStore().salir()
  void router.push({ name: 'ingresar', query: { volver: router.currentRoute.value.fullPath, vencida: '1' } })
})

app.mount('#app')
