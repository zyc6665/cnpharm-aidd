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

          <!-- 游客模式入口 -->
          <a-form-item>
            <a-button
              size="large"
              block
              :loading="guestLoading"
              class="guest-btn"
              @click="handleGuestLogin"
            >
              <EyeOutlined />
              {{ t('auth.guestMode') }}
            </a-button>
          </a-form-item>

          <div class="auth-footer">
            <span>{{ t('auth.noAccount') }}</span>
            <router-link to="/register">{{ t('auth.goRegister') }}</router-link>
          </div>
    </a-form>

    <!-- 游客模式确认弹窗 -->
    <a-modal
      v-model:open="guestModalVisible"
      :title="t('auth.guestMode')"
      :ok-text="t('auth.continueAsGuest')"
      :cancel-text="t('common.cancel')"
      @ok="confirmGuestLogin"
      @cancel="guestModalVisible = false"
    >
      <div class="guest-modal-content">
        <a-alert
          type="info"
          show-icon
          :message="t('auth.guestModeTitle')"
          :description="t('auth.guestModeDesc')"
          style="margin-bottom: 16px"
        />
        <div class="guest-limitations">
          <h4>{{ t('auth.guestLimitations') }}</h4>
          <ul>
            <li>
              <CloseCircleOutlined class="limitation-icon" />
              {{ t('auth.guestLimit1') }}
            </li>
            <li>
              <CloseCircleOutlined class="limitation-icon" />
              {{ t('auth.guestLimit2') }}
            </li>
            <li>
              <CloseCircleOutlined class="limitation-icon" />
              {{ t('auth.guestLimit3') }}
            </li>
          </ul>
        </div>
        <div class="guest-benefits">
          <h4>{{ t('auth.guestBenefits') }}</h4>
          <ul>
            <li>
              <CheckCircleOutlined class="benefit-icon" />
              {{ t('auth.guestBenefit1') }}
            </li>
            <li>
              <CheckCircleOutlined class="benefit-icon" />
              {{ t('auth.guestBenefit2') }}
            </li>
          </ul>
        </div>
      </div>
    </a-modal>
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
    LockOutlined,
    EyeOutlined,
    CloseCircleOutlined,
    CheckCircleOutlined
  } from '@ant-design/icons-vue'
  import AuthShell from '@/components/auth/AuthShell.vue'
  import { useUserStore } from '@/stores'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const guestLoading = ref(false)
  const guestModalVisible = ref(false)

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

  // 点击游客模式按钮，弹出确认弹窗
  const handleGuestLogin = () => {
    guestModalVisible.value = true
  }

  // 确认以游客模式进入
  const confirmGuestLogin = async () => {
    guestLoading.value = true
    guestModalVisible.value = false
    try {
      await userStore.guestLogin()
      message.success(t('auth.guestLoginSuccess'))
      router.push('/')
    } catch {
      // 错误已在请求层处理
    } finally {
      guestLoading.value = false
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

  .guest-btn {
    border-style: dashed;
    color: @text-color-light-secondary;

    &:hover {
      color: @accent-color;
      border-color: @accent-color;
    }

    .anticon {
      margin-right: @spacing-xs;
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

  // 游客模式弹窗内容
  .guest-modal-content {
    .guest-limitations,
    .guest-benefits {
      h4 {
        font-size: @font-size-sm;
        font-weight: @font-weight-medium;
        margin-bottom: @spacing-sm;
        color: @text-color-light;
      }

      ul {
        list-style: none;
        padding: 0;
        margin: 0 0 @spacing-md 0;

        li {
          display: flex;
          align-items: center;
          gap: @spacing-xs;
          padding: @spacing-xs 0;
          font-size: @font-size-sm;
        }
      }
    }

    .limitation-icon {
      color: @error-color;
    }

    .benefit-icon {
      color: @success-color;
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
