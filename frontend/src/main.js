import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { setUnauthorizedHandler } from './api/client'

import 'element-plus/dist/index.css'
import 'nprogress/nprogress.css'
import './styles/index.scss'

dayjs.locale('zh-cn')

const app = createApp(App)
const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component)
}

// 401 且刷新失败 → 清理登录态并回到登录页
setUnauthorizedHandler(() => {
  const auth = useAuthStore()
  auth.clearSession()
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})

app.mount('#app')
