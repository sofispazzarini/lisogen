import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { eventosSesion } from '@/api/cliente'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
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
