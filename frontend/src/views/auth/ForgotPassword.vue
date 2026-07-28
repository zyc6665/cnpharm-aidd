<template>
  <AuthShell :title="t('auth.forgotPassword')" :description="t('auth.forgotPasswordDesc')">

        <!-- 步骤指示器 -->
        <a-steps :current="currentStep" size="small" class="auth-steps">
          <a-step :title="t('auth.step1Email')" />
          <a-step :title="t('auth.step2Verify')" />
          <a-step :title="t('auth.step3Reset')" />
        </a-steps>

        <!-- 步骤 1: 输入邮箱 -->
        <a-form
          v-if="currentStep === 0"
          ref="emailFormRef"
          :model="emailFormState"
          :rules="emailRules"
          layout="vertical"
          @finish="handleSendCode"
        >
          <a-form-item name="email" :label="t('auth.email')">
            <a-input
              v-model:value="emailFormState.email"
              size="large"
              :placeholder="t('auth.validation.emailRequired')"
            >
              <template #prefix>
                <MailOutlined />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" size="large" block :loading="loading">
              {{ t('auth.sendResetCode') }}
            </a-button>
          </a-form-item>
        </a-form>

        <!-- 步骤 2: 输入验证码 -->
        <a-form
          v-if="currentStep === 1"
          ref="codeFormRef"
          :model="codeFormState"
          :rules="codeRules"
          layout="vertical"
          @finish="handleVerifyCode"
        >
          <a-alert
            type="info"
            show-icon
            :message="t('auth.codeSentTo', { email: emailFormState.email })"
            style="margin-bottom: 16px"
          />

          <a-form-item name="code" :label="t('auth.verificationCode')">
            <a-input
              v-model:value="codeFormState.code"
              size="large"
              :placeholder="t('auth.validation.codeRequired')"
              :maxlength="6"
            >
              <template #prefix>
                <SafetyOutlined />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item>
            <a-space direction="vertical" style="width: 100%">
              <a-button type="primary" html-type="submit" size="large" block :loading="loading">
                {{ t('auth.verifyCode') }}
              </a-button>
              <a-button
                size="large"
                block
                :disabled="countdown > 0"
                @click="handleResendCode"
              >
                {{ countdown > 0 ? t('auth.resendCodeIn', { seconds: countdown }) : t('auth.resendCode') }}
              </a-button>
            </a-space>
          </a-form-item>
        </a-form>

        <!-- 步骤 3: 设置新密码 -->
        <a-form
          v-if="currentStep === 2"
          ref="passwordFormRef"
          :model="passwordFormState"
          :rules="passwordRules"
          layout="vertical"
          @finish="handleResetPassword"
        >
          <a-form-item name="password" :label="t('auth.newPassword')">
            <a-input-password
              v-model:value="passwordFormState.password"
              size="large"
              :placeholder="t('auth.validation.passwordRequired')"
              @input="checkPasswordStrength"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
            <!-- 密码强度指示器 -->
            <div v-if="passwordFormState.password" class="password-strength">
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

          <a-form-item name="confirmPassword" :label="t('auth.confirmNewPassword')">
            <a-input-password
              v-model:value="passwordFormState.confirmPassword"
              size="large"
              :placeholder="t('auth.validation.confirmPasswordRequired')"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" size="large" block :loading="loading">
              {{ t('auth.resetPassword') }}
            </a-button>
          </a-form-item>
        </a-form>

        <!-- 成功提示 -->
        <div v-if="currentStep === 3" class="success-result">
          <a-result
            status="success"
            :title="t('auth.resetSuccess')"
            :sub-title="t('auth.resetSuccessDesc')"
          >
            <template #extra>
              <a-button type="primary" size="large" @click="goLogin">
                {{ t('auth.goLogin') }}
              </a-button>
            </template>
          </a-result>
        </div>

        <div v-if="currentStep < 3" class="auth-footer">
          <router-link to="/login">
            <ArrowLeftOutlined /> {{ t('common.back') }} {{ t('auth.login') }}
          </router-link>
        </div>
  </AuthShell>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onBeforeUnmount } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    MailOutlined,
    SafetyOutlined,
    LockOutlined,
    ArrowLeftOutlined
  } from '@ant-design/icons-vue'
  import AuthShell from '@/components/auth/AuthShell.vue'
  import { sendEmailCode, verifyEmailCode, resetPassword } from '@/api/auth'

  const router = useRouter()
  const { t } = useI18n()

  const emailFormRef = ref<FormInstance>()
  const codeFormRef = ref<FormInstance>()
  const passwordFormRef = ref<FormInstance>()
  const loading = ref(false)
  const currentStep = ref(0)
  const countdown = ref(0)
  const countdownTimer = ref<NodeJS.Timeout | null>(null)
  const resetToken = ref('')

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

  const emailFormState = reactive({
    email: ''
  })

  const codeFormState = reactive({
    code: ''
  })

  const passwordFormState = reactive({
    password: '',
    confirmPassword: ''
  })

  const emailRules: Record<string, Rule[]> = {
    email: [
      { required: true, message: t('auth.validation.emailRequired'), trigger: 'blur' },
      { type: 'email', message: t('auth.validation.emailInvalid'), trigger: 'blur' }
    ]
  }

  const codeRules: Record<string, Rule[]> = {
    code: [
      { required: true, message: t('auth.validation.codeRequired'), trigger: 'blur' },
      { len: 6, message: t('auth.validation.codeLength'), trigger: 'blur' }
    ]
  }

  const validateConfirmPassword = async (_rule: Rule, value: string) => {
    if (value && value !== passwordFormState.password) {
      throw new Error(t('auth.validation.passwordMismatch'))
    }
  }

  const passwordRules: Record<string, Rule[]> = {
    password: [
      { required: true, message: t('auth.validation.passwordRequired'), trigger: 'blur' },
      { min: 8, message: t('auth.validation.passwordLength'), trigger: 'blur' }
    ],
    confirmPassword: [
      { required: true, message: t('auth.validation.confirmPasswordRequired'), trigger: 'blur' },
      { validator: validateConfirmPassword, trigger: 'blur' }
    ]
  }

  // 检查密码强度
  const checkPasswordStrength = () => {
    const password = passwordFormState.password
    let strength = 0
    if (password.length >= 8) strength++
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++
    if (/\d/.test(password)) strength++
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength++
    passwordStrength.value = strength
  }

  // 开始倒计时
  const startCountdown = () => {
    countdown.value = 60
    countdownTimer.value = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0 && countdownTimer.value) {
        clearInterval(countdownTimer.value)
        countdownTimer.value = null
      }
    }, 1000)
  }

  // 步骤 1: 发送验证码
  const handleSendCode = async () => {
    loading.value = true
    try {
      await sendEmailCode(emailFormState.email, 'reset_password')
      message.success(t('auth.codeSent'))
      currentStep.value = 1
      startCountdown()
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 重新发送验证码
  const handleResendCode = async () => {
    loading.value = true
    try {
      await sendEmailCode(emailFormState.email, 'reset_password')
      message.success(t('auth.codeSent'))
      startCountdown()
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 步骤 2: 验证验证码
  const handleVerifyCode = async () => {
    loading.value = true
    try {
      const res = await verifyEmailCode(emailFormState.email, codeFormState.code, 'reset_password')
      if (res.data.valid) {
        // 保存重置 token（实际实现中验证成功后后端会返回 token）
        resetToken.value = codeFormState.code
        currentStep.value = 2
      } else {
        message.error(t('auth.invalidCode'))
      }
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 步骤 3: 重置密码
  const handleResetPassword = async () => {
    loading.value = true
    try {
      await resetPassword(emailFormState.email, resetToken.value, passwordFormState.password)
      currentStep.value = 3
    } catch {
      // 错误已在请求层处理
    } finally {
      loading.value = false
    }
  }

  // 跳转登录
  const goLogin = () => {
    router.push('/login')
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

  .auth-steps {
    margin-bottom: @spacing-xl;

    :deep(.ant-steps-item-title) {
      font-size: @font-size-sm;
    }
  }

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

  .success-result {
    padding: @spacing-lg 0;
  }

  .auth-footer {
    text-align: center;
    margin-top: @spacing-md;

    a {
      color: @accent-color;
      display: inline-flex;
      align-items: center;
      gap: @spacing-xs;

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
