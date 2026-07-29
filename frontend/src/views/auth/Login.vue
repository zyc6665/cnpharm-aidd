<template>
  <AuthShell :title="t('auth.login')">
    <a-form
      ref="formRef"
      :model="formState"
      :rules="rules"
      layout="vertical"
      @finish="handleSubmit"
    >
          <a-form-item name="email" :label="t('auth.email')">
            <a-input
              v-model:value="formState.email"
              size="large"
              :placeholder="t('auth.validation.emailRequired')"
            >
              <template #prefix>
                <MailOutlined />
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
            <div class="form-extra">
              <a-checkbox v-model:checked="formState.remember">
                {{ t('auth.rememberMe') }}
              </a-checkbox>
              <router-link to="/forgot-password" class="forgot-link">
                {{ t('auth.forgotPassword') }}
              </router-link>
            </div>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" size="large" block :loading="loading">
              {{ t('auth.login') }}
            </a-button>
          </a-form-item>

          <div class="auth-footer">
            <span>{{ t('auth.noAccount') }}</span>
            <router-link to="/register">{{ t('auth.goRegister') }}</router-link>
          </div>
    </a-form>

  </AuthShell>
</template>

<script setup lang="ts">
  import { ref, reactive } from 'vue'
  import { useRouter, useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    MailOutlined,
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
    email: '',
    password: '',
    remember: true
  })

  const rules: Record<string, Rule[]> = {
    email: [
      { required: true, message: t('auth.validation.emailRequired'), trigger: 'blur' },
      { type: 'email', message: t('auth.validation.emailInvalid'), trigger: 'blur' }
    ],
    password: [
      { required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' }
    ]
  }

  const handleSubmit = async () => {
    loading.value = true
    try {
      await userStore.login({
        email: formState.email,
        password: formState.password
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

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .form-extra {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .forgot-link {
      color: @accent-color;

      &:hover {
        color: @accent-color-hover;
      }
    }
  }

  .auth-footer {
    text-align: center;
    margin-top: @spacing-md;
    color: @text-color-light-secondary;

    a {
      color: @accent-color;
      margin-left: @spacing-xs;

      &:hover {
        color: @accent-color-hover;
      }
    }
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
