<template>
  <AuthShell :title="t('auth.register')">
    <a-form
      ref="formRef"
      :model="formState"
      :rules="rules"
      layout="vertical"
      @finish="handleSubmit"
    >
          <a-form-item name="username" :label="t('auth.username')">
            <a-input
              v-model:value="formState.username"
              size="large"
              :placeholder="t('auth.validation.usernameRequired')"
            >
              <template #prefix>
                <UserOutlined />
              </template>
            </a-input>
          </a-form-item>

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

          <!-- 邮箱验证码 -->
          <a-form-item name="code" :label="t('auth.verificationCode')">
            <a-input-group compact>
              <a-input
                v-model:value="formState.code"
                size="large"
                style="width: calc(100% - 120px)"
                :placeholder="t('auth.validation.codeRequired')"
              >
                <template #prefix>
                  <SafetyOutlined />
                </template>
              </a-input>
              <a-button
                size="large"
                :disabled="codeSending || countdown > 0"
                :loading="codeSending"
                style="width: 120px"
                @click="handleSendCode"
              >
                {{ countdown > 0 ? `${countdown}s` : t('auth.sendCode') }}
              </a-button>
            </a-input-group>
          </a-form-item>

          <a-form-item name="password" :label="t('auth.password')">
            <a-input-password
              v-model:value="formState.password"
              size="large"
              :placeholder="t('auth.validation.passwordRequired')"
              @input="checkPasswordStrength"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
            <!-- 密码强度指示器 -->
            <div v-if="formState.password" class="password-strength">
              <div class="strength-bars">
                <span
                  v-for="i in 4"
                  :key="i"
                  class="strength-bar"
                  :class="{ active: passwordStrength >= i }"
                  :style="{ backgroundColor: passwordStrength >= i ? strengthColor : '' }"
                />
              </div>
              <span class="strength-text" :style="{ color: strengthColor }">
                {{ strengthText }}
              </span>
            </div>
          </a-form-item>

          <a-form-item name="confirmPassword" :label="t('auth.confirmPassword')">
            <a-input-password
              v-model:value="formState.confirmPassword"
              size="large"
              :placeholder="t('auth.validation.confirmPasswordRequired')"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
          </a-form-item>

          <!-- 邀请码（可选） -->
          <a-form-item name="invitation_code" :label="t('auth.invitationCode')">
            <a-input
              v-model:value="formState.invitation_code"
              size="large"
              :placeholder="t('auth.invitationCodePlaceholder')"
              @blur="validateInvitation"
            >
              <template #prefix>
                <GiftOutlined />
              </template>
              <template v-if="invitationValidating" #suffix>
                <LoadingOutlined />
              </template>
            </a-input>
          </a-form-item>

          <!-- 服务条款 -->
          <a-form-item name="agreement">
            <a-checkbox v-model:checked="formState.agreement">
              {{ t('auth.agreementPrefix') }}
              <a href="/terms" target="_blank">{{ t('auth.termsOfService') }}</a>
              {{ t('auth.agreementAnd') }}
              <a href="/privacy" target="_blank">{{ t('auth.privacyPolicy') }}</a>
            </a-checkbox>
          </a-form-item>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              block
              :loading="loading"
              :disabled="!formState.agreement"
            >
              {{ t('auth.register') }}
            </a-button>
          </a-form-item>

          <div class="auth-footer">
            <span>{{ t('auth.hasAccount') }}</span>
            <router-link to="/login">{{ t('auth.goLogin') }}</router-link>
          </div>
    </a-form>
  </AuthShell>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onBeforeUnmount } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    UserOutlined,
    LockOutlined,
    MailOutlined,
    SafetyOutlined,
    GiftOutlined,
    LoadingOutlined
  } from '@ant-design/icons-vue'
  import AuthShell from '@/components/auth/AuthShell.vue'
  import { useUserStore } from '@/stores'
  import { validateInvitationCode } from '@/api/auth'

  const router = useRouter()
  const { t } = useI18n()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const codeSending = ref(false)
  const countdown = ref(0)
  const countdownTimer = ref<NodeJS.Timeout | null>(null)
  const invitationValidating = ref(false)

  // 密码强度
  const passwordStrength = ref(0)
  const strengthColor = computed(() => {
    const colors = ['', '#ff4d4f', '#faad14', '#52c41a', '#1890ff']
    return colors[passwordStrength.value] || ''
  })
  const strengthText = computed(() => {
    const texts = ['', t('auth.passwordWeak'), t('auth.passwordMedium'), t('auth.passwordStrong'), t('auth.passwordVeryStrong')]
    return texts[passwordStrength.value] || ''
  })

  const formState = reactive({
    username: '',
    email: '',
    code: '',
    password: '',
    confirmPassword: '',
    invitation_code: '',
    agreement: false
  })

  const validateConfirmPassword = async (_rule: Rule, value: string) => {
    if (value && value !== formState.password) {
      throw new Error(t('auth.validation.passwordMismatch'))
    }
  }

  const validateAgreement = async (_rule: Rule, value: boolean) => {
    if (!value) {
      throw new Error(t('auth.validation.agreementRequired'))
    }
  }

  const rules: Record<string, Rule[]> = {
    username: [
      { required: true, message: t('auth.validation.usernameRequired'), trigger: 'blur' },
      { min: 3, max: 20, message: t('auth.validation.usernameLength'), trigger: 'blur' },
      { pattern: /^[a-zA-Z0-9_]+$/, message: t('auth.validation.usernameFormat'), trigger: 'blur' }
    ],
    email: [
      { required: true, message: t('auth.validation.emailRequired'), trigger: 'blur' },
      { type: 'email', message: t('auth.validation.emailInvalid'), trigger: 'blur' }
    ],
    code: [
      { required: true, message: t('auth.validation.codeRequired'), trigger: 'blur' },
      { len: 6, message: t('auth.validation.codeLength'), trigger: 'blur' }
    ],
    password: [
      { required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' },
      { min: 8, message: t('auth.validation.passwordLength'), trigger: 'blur' }
    ],
    confirmPassword: [
      { required: true, message: t('auth.validation.confirmPasswordRequired'), trigger: 'blur' },
      { validator: validateConfirmPassword, trigger: 'blur' }
    ],
    agreement: [
      { validator: validateAgreement, trigger: 'change' }
    ]
  }

  // 检查密码强度
  const checkPasswordStrength = () => {
    const password = formState.password
    let strength = 0
    if (password.length >= 8) strength++
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++
    if (/\d/.test(password)) strength++
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength++
    passwordStrength.value = strength
  }

  // 发送验证码
  const handleSendCode = async () => {
    // 先验证邮箱
    try {
      await formRef.value?.validateFields(['email'])
    } catch {
      return
    }

    codeSending.value = true
    try {
      await userStore.sendEmailCode(formState.email)
      message.success(t('auth.codeSent'))
      // 开始倒计时
      countdown.value = 60
      countdownTimer.value = setInterval(() => {
        countdown.value--
        if (countdown.value <= 0 && countdownTimer.value) {
          clearInterval(countdownTimer.value)
          countdownTimer.value = null
        }
      }, 1000)
    } catch {
      // 错误已在请求层处理
    } finally {
      codeSending.value = false
    }
  }

  // 验证邀请码
  const validateInvitation = async () => {
    if (!formState.invitation_code) {
      return
    }

    invitationValidating.value = true
    try {
      const res = await validateInvitationCode(formState.invitation_code)
      if (!res.data.valid) {
        message.warning(t('auth.invalidInvitationCode'))
      }
    } catch {
      // 错误已在请求层处理
    } finally {
      invitationValidating.value = false
    }
  }

  const handleSubmit = async () => {
    loading.value = true
    try {
      await userStore.register({
        email: formState.email,
        password: formState.password,
        verification_code: formState.code,
        display_name: formState.username || undefined
      })
      message.success(t('auth.registerSuccess'))
      router.push('/')
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 清理倒计时
  onBeforeUnmount(() => {
    if (countdownTimer.value) {
      clearInterval(countdownTimer.value)
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  // 密码强度指示器
  .password-strength {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    margin-top: @spacing-xs;

    .strength-bars {
      display: flex;
      gap: 4px;

      .strength-bar {
        width: 40px;
        height: 4px;
        background-color: #e8e8e8;
        border-radius: 2px;
        transition: background-color 0.3s;
      }
    }

    .strength-text {
      font-size: @font-size-sm;
      transition: color 0.3s;
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

    &:disabled {
      background: #d9d9d9;
      border-color: #d9d9d9;
    }
  }

  :deep(.ant-checkbox-wrapper) {
    a {
      color: @accent-color;

      &:hover {
        color: @accent-color-hover;
      }
    }
  }
</style>
