import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import App from './App.vue'
import router from './router'
import pinia from './stores'
import i18n from './locales'

import 'ant-design-vue/dist/reset.css'

const app = createApp(App)

app.use(pinia)
app.use(router)
app.use(i18n)
app.use(Antd)

app.mount('#app')
