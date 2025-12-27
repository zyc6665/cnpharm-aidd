<template>
  <div class="user-center-page">
    <div class="container">
      <a-row :gutter="24">
        <!-- 左侧菜单 -->
        <a-col :xs="24" :md="6">
          <div class="user-sidebar">
            <div class="user-profile-card">
              <a-avatar :size="80" :src="userStore.user?.avatar">
                <template #icon><UserOutlined /></template>
              </a-avatar>
              <h3 class="username">{{ userStore.user?.username || t('user.guest') }}</h3>
              <p class="email">{{ userStore.user?.email || '' }}</p>
              <a-tag :color="getRoleColor()" class="role-tag">
                {{ getRoleName() }}
              </a-tag>
            </div>

            <a-menu
              v-model:selectedKeys="selectedKeys"
              mode="inline"
              class="user-menu"
            >
              <a-menu-item key="profile" @click="navigate('profile')">
                <UserOutlined />
                {{ t('user.profile') }}
              </a-menu-item>
              <a-menu-item key="settings" @click="navigate('settings')">
                <SettingOutlined />
                {{ t('user.settings') }}
              </a-menu-item>
              <a-menu-item key="favorites" @click="navigate('favorites')">
                <HeartOutlined />
                {{ t('user.favorites') }}
              </a-menu-item>
              <a-menu-item key="credits" @click="navigate('credits')">
                <WalletOutlined />
                {{ t('nav.credits') }}
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" danger @click="handleLogout">
                <LogoutOutlined />
                {{ t('nav.logout') }}
              </a-menu-item>
            </a-menu>
          </div>
        </a-col>

        <!-- 右侧内容 -->
        <a-col :xs="24" :md="18">
          <div class="user-content">
            <router-view />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  UserOutlined,
  SettingOutlined,
  HeartOutlined,
  WalletOutlined,
  LogoutOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const userStore = useUserStore()

const selectedKeys = ref<string[]>(['profile'])

// 根据当前路由更新选中菜单
watch(
  () => route.path,
  (path) => {
    if (path.includes('settings')) {
      selectedKeys.value = ['settings']
    } else if (path.includes('favorites')) {
      selectedKeys.value = ['favorites']
    } else {
      selectedKeys.value = ['profile']
    }
  },
  { immediate: true }
)

const getRoleColor = () => {
  const colors: Record<string, string> = {
    admin: 'red',
    vip: 'gold',
    user: 'blue',
    guest: 'default'
  }
  return colors[userStore.role] || 'default'
}

const getRoleName = () => {
  const names: Record<string, string> = {
    admin: t('user.role.admin'),
    vip: t('user.role.vip'),
    user: t('user.role.user'),
    guest: t('user.role.guest')
  }
  return names[userStore.role] || t('user.role.user')
}

const navigate = (key: string) => {
  if (key === 'credits') {
    router.push('/credits')
  } else if (key === 'profile') {
    router.push('/user')
  } else {
    router.push(`/user/${key}`)
  }
}

const handleLogout = () => {
  Modal.confirm({
    title: t('user.logoutConfirm'),
    content: t('user.logoutConfirmContent'),
    okText: t('common.confirm'),
    cancelText: t('common.cancel'),
    onOk: async () => {
      await userStore.logout()
      message.success(t('auth.logoutSuccess'))
      router.push('/')
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.user-center-page {
  padding: @spacing-xl 0;
  min-height: calc(100vh - @header-height - @footer-height);
  background: @bg-color-light;
}

.user-sidebar {
  position: sticky;
  top: @spacing-xl;
}

.user-profile-card {
  .card();
  text-align: center;
  margin-bottom: @spacing-lg;

  .username {
    margin: @spacing-md 0 @spacing-xs 0;
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
  }

  .email {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    margin-bottom: @spacing-sm;
  }

  .role-tag {
    margin-top: @spacing-xs;
  }
}

.user-menu {
  .card();
  padding: @spacing-sm 0;

  :deep(.ant-menu-item) {
    margin: 0;
    border-radius: 0;

    &:hover {
      background: @primary-color-light;
    }

    &.ant-menu-item-selected {
      background: @primary-color-light;
    }
  }
}

.user-content {
  min-height: 500px;
}

// 响应式
@media (max-width: @breakpoint-md) {
  .user-sidebar {
    position: static;
    margin-bottom: @spacing-lg;
  }
}
</style>
