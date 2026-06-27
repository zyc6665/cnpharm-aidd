<template>
  <a-config-provider :locale="antdLocale" :theme="antdTheme">
    <!-- 品牌页 / 认证页 / 错误页：无壳层 -->
    <router-view v-if="isShellLess" />
    <!-- 所有其他页面：AppShell 侧边栏壳层 -->
    <AppShell v-else />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import enUS from 'ant-design-vue/es/locale/en_US'
import { theme } from 'ant-design-vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useAppStore, useUserStore } from '@/stores'

const route = useRoute()
const appStore = useAppStore()
const userStore = useUserStore()

// Ant Design 国际化
const antdLocale = computed(() => {
  return appStore.locale === 'zh-CN' ? zhCN : enUS
})

// Ant Design 暗色主题算法
const antdTheme = computed(() => ({
  algorithm: appStore.theme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
}))

// 不需要侧边栏的页面：首页、认证页、错误页
const shellLessPaths = ['/login', '/register', '/forgot-password', '/403', '/404']
const isShellLess = computed(() => {
  if (route.path === '/') return true
  return shellLessPaths.some((p) => route.path.startsWith(p))
})

// 初始化
onMounted(async () => {
  // 应用持久化的主题
  if (appStore.theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light')
  }
  await userStore.bootstrapAuthState()
})
</script>

<style lang="less">
@import '@/assets/styles/global.less';
@import '@/assets/styles/antd-override.less';
</style>
