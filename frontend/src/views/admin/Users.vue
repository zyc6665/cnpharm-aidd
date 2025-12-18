<template>
  <div class="admin-users">
    <div class="page-header">
      <h2>{{ t('admin.users') }}</h2>
      <a-button type="primary" @click="showCreateModal = true">
        <PlusOutlined /> {{ t('admin.createUser') }}
      </a-button>
    </div>

    <!-- 搜索筛选 -->
    <a-card class="filter-card">
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchUserPlaceholder')"
            style="width: 200px"
            @pressEnter="handleSearch"
          />
        </a-form-item>
        <a-form-item :label="t('admin.role')">
          <a-select
            v-model:value="filters.role"
            :placeholder="t('common.all')"
            style="width: 120px"
            allowClear
          >
            <a-select-option value="admin">{{ t('user.role.admin') }}</a-select-option>
            <a-select-option value="vip">{{ t('user.role.vip') }}</a-select-option>
            <a-select-option value="user">{{ t('user.role.user') }}</a-select-option>
            <a-select-option value="guest">{{ t('user.role.guest') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 120px"
            allowClear
          >
            <a-select-option value="active">{{ t('admin.active') }}</a-select-option>
            <a-select-option value="inactive">{{ t('admin.inactive') }}</a-select-option>
            <a-select-option value="banned">{{ t('admin.banned') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <SearchOutlined /> {{ t('common.search') }}
            </a-button>
            <a-button @click="handleReset">
              <ReloadOutlined /> {{ t('common.reset') }}
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 用户列表 -->
    <a-card>
      <a-table
        :columns="columns"
        :data-source="users"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <div class="user-cell">
              <a-avatar :size="40" :src="record.avatar">
                {{ record.username?.charAt(0).toUpperCase() }}
              </a-avatar>
              <div class="user-info">
                <span class="username">{{ record.username }}</span>
                <span class="email">{{ record.email }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'role'">
            <a-tag :color="getRoleColor(record.role)">
              {{ t(`user.role.${record.role}`) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-badge
              :status="getStatusBadge(record.status)"
              :text="t(`admin.${record.status}`)"
            />
          </template>
          <template v-else-if="column.key === 'credits'">
            💎 {{ record.credits || 0 }}
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-tooltip :title="t('common.edit')">
                <a-button type="link" size="small" @click="handleEdit(record)">
                  <EditOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip :title="t('admin.resetPassword')">
                <a-button type="link" size="small" @click="handleResetPassword(record)">
                  <KeyOutlined />
                </a-button>
              </a-tooltip>
              <a-dropdown>
                <a-button type="link" size="small">
                  <MoreOutlined />
                </a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item v-if="record.status !== 'banned'" @click="handleBan(record)">
                      <StopOutlined /> {{ t('admin.banUser') }}
                    </a-menu-item>
                    <a-menu-item v-else @click="handleUnban(record)">
                      <CheckOutlined /> {{ t('admin.unbanUser') }}
                    </a-menu-item>
                    <a-menu-item danger @click="handleDelete(record)">
                      <DeleteOutlined /> {{ t('common.delete') }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 创建/编辑用户弹窗 -->
    <a-modal
      v-model:open="showCreateModal"
      :title="editingUser ? t('admin.editUser') : t('admin.createUser')"
      @ok="handleSaveUser"
      :confirm-loading="saveLoading"
    >
      <a-form
        ref="formRef"
        :model="userForm"
        :rules="formRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 16 }"
      >
        <a-form-item :label="t('auth.username')" name="username">
          <a-input v-model:value="userForm.username" />
        </a-form-item>
        <a-form-item :label="t('auth.email')" name="email">
          <a-input v-model:value="userForm.email" />
        </a-form-item>
        <a-form-item v-if="!editingUser" :label="t('auth.password')" name="password">
          <a-input-password v-model:value="userForm.password" />
        </a-form-item>
        <a-form-item :label="t('admin.role')" name="role">
          <a-select v-model:value="userForm.role">
            <a-select-option value="admin">{{ t('user.role.admin') }}</a-select-option>
            <a-select-option value="vip">{{ t('user.role.vip') }}</a-select-option>
            <a-select-option value="user">{{ t('user.role.user') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.credits')" name="credits">
          <a-input-number v-model:value="userForm.credits" :min="0" style="width: 100%" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PlusOutlined,
  SearchOutlined,
  ReloadOutlined,
  EditOutlined,
  KeyOutlined,
  MoreOutlined,
  StopOutlined,
  CheckOutlined,
  DeleteOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import type { FormInstance } from 'ant-design-vue'
import dayjs from 'dayjs'

const { t } = useI18n()

const loading = ref(false)
const saveLoading = ref(false)
const showCreateModal = ref(false)
const editingUser = ref<any>(null)
const formRef = ref<FormInstance>()

const filters = reactive({
  keyword: '',
  role: undefined as string | undefined,
  status: undefined as string | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 100
})

const userForm = reactive({
  username: '',
  email: '',
  password: '',
  role: 'user',
  credits: 0
})

const formRules = {
  username: [
    { required: true, message: t('auth.validation.usernameRequired') },
    { min: 3, max: 20, message: t('auth.validation.usernameLength') }
  ],
  email: [
    { required: true, message: t('auth.validation.emailRequired') },
    { type: 'email', message: t('auth.validation.emailInvalid') }
  ],
  password: [
    { required: true, message: t('auth.validation.passwordRequired') },
    { min: 6, message: t('auth.validation.passwordLength') }
  ],
  role: [{ required: true, message: t('admin.selectRole') }]
}

// 模拟用户数据
const users = ref([
  { id: 1, username: 'admin', email: 'admin@example.com', role: 'admin', status: 'active', credits: 9999, created_at: '2024-01-01T00:00:00' },
  { id: 2, username: 'vipuser', email: 'vip@example.com', role: 'vip', status: 'active', credits: 1000, created_at: '2024-01-10T10:00:00' },
  { id: 3, username: 'researcher', email: 'researcher@example.com', role: 'user', status: 'active', credits: 200, created_at: '2024-01-15T14:30:00' },
  { id: 4, username: 'scientist', email: 'scientist@example.com', role: 'user', status: 'inactive', credits: 50, created_at: '2024-01-12T09:15:00' },
  { id: 5, username: 'banned_user', email: 'banned@example.com', role: 'user', status: 'banned', credits: 0, created_at: '2024-01-08T16:45:00' }
])

const columns = computed(() => [
  { title: t('admin.userInfo'), key: 'user', width: 250 },
  { title: t('admin.role'), key: 'role', width: 100 },
  { title: t('admin.status'), key: 'status', width: 100 },
  { title: t('admin.credits'), key: 'credits', width: 100 },
  { title: t('admin.registerTime'), key: 'created_at', width: 150 },
  { title: t('common.actions'), key: 'actions', width: 150, fixed: 'right' }
])

const getRoleColor = (role: string) => {
  const colors: Record<string, string> = {
    admin: 'red',
    vip: 'gold',
    user: 'blue',
    guest: 'default'
  }
  return colors[role] || 'default'
}

const getStatusBadge = (status: string) => {
  const badges: Record<string, 'success' | 'default' | 'error'> = {
    active: 'success',
    inactive: 'default',
    banned: 'error'
  }
  return badges[status] || 'default'
}

const formatDate = (date: string) => {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

const handleSearch = () => {
  pagination.current = 1
  // TODO: 实现搜索
}

const handleReset = () => {
  filters.keyword = ''
  filters.role = undefined
  filters.status = undefined
  handleSearch()
}

const handleTableChange = (pag: any) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  // TODO: 加载数据
}

const handleEdit = (record: any) => {
  editingUser.value = record
  userForm.username = record.username
  userForm.email = record.email
  userForm.password = ''
  userForm.role = record.role
  userForm.credits = record.credits
  showCreateModal.value = true
}

const handleSaveUser = async () => {
  try {
    await formRef.value?.validate()
    saveLoading.value = true
    // TODO: 保存用户
    message.success(t('common.success'))
    showCreateModal.value = false
    resetForm()
  } catch {
    // 验证失败
  } finally {
    saveLoading.value = false
  }
}

const resetForm = () => {
  editingUser.value = null
  userForm.username = ''
  userForm.email = ''
  userForm.password = ''
  userForm.role = 'user'
  userForm.credits = 0
}

const handleResetPassword = (record: any) => {
  Modal.confirm({
    title: t('admin.resetPasswordConfirm'),
    content: t('admin.resetPasswordConfirmContent', { username: record.username }),
    onOk: () => {
      // TODO: 重置密码
      message.success(t('admin.resetPasswordSuccess'))
    }
  })
}

const handleBan = (record: any) => {
  Modal.confirm({
    title: t('admin.banUserConfirm'),
    content: t('admin.banUserConfirmContent', { username: record.username }),
    okType: 'danger',
    onOk: () => {
      record.status = 'banned'
      message.success(t('admin.banUserSuccess'))
    }
  })
}

const handleUnban = (record: any) => {
  record.status = 'active'
  message.success(t('admin.unbanUserSuccess'))
}

const handleDelete = (record: any) => {
  Modal.confirm({
    title: t('admin.deleteUserConfirm'),
    content: t('admin.deleteUserConfirmContent', { username: record.username }),
    okType: 'danger',
    onOk: () => {
      users.value = users.value.filter(u => u.id !== record.id)
      message.success(t('common.success'))
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-users {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
    }
  }

  .filter-card {
    margin-bottom: @spacing-lg;
  }

  .user-cell {
    display: flex;
    align-items: center;
    gap: @spacing-sm;

    .user-info {
      display: flex;
      flex-direction: column;

      .username {
        font-weight: @font-weight-medium;
      }

      .email {
        font-size: @font-size-sm;
        color: @text-color-light-secondary;
      }
    }
  }
}
</style>
