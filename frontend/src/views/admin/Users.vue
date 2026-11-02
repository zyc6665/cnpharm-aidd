<template>
  <div class="admin-users">
    <AppPageHeader :title="t('admin.users')">
      <template #actions>
      <a-button type="primary" @click="openCreateModal">
        {{ t('admin.createUser') }}
      </a-button>
      </template>
    </AppPageHeader>

    <a-row :gutter="16" class="stats-row">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.stats.totalUsers')" :value="stats?.total_users ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.active')" :value="stats?.active_users ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('user.role.admin')" :value="stats?.admin_users ?? 0" />
        </a-card>
      </a-col>
    </a-row>

    <AppFilterBar>
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchUserPlaceholder')"
            style="width: 220px"
            @pressEnter="handleSearch"
          />
        </a-form-item>
        <a-form-item :label="t('admin.role')">
          <a-select
            v-model:value="filters.role"
            :placeholder="t('common.all')"
            style="width: 140px"
            allowClear
          >
            <a-select-option value="admin">{{ t('user.role.admin') }}</a-select-option>
            <a-select-option value="user">{{ t('user.role.user') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 140px"
            allowClear
          >
            <a-select-option value="active">{{ t('admin.active') }}</a-select-option>
            <a-select-option value="disabled">{{ t('admin.disabled') }}</a-select-option>
            <a-select-option value="pending">{{ t('admin.pending') }}</a-select-option>
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
    </AppFilterBar>

    <a-card>
      <SkeletonList v-if="loading && users.length === 0" :count="6" />

      <AppInlineError
        v-else-if="loadError"
        data-testid="users-error"
        :title="t('admin.listStates.usersLoadError')"
        :description="t('common.listStates.errorDescription')"
        :detail="loadErrorDetail"
      >
        <a-button size="small" @click="refreshUsersPage">
          {{ t('common.listStates.retry') }}
        </a-button>
      </AppInlineError>

      <AppEmptyState
        v-else-if="users.length === 0"
        :title="t('admin.listStates.usersEmptyTitle')"
        :description="t('admin.listStates.usersEmptyHint')"
      >
        <a-button type="primary" @click="openCreateModal">
          {{ t('admin.createUser') }}
        </a-button>
      </AppEmptyState>

      <a-table
        v-else
        :scroll="{ x: 'max-content' }"
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
                <ProtectedAvatar :size="40" :src="record.avatar_url">
                  {{ getUserInitial(record) }}
                </ProtectedAvatar>
              <div class="user-info">
                <span class="username">{{ getUserDisplayName(record) }}</span>
                <span class="email">{{ formatUserEmail(record.email) }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'username'">
            {{ record.username || '—' }}
          </template>
          <template v-else-if="column.key === 'auth_source'">
            <a-tag :color="record.auth_source === 'ldap' ? 'gold' : 'default'">
              {{ record.auth_source === 'ldap' ? t('admin.authSourceLdap') : t('admin.authSourceLocal') }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'role'">
            <a-tag :color="getRoleColor(record.role)">
              {{ t(`user.role.${record.role}`) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-badge :status="getStatusBadge(record.status)" :text="t(`admin.${record.status}`)" />
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTimeOrDash(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space size="small" wrap>
              <a-button type="link" size="small" @click="handleEdit(record)">
                {{ t('common.edit') }}
              </a-button>
              <a-button
                type="link"
                size="small"
                :disabled="record.auth_source === 'ldap'"
                :title="record.auth_source === 'ldap' ? t('admin.resetPasswordLdapDisabled') : undefined"
                @click="openResetPasswordModal(record)"
              >
                {{ t('admin.resetPassword') }}
              </a-button>
              <a-button type="link" size="small" danger @click="handleSoftDelete(record)">
                {{ t('admin.softDeleteUser') }}
              </a-button>
              <a-button type="link" size="small" danger @click="handleHardDelete(record)">
                {{ t('admin.hardDeleteUser') }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="showCreateModal"
      :title="t('admin.createUser')"
      :confirm-loading="createLoading"
      @ok="handleCreateUser"
      @cancel="resetCreateForm"
    >
      <a-form
        ref="createFormRef"
        :model="createForm"
        :rules="createFormRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 16 }"
      >
        <a-form-item :label="t('admin.username')" name="username">
          <a-input v-model:value="createForm.username" />
        </a-form-item>
        <a-form-item :label="t('auth.email')" name="email">
          <a-input v-model:value="createForm.email" :placeholder="t('admin.emailOptional')" />
        </a-form-item>
        <a-form-item :label="t('common.name')" name="display_name">
          <a-input v-model:value="createForm.display_name" />
        </a-form-item>
        <a-form-item :label="t('admin.authSource')" name="auth_source">
          <a-select v-model:value="createForm.auth_source">
            <a-select-option value="local">{{ t('admin.authSourceLocal') }}</a-select-option>
            <a-select-option value="ldap">{{ t('admin.authSourceLdap') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item
          v-if="createForm.auth_source === 'local'"
          :label="t('auth.password')"
          name="password"
        >
          <a-input-password v-model:value="createForm.password" />
        </a-form-item>
        <a-form-item :label="t('admin.role')" name="role">
          <a-select v-model:value="createForm.role">
            <a-select-option v-for="option in roleOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')" name="status">
          <a-select v-model:value="createForm.status">
            <a-select-option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="showEditModal"
      :title="t('admin.editUser')"
      :confirm-loading="saveLoading"
      @ok="handleSaveUser"
      @cancel="resetEditForm"
    >
      <a-form
        ref="formRef"
        :model="editForm"
        :rules="formRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 16 }"
      >
        <a-form-item :label="t('auth.email')" name="email">
          <a-input v-model:value="editForm.email" />
        </a-form-item>
        <a-form-item :label="t('admin.role')" name="role">
          <a-select v-model:value="editForm.role">
            <a-select-option v-for="option in roleOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')" name="status">
          <a-select v-model:value="editForm.status">
            <a-select-option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="showResetPasswordModal"
      :title="t('admin.resetPassword')"
      :confirm-loading="resetPasswordLoading"
      @ok="handleResetPassword"
      @cancel="resetResetPasswordForm"
    >
      <p v-if="resetPasswordUser" class="reset-password-hint">
        {{ t('admin.resetPasswordConfirmContent', { username: getUserDisplayName(resetPasswordUser) }) }}
      </p>
      <a-form
        ref="resetPasswordFormRef"
        :model="resetPasswordForm"
        :rules="resetPasswordRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 16 }"
      >
        <a-form-item :label="t('auth.newPassword')" name="new_password">
          <a-input-password v-model:value="resetPasswordForm.new_password" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import ProtectedAvatar from '@/components/common/ProtectedAvatar.vue'
import { message, Modal } from 'ant-design-vue'
import type { FormInstance } from 'ant-design-vue'
import AppFilterBar from '@/components/common/AppFilterBar.vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { formatDateTimeOrDash } from '@/domain/common/format'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'
import {
  adminCreateUser,
  adminDeleteUser,
  adminGetUsers,
  adminGetUserStats,
  adminResetUserPassword,
  adminUpdateUser
} from '@/api/users'
import type { AdminResetUserPasswordParams, AdminUserCreateParams } from '@/api/users'
import type { AdminUserStats, UserInfo } from '@/types/models'
import { formatUserEmail, getUserDisplayName } from '@/utils/user-display'
import { buildAdminUserCreatePayload } from '@/utils/admin-user-payload'

const { t } = useI18n()

const loading = ref(false)
const loadError = ref(false)
const loadErrorDetail = ref('')
const createLoading = ref(false)
const saveLoading = ref(false)
const resetPasswordLoading = ref(false)
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showResetPasswordModal = ref(false)
const createFormRef = ref<FormInstance>()
const formRef = ref<FormInstance>()
const resetPasswordFormRef = ref<FormInstance>()
const users = ref<UserInfo[]>([])
const stats = ref<AdminUserStats | null>(null)
const editingUser = ref<UserInfo | null>(null)
const resetPasswordUser = ref<UserInfo | null>(null)

const filters = reactive({
  keyword: '',
  role: undefined as string | undefined,
  status: undefined as string | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true
})

const createForm = reactive<AdminUserCreateParams>({
  username: '',
  email: '',
  display_name: '',
  password: '',
  role: 'user',
  status: 'active',
  auth_source: 'local'
})

const editForm = reactive({
  email: '',
  role: 'user',
  status: 'active'
})

const resetPasswordForm = reactive<AdminResetUserPasswordParams>({
  new_password: ''
})

const roleOptions = computed(() => ([
  { value: 'admin', label: t('user.role.admin') },
  { value: 'user', label: t('user.role.user') }
]))

const statusOptions = computed(() => ([
  { value: 'active', label: t('admin.active') },
  { value: 'disabled', label: t('admin.disabled') },
  { value: 'pending', label: t('admin.pending') }
]))

const createFormRules = computed(() => ({
  username: [
    { required: true, message: t('admin.usernameRequired') },
    { pattern: /^[A-Za-z0-9._-]{1,64}$/, message: t('admin.usernameFormat') }
  ],
  email: [
    { type: 'email', message: t('auth.validation.emailInvalid') }
  ],
  // LDAP 用户由目录服务校验口令，创建时不要求填写
  password: createForm.auth_source === 'local'
    ? [
        { required: true, message: t('auth.validation.passwordRequired') },
        { min: 12, message: t('auth.validation.passwordLength') }
      ]
    : [],
  role: [{ required: true, message: t('admin.selectRole') }],
  status: [{ required: true, message: t('admin.selectStatus') }]
}))

const formRules = computed(() => ({
  email: [
    { required: true, message: t('auth.validation.emailRequired') },
    { type: 'email', message: t('auth.validation.emailInvalid') }
  ],
  role: [{ required: true, message: t('admin.selectRole') }],
  status: [{ required: true, message: t('admin.selectStatus') }]
}))

const resetPasswordRules = computed(() => ({
  new_password: [
    { required: true, message: t('auth.validation.passwordRequired') },
    { min: 12, message: t('auth.validation.passwordLength') }
  ]
}))

const columns = computed(() => [
  { title: t('admin.userInfo'), key: 'user', width: 280 },
  { title: t('admin.username'), key: 'username', width: 140 },
  { title: t('admin.authSource'), key: 'auth_source', width: 120 },
  { title: t('admin.role'), key: 'role', width: 120 },
  { title: t('admin.status'), key: 'status', width: 120 },
  { title: t('admin.registerTime'), key: 'created_at', width: 180 },
  { title: t('common.actions'), key: 'actions', width: 260 }
])

const getUserInitial = (user: UserInfo) => {
  const displayName = getUserDisplayName(user)
  return displayName ? displayName.charAt(0).toUpperCase() : 'U'
}

const getRoleColor = (role: string) => {
  const colors: Record<string, string> = {
    admin: 'red',
    user: 'blue'
  }
  return colors[role] || 'default'
}

const getStatusBadge = (status: string) => {
  const badges: Record<string, 'success' | 'default' | 'error'> = {
    active: 'success',
    disabled: 'error',
    pending: 'default'
  }
  return badges[status] || 'default'
}


const fetchUsers = async () => {
  loading.value = true
  loadError.value = false
  loadErrorDetail.value = ''
  try {
    const res = await adminGetUsers({
      page: pagination.current,
      page_size: pagination.pageSize,
      keyword: filters.keyword || undefined,
      role: filters.role,
      status: filters.status
    })
    users.value = res.data.items
    pagination.total = res.data.total
  } catch (error) {
    users.value = []
    pagination.total = 0
    loadError.value = true
    loadErrorDetail.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const res = await adminGetUserStats()
    stats.value = res.data
  } catch {
    stats.value = null
  }
}

const refreshUsersPage = async () => {
  await Promise.allSettled([fetchUsers(), fetchStats()])
}

const resetCreateForm = () => {
  createForm.username = ''
  createForm.email = ''
  createForm.display_name = ''
  createForm.password = ''
  createForm.role = 'user'
  createForm.status = 'active'
  createForm.auth_source = 'local'
}

const resetEditForm = () => {
  editingUser.value = null
  editForm.email = ''
  editForm.role = 'user'
  editForm.status = 'active'
}

const resetResetPasswordForm = () => {
  resetPasswordUser.value = null
  resetPasswordForm.new_password = ''
}

const openCreateModal = () => {
  showCreateModal.value = true
}

const handleCreateUser = async () => {
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }

  const payload = buildAdminUserCreatePayload(createForm)
  createLoading.value = true
  try {
    await adminCreateUser(payload)
    message.success(t('admin.createUserSuccess'))
    showCreateModal.value = false
    resetCreateForm()
    await refreshUsersPage()
  } finally {
    createLoading.value = false
  }
}

const handleSearch = async () => {
  pagination.current = 1
  await fetchUsers()
}

const handleReset = async () => {
  filters.keyword = ''
  filters.role = undefined
  filters.status = undefined
  pagination.current = 1
  await fetchUsers()
}

const handleTableChange = async (pag: { current?: number; pageSize?: number }) => {
  pagination.current = pag.current || 1
  pagination.pageSize = pag.pageSize || 10
  await fetchUsers()
}

const handleEdit = (record: UserInfo) => {
  editingUser.value = record
  editForm.email = record.email || ''
  editForm.role = record.role
  editForm.status = record.status
  showEditModal.value = true
}

const handleSaveUser = async () => {
  if (!editingUser.value) return

  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saveLoading.value = true
  try {
    await adminUpdateUser(editingUser.value.id, {
      email: editForm.email,
      role: editForm.role,
      status: editForm.status
    })
    message.success(t('common.success'))
    showEditModal.value = false
    resetEditForm()
    await refreshUsersPage()
  } finally {
    saveLoading.value = false
  }
}

const openResetPasswordModal = (record: UserInfo) => {
  if (record.auth_source === 'ldap') {
    message.warning(t('admin.resetPasswordLdapDisabled'))
    return
  }
  resetPasswordUser.value = record
  resetPasswordForm.new_password = ''
  showResetPasswordModal.value = true
}

const handleResetPassword = async () => {
  if (!resetPasswordUser.value) return
  if (resetPasswordUser.value.auth_source === 'ldap') {
    message.warning(t('admin.resetPasswordLdapDisabled'))
    return
  }

  try {
    await resetPasswordFormRef.value?.validate()
  } catch {
    return
  }

  resetPasswordLoading.value = true
  try {
    await adminResetUserPassword(resetPasswordUser.value.id, { ...resetPasswordForm })
    message.success(t('admin.resetPasswordSuccess'))
    showResetPasswordModal.value = false
    resetResetPasswordForm()
  } finally {
    resetPasswordLoading.value = false
  }
}

const handleSoftDelete = (record: UserInfo) => {
  Modal.confirm({
    title: t('admin.softDeleteUserConfirm'),
    content: t('admin.softDeleteUserConfirmContent', { username: getUserDisplayName(record) }),
    okType: 'danger',
    onOk: async () => {
      await adminDeleteUser(record.id)
      message.success(t('admin.softDeleteUserSuccess'))
      await refreshUsersPage()
    }
  })
}

const handleHardDelete = (record: UserInfo) => {
  Modal.confirm({
    title: t('admin.hardDeleteUserConfirm'),
    content: t('admin.hardDeleteUserConfirmContent', { username: getUserDisplayName(record) }),
    okType: 'danger',
    onOk: async () => {
      await adminDeleteUser(record.id, true)
      message.success(t('admin.hardDeleteUserSuccess'))
      await refreshUsersPage()
    }
  })
}

onMounted(async () => {
  await refreshUsersPage()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-users {
  .stats-row {
    margin-bottom: @spacing-lg;
  }

  .stat-card {
    text-align: center;
  }

  .reset-password-hint {
    margin-bottom: @spacing-md;
    color: @text-color-light-secondary;
  }

  .user-cell {
    display: flex;
    align-items: center;
    gap: @spacing-sm;

    .user-info {
      display: flex;
      flex-direction: column;
    }

    .username {
      font-weight: @font-weight-medium;
    }

    .email {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }
  }
}
</style>
