<template>
  <AuthShell :title="t('auth.login')">
    <!-- 统一认证失败回跳：独立于 ssoEnabled 渲染，否则 /status 请求失败时用户既看不到入口也看不到原因 -->
    <a-alert
      v-if="ssoErrorText"
      data-testid="sso-error"
      type="warning"
      show-icon
      :message="t('auth.ssoErrorTitle')"
      :description="ssoErrorText + ' ' + t('auth.ssoErrorHint')"
      class="sso-error"
    />

    <!-- 统一认证主入口：放在表单外，避免被 a-form 的 submit 吞掉；href 供中键/新标签打开，点击仍走顶层跳转 -->
    <template v-if="ssoEnabled">
      <a-button
        data-testid="sso-login"
        type="primary"
        size="large"
        block
        :href="ssoAuthorizeUrl"
        @click.prevent="handleSsoLogin"
      >
        {{ t('auth.ssoLogin') }}
      </a-button>
      <p class="sso-hint">{{ t('auth.ssoLoginHint') }}</p>
      <a-divider class="sso-divider">{{ t('auth.ssoOrLocal') }}</a-divider>
    </template>

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
            <a-button
              :type="ssoEnabled ? 'default' : 'primary'"
              html-type="submit"
              size="large"
              block
              :loading="loading"
            >
              {{ t('auth.login') }}
            </a-button>
          </a-form-item>
    </a-form>

  </AuthShell>
</template>

<script setup lang="ts">
  import { ref, computed, reactive, onMounted } from 'vue'
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
  import { getSsoStatus } from '@/api/auth'
  import {
    buildSsoAuthorizeUrl,
    navigateToSso,
    resolveNextPath,
    ssoErrorKey
  } from '@/utils/sso'
  import type { SsoStatus } from '@/types/models'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)

  // 统一认证状态：探测失败按「未启用」处理，本地账号登录绝不被认证服务故障拖死
  const ssoStatus = ref<SsoStatus | null>(null)
  const ssoEnabled = ref(false)

  // ?sso_error=<码> 由后端回跳带来；未知码走通用文案，非字符串不抛错
  const ssoErrorText = computed(() => {
    const raw = route.query.sso_error
    const code = Array.isArray(raw) ? raw[0] : raw
    return code ? t(ssoErrorKey(code)) : ''
  })

  // next 必须过白名单（含拒绝 /login），否则 SSO 回流会与登录页互相跳
  const ssoAuthorizeUrl = computed(() =>
    buildSsoAuthorizeUrl(
      ssoStatus.value?.authorize_path,
      resolveNextPath(route.query.redirect),
      import.meta.env.VITE_API_BASE_URL
    )
  )

  const loadSsoStatus = async () => {
    ssoStatus.value = await getSsoStatus()
    ssoEnabled.value = Boolean(ssoStatus.value?.enabled)
  }

  const handleSsoLogin = () => {
    navigateToSso(ssoAuthorizeUrl.value)
  }

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
  const handleSsoLogoutQuery = () => {
    if (!route.query.sso_logout) {
      return
    }
    message.info(t('auth.ssoLogoutSuccess'))
    const restQuery = { ...route.query }
    delete restQuery.sso_logout
    router.replace({ path: route.path, query: restQuery })
  }

  // 顺序不能反：先取状态，再清 sso_logout 的 query（router.replace 会让后续读不到原始 query）
  onMounted(async () => {
    await loadSsoStatus()
    handleSsoLogoutQuery()
  })

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .sso-error {
    margin-bottom: 16px;
  }

  .sso-hint {
    margin: 8px 0 0;
    font-size: 12px;
    color: @text-secondary;
  }

  .sso-divider {
    margin: 20px 0 12px;
    font-size: 12px;
    color: @text-secondary;
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }
</style>
