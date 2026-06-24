<template>
  <a-config-provider :locale="antdLocale">
    <component :is="layout">
      <router-view />
    </component>
  </a-config-provider>
</template>

<script setup lang="ts">
  import { computed, onMounted } from 'vue'
  import { useRoute } from 'vue-router'
  import zhCN from 'ant-design-vue/es/locale/zh_CN'
  import enUS from 'ant-design-vue/es/locale/en_US'
  import DefaultLayout from '@/components/layout/DefaultLayout.vue'
  import { useAppStore, useUserStore } from '@/stores'

  const route = useRoute()
  const appStore = useAppStore()
  const userStore = useUserStore()

  // Ant Design 国际化
  const antdLocale = computed(() => {
    return appStore.locale === 'zh-CN' ? zhCN : enUS
  })

  // 根据路由选择布局
  const layout = computed(() => {
    // 管理后台、认证页面和错误页面由各自路由组件自行控制布局
    if (
      route.path.startsWith('/admin') ||
      route.path.startsWith('/login') ||
      route.path.startsWith('/register') ||
      route.path.startsWith('/forgot-password') ||
      route.path.startsWith('/403') ||
      route.path.startsWith('/404')
    ) {
      return 'div'
    }
    return DefaultLayout
  })

  // 初始化：获取用户信息
  onMounted(async () => {
    await userStore.bootstrapAuthState()
  })
</script>

<style lang="less">
  @import '@/assets/styles/global.less';
  @import '@/assets/styles/antd-override.less';
</style>
