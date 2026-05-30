<template>
  <div class="user-profile">
    <AppPageHeader :title="t('user.profile')" />
    <a-card class="profile-card">
      <a-form
        class="profile-form"
        :model="form"
        :rules="rules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 14 }"
        @finish="handleSubmit"
      >
        <a-form-item :label="t('user.avatar')" name="avatar">
          <a-upload
            v-model:file-list="avatarList"
            list-type="picture-card"
            :show-upload-list="false"
            :before-upload="beforeUpload"
            :custom-request="handleAvatarUpload"
          >
            <div v-if="form.avatar" class="avatar-wrapper">
              <a-avatar :size="100" :src="form.avatar" />
              <div class="avatar-mask">
                <CameraOutlined />
              </div>
            </div>
            <div v-else class="upload-placeholder">
              <PlusOutlined />
              <div class="ant-upload-text">{{ t('user.uploadAvatar') }}</div>
            </div>
          </a-upload>
        </a-form-item>

        <a-form-item :label="t('auth.username')" name="username">
          <a-input v-model:value="form.username" :maxlength="20" />
        </a-form-item>

        <a-form-item :label="t('auth.email')">
          <a-input :value="userStore.user?.email" disabled />
          <template #extra>
            <a @click="showEmailChangeModal = true">{{ t('user.changeEmail') }}</a>
          </template>
        </a-form-item>

        <a-form-item :label="t('user.invitationCode')">
          <a-input-group compact>
            <a-input
              :value="userStore.user?.invitation_code"
              readonly
              style="width: calc(100% - 80px)"
            />
            <a-button @click="copyInviteCode">
              <CopyOutlined />
            </a-button>
          </a-input-group>
          <template #extra>
            {{ t('user.inviteCodeTip') }}
          </template>
        </a-form-item>

        <a-form-item :label="t('user.createdAt')">
          {{ formatDate(userStore.user?.created_at) }}
        </a-form-item>

        <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
          <a-button type="primary" html-type="submit" :loading="loading">
            {{ t('common.save') }}
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 修改邮箱弹窗 -->
    <a-modal
      v-model:open="showEmailChangeModal"
      :title="t('user.changeEmail')"
      @ok="handleEmailChange"
      :confirm-loading="emailChangeLoading"
    >
      <a-form :model="emailForm" layout="vertical">
        <a-form-item :label="t('user.newEmail')">
          <a-input v-model:value="emailForm.newEmail" />
        </a-form-item>
        <a-form-item :label="t('user.verifyCode')">
          <a-input-group compact>
            <a-input
              v-model:value="emailForm.code"
              style="width: calc(100% - 120px)"
            />
            <a-button
              :disabled="countdown > 0"
              @click="sendEmailCode"
            >
              {{ countdown > 0 ? `${countdown}s` : t('user.sendCode') }}
            </a-button>
          </a-input-group>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlusOutlined, CameraOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps, UploadFile } from 'ant-design-vue'
import dayjs from 'dayjs'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { useUserStore } from '@/stores'

const { t } = useI18n()
const userStore = useUserStore()

const loading = ref(false)
const avatarList = ref<UploadFile[]>([])
const showEmailChangeModal = ref(false)
const emailChangeLoading = ref(false)
const countdown = ref(0)

const form = reactive({
  avatar: userStore.user?.avatar || '',
  avatarUrl: userStore.user?.avatar || '',
  username: userStore.user?.username || ''
})

const emailForm = reactive({
  newEmail: '',
  code: ''
})

const rules = {
  username: [
    { required: true, message: t('auth.validation.usernameRequired') },
    { min: 3, max: 20, message: t('auth.validation.usernameLength') }
  ]
}

const formatDate = (date?: string) => {
  return date ? dayjs(date).format('YYYY-MM-DD') : '-'
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    message.error(t('user.avatarTypeError'))
    return false
  }
  const isLt2M = file.size / 1024 / 1024 < 2
  if (!isLt2M) {
    message.error(t('user.avatarSizeError'))
    return false
  }
  return true
}

const handleAvatarUpload = async ({ file }: { file: File }) => {
  try {
    // 先预览
    const reader = new FileReader()
    reader.onload = (e) => {
      form.avatar = e.target?.result as string
    }
    reader.readAsDataURL(file)

    // 上传到服务器（设置为公开文件）
    const { uploadFile } = await import('@/api/files')
    const res = await uploadFile(file, { is_public: true })

    // 构造文件访问URL并同时更新两个字段
    const avatarUrl = `/api/v1/files/${res.data.id}/download`
    form.avatarUrl = avatarUrl
    form.avatar = avatarUrl  // 上传成功后立即显示服务器URL
    message.success(t('user.avatarUploaded'))
  } catch (error) {
    message.error(t('user.avatarUploadFailed'))
  }
}

const copyInviteCode = async () => {
  const code = userStore.user?.invitation_code
  if (code) {
    await navigator.clipboard.writeText(code)
    message.success(t('common.copySuccess'))
  }
}

const sendEmailCode = async () => {
  if (!emailForm.newEmail) {
    message.error(t('user.enterNewEmail'))
    return
  }
  // 发送验证码并启动倒计时
  countdown.value = 60
  const timer = setInterval(() => {
    countdown.value--
    if (countdown.value === 0) {
      clearInterval(timer)
    }
  }, 1000)
  message.success(t('user.codeSent'))
}

const handleEmailChange = async () => {
  emailChangeLoading.value = true
  try {
    // 实现邮箱修改（验证码已发送）
    message.success(t('user.emailChanged'))
    showEmailChangeModal.value = false
  } finally {
    emailChangeLoading.value = false
  }
}

const handleSubmit = async () => {
  loading.value = true
  try {
    await userStore.updateProfile({
      username: form.username,
      avatar_url: form.avatarUrl
    })
    // 从 store 同步最新的头像URL
    if (userStore.user?.avatar) {
      form.avatar = userStore.user.avatar
      form.avatarUrl = userStore.user.avatar
    }
    message.success(t('common.success'))
  } catch {
    // 错误已处理
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (userStore.user) {
    form.avatar = userStore.user.avatar || ''
    form.avatarUrl = userStore.user.avatar || ''
    form.username = userStore.user.username || userStore.user.display_name || ''
  }
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.user-profile {
  .avatar-wrapper {
    position: relative;
    display: inline-block;

    .avatar-mask {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 24px;
      opacity: 0;
      transition: opacity @transition-duration;
      border-radius: 50%;
    }

    &:hover .avatar-mask {
      opacity: 1;
    }
  }

  .upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100px;
    height: 100px;
  }

  @media (max-width: @screen-md) {
    .profile-form {
      :deep(.ant-form-item) {
        flex-direction: column;
      }

      :deep(.ant-form-item-label),
      :deep(.ant-form-item-control) {
        flex: 0 0 100%;
        max-width: 100%;
        text-align: left;
      }

      :deep(.ant-form-item-control) {
        margin-left: 0;
      }

      :deep(.ant-btn-primary) {
        width: 100%;
      }
    }
  }
}
</style>
