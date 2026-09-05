import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { router } from './app/router'
import { i18n } from './shared/i18n'
import App from './App.vue'

// Import Design System Theme & Tailwind Styles
import './shared/theme/index.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

app.mount('#app')
