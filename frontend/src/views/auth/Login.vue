<template>
  <AuthShell :title="t('auth.login')">
    <a-form
      ref="formRef"
      :model="formState"
      :rules="rules"
      layout="vertical"
      @finish="handleSubmit"
    >
          <a-form-item name="username" :label="t('auth.account')">
            <a-input
              v-model:value="formState.username"
              size="large"
              :placeholder="t('auth.validation.accountRequired')"
            >
              <template #prefix>
                <UserOutlined />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item name="password" :label="t('auth.password')">
            <a-input-password
              v-model:value="formState.password"
              size="large"
              :placeholder="t('auth.validation.passwordRequired')"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-checkbox v-model:checked="formState.remember">
              {{ t('auth.rememberMe') }}
            </a-checkbox>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" size="large" block :loading="loading">
              {{ t('auth.login') }}
            </a-button>
          </a-form-item>
    </a-form>

  </AuthShell>
</template>

<script setup lang="ts">
  import { ref, reactive, onMounted } from 'vue'
  import { useRouter, useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    UserOutlined,
    LockOutlined
  } from '@ant-design/icons-vue'
  import AuthShell from '@/components/auth/AuthShell.vue'
  import { useUserStore } from '@/stores'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)

  const formState = reactive({
    username: '',
    password: '',
    remember: true
  })

  const rules: Record<string, Rule[]> = {
    username: [
      { required: true, message: t('auth.validation.accountRequired'), trigger: 'blur' }
    ],
    password: [
      { required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' }
    ]
  }

  const handleSubmit = async () => {
    loading.value = true
    try {
      await userStore.login({
        username: formState.username,
        password: formState.password,
        remember: formState.remember
      })
      message.success(t('auth.loginSuccess'))
      const redirect = route.query.redirect as string
      router.push(redirect || '/')
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 从统一认证登出回跳（GLO 带 ?sso_logout=1）：提示一次并把标记从地址栏清掉，
  // 避免刷新页面重复提示；这里**不**自动发起 SSO 登录，仍由用户选择登录方式。
  onMounted(() => {
    if (!route.query.sso_logout) {
      return
    }
    message.info(t('auth.ssoLogoutSuccess'))
    const restQuery = { ...route.query }
    delete restQuery.sso_logout
    router.replace({ path: route.path, query: restQuery })
  })

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }
</style>
