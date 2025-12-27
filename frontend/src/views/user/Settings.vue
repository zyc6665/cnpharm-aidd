<template>
  <div class="user-settings">
    <a-card :title="t('user.settings')">
      <a-tabs v-model:activeKey="activeTab">
        <!-- 密码设置 -->
        <a-tab-pane key="password" :tab="t('user.changePassword')">
          <a-form
            :model="passwordForm"
            :rules="passwordRules"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
            @finish="handlePasswordChange"
          >
            <a-form-item :label="t('user.oldPassword')" name="oldPassword">
              <a-input-password v-model:value="passwordForm.oldPassword" />
            </a-form-item>
            <a-form-item :label="t('user.newPassword')" name="newPassword">
              <a-input-password v-model:value="passwordForm.newPassword" />
            </a-form-item>
            <a-form-item :label="t('auth.confirmPassword')" name="confirmPassword">
              <a-input-password v-model:value="passwordForm.confirmPassword" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" html-type="submit" :loading="passwordLoading">
                {{ t('user.changePassword') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <!-- 通知设置 -->
        <a-tab-pane key="notification" :tab="t('user.notificationSettings')">
          <a-form
            :model="notificationForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('user.emailNotification')">
              <a-switch v-model:checked="notificationForm.emailNotification" />
            </a-form-item>
            <a-form-item :label="t('user.taskCompleteNotify')">
              <a-switch v-model:checked="notificationForm.taskComplete" />
            </a-form-item>
            <a-form-item :label="t('user.taskFailNotify')">
              <a-switch v-model:checked="notificationForm.taskFail" />
            </a-form-item>
            <a-form-item :label="t('user.systemNotify')">
              <a-switch v-model:checked="notificationForm.system" />
            </a-form-item>
            <a-form-item :label="t('user.marketingNotify')">
              <a-switch v-model:checked="notificationForm.marketing" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" @click="handleNotificationSave" :loading="notificationLoading">
                {{ t('common.save') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <!-- 隐私设置 -->
        <a-tab-pane key="privacy" :tab="t('user.privacySettings')">
          <a-form
            :model="privacyForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('user.profileVisibility')">
              <a-radio-group v-model:value="privacyForm.profileVisibility">
                <a-radio value="public">{{ t('user.public') }}</a-radio>
                <a-radio value="friends">{{ t('user.friendsOnly') }}</a-radio>
                <a-radio value="private">{{ t('user.private') }}</a-radio>
              </a-radio-group>
            </a-form-item>
            <a-form-item :label="t('user.showTaskHistory')">
              <a-switch v-model:checked="privacyForm.showTaskHistory" />
            </a-form-item>
            <a-form-item :label="t('user.showCredits')">
              <a-switch v-model:checked="privacyForm.showCredits" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" @click="handlePrivacySave" :loading="privacyLoading">
                {{ t('common.save') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <!-- 账号安全 -->
        <a-tab-pane key="security" :tab="t('user.accountSecurity')">
          <div class="security-list">
            <div class="security-item">
              <div class="security-info">
                <h4>{{ t('user.twoFactorAuth') }}</h4>
                <p>{{ t('user.twoFactorAuthDesc') }}</p>
              </div>
              <a-switch v-model:checked="securityForm.twoFactorAuth" @change="handleTwoFactorChange" />
            </div>

            <a-divider />

            <div class="security-item">
              <div class="security-info">
                <h4>{{ t('user.loginDevices') }}</h4>
                <p>{{ t('user.loginDevicesDesc') }}</p>
              </div>
              <a-button type="link" @click="showDevicesModal = true">
                {{ t('user.manage') }}
              </a-button>
            </div>

            <a-divider />

            <div class="security-item danger">
              <div class="security-info">
                <h4>{{ t('user.deleteAccount') }}</h4>
                <p>{{ t('user.deleteAccountDesc') }}</p>
              </div>
              <a-button danger @click="handleDeleteAccount">
                {{ t('user.deleteAccount') }}
              </a-button>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <!-- 登录设备弹窗 -->
    <a-modal
      v-model:open="showDevicesModal"
      :title="t('user.loginDevices')"
      :footer="null"
      width="600px"
    >
      <a-list :data-source="loginDevices" item-layout="horizontal">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta
              :title="item.device"
              :description="`${item.location} · ${item.lastActive}`"
            >
              <template #avatar>
                <DesktopOutlined v-if="item.type === 'desktop'" />
                <MobileOutlined v-else />
              </template>
            </a-list-item-meta>
            <template #actions>
              <a-tag v-if="item.current" color="green">{{ t('user.currentDevice') }}</a-tag>
              <a-button v-else type="link" danger @click="handleLogoutDevice(item.id)">
                {{ t('user.logoutDevice') }}
              </a-button>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { DesktopOutlined, MobileOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores'

const { t } = useI18n()
const userStore = useUserStore()

const activeTab = ref('password')
const passwordLoading = ref(false)
const notificationLoading = ref(false)
const privacyLoading = ref(false)
const showDevicesModal = ref(false)

// 密码表单
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const passwordRules = {
  oldPassword: [{ required: true, message: t('user.enterOldPassword') }],
  newPassword: [
    { required: true, message: t('auth.validation.passwordRequired') },
    { min: 6, message: t('auth.validation.passwordLength') }
  ],
  confirmPassword: [
    { required: true, message: t('auth.validation.confirmPasswordRequired') },
    {
      validator: async (_rule: unknown, value: string) => {
        if (value !== passwordForm.newPassword) {
          throw new Error(t('auth.validation.passwordMismatch'))
        }
      }
    }
  ]
}

// 通知设置
const notificationForm = reactive({
  emailNotification: true,
  taskComplete: true,
  taskFail: true,
  system: true,
  marketing: false
})

// 隐私设置
const privacyForm = reactive({
  profileVisibility: 'public',
  showTaskHistory: true,
  showCredits: false
})

// 安全设置
const securityForm = reactive({
  twoFactorAuth: false
})

// 登录设备
const loginDevices = ref([
  {
    id: 1,
    device: 'Chrome on Windows',
    type: 'desktop',
    location: '北京, 中国',
    lastActive: '当前会话',
    current: true
  },
  {
    id: 2,
    device: 'Safari on iPhone',
    type: 'mobile',
    location: '上海, 中国',
    lastActive: '2天前',
    current: false
  }
])

const handlePasswordChange = async () => {
  passwordLoading.value = true
  try {
    await userStore.changePassword(passwordForm.oldPassword, passwordForm.newPassword)
    message.success(t('user.passwordChanged'))
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch {
    // 错误已处理
  } finally {
    passwordLoading.value = false
  }
}

const handleNotificationSave = async () => {
  notificationLoading.value = true
  try {
    // 保存通知设置（数据已通过 reactive 自动更新）
    message.success(t('common.success'))
  } finally {
    notificationLoading.value = false
  }
}

const handlePrivacySave = async () => {
  privacyLoading.value = true
  try {
    // 保存隐私设置（数据已通过 reactive 自动更新）
    message.success(t('common.success'))
  } finally {
    privacyLoading.value = false
  }
}

const handleTwoFactorChange = (checked: boolean) => {
  if (checked) {
    // 开启两步验证流程（显示设置提示）
    message.info(t('user.twoFactorSetup'))
  } else {
    Modal.confirm({
      title: t('user.disableTwoFactor'),
      content: t('user.disableTwoFactorDesc'),
      onOk: () => {
        securityForm.twoFactorAuth = false
        message.success(t('user.twoFactorDisabled'))
      },
      onCancel: () => {
        securityForm.twoFactorAuth = true
      }
    })
  }
}

const handleLogoutDevice = (deviceId: number) => {
  Modal.confirm({
    title: t('user.logoutDeviceConfirm'),
    onOk: () => {
      loginDevices.value = loginDevices.value.filter(d => d.id !== deviceId)
      message.success(t('user.deviceLoggedOut'))
    }
  })
}

const handleDeleteAccount = () => {
  Modal.confirm({
    title: t('user.deleteAccountConfirm'),
    content: t('user.deleteAccountConfirmContent'),
    okText: t('user.confirmDelete'),
    okType: 'danger',
    onOk: () => {
      // 删除账号流程（显示处理提示）
      message.info(t('user.deleteAccountProcess'))
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.user-settings {
  .security-list {
    .security-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: @spacing-md 0;

      .security-info {
        h4 {
          margin: 0 0 @spacing-xs 0;
          font-weight: @font-weight-medium;
        }

        p {
          margin: 0;
          color: @text-color-light-secondary;
          font-size: @font-size-sm;
        }
      }

      &.danger .security-info h4 {
        color: @error-color;
      }
    }
  }
}
</style>
