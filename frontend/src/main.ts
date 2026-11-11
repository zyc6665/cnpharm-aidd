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

/**
 * 移除 `index.html` 里的首屏骨架。
 *
 * 时机很关键：必须在首次路由解析完成（`router.isReady()`）之后，
 * 否则骨架消失时页面还没渲染，用户看到的是「转圈 → 白屏 → 内容」，
 * 比不做还糟。8s 兜底是防路由异常时骨架永远盖住界面。
 */
function dismissSplash(): void {
  const splash = document.getElementById('app-splash')
  if (!splash || splash.classList.contains('is-hidden')) return
  splash.classList.add('is-hidden')
  window.setTimeout(() => splash.remove(), 260)
}

app.mount('#app')

void router.isReady().then(dismissSplash)
window.setTimeout(dismissSplash, 8000)
