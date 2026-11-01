<template>
  <main class="project-settings-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">返回项目总览</router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader
      title="项目设置"
      :subtitle="project ? `${project.name} · 成员与权限` : '成员与权限'"
    >
      <template #actions>
        <a-button :loading="loading" @click="load">刷新</a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="settings-alert"
      type="error"
      show-icon
      message="项目设置加载失败"
    >
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>

    <a-skeleton v-if="loading && !project" active :paragraph="{ rows: 8 }" />
    <template v-else-if="project">
      <section class="settings-section">
        <div class="section-heading">
          <div>
            <h2>项目成员</h2>
            <span>owner 可管理成员；editor 可编辑项目；runner 可运行任务；viewer 只读。</span>
          </div>
        </div>

        <div v-if="canManageMembers" class="member-form">
          <a-input
            v-model:value="newMember.username"
            placeholder="成员用户名"
            @pressEnter="handleAddMember"
          />
          <a-select v-model:value="newMember.role" class="role-select">
            <a-select-option value="editor">编辑者</a-select-option>
            <a-select-option value="runner">运行者</a-select-option>
            <a-select-option value="viewer">只读</a-select-option>
          </a-select>
          <a-button type="primary" :loading="saving" @click="handleAddMember">
            添加成员
          </a-button>
        </div>

        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="memberColumns"
          :data-source="members"
          :loading="membersLoading"
          :pagination="false"
          row-key="id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'member'">
              <div class="member-cell">
                <strong>{{ record.display_name || record.username || record.email || '—' }}</strong>
                <span>{{ record.email || '—' }}</span>
              </div>
            </template>
            <template v-else-if="column.key === 'role'">
              <a-select
                v-if="canManageMembers && record.role !== 'owner'"
                :value="record.role"
                class="role-select"
                @change="handleRoleChange(record, $event)"
              >
                <a-select-option value="editor">编辑者</a-select-option>
                <a-select-option value="runner">运行者</a-select-option>
                <a-select-option value="viewer">只读</a-select-option>
              </a-select>
              <a-tag v-else :color="roleColor(record.role)">{{ roleLabel(record.role) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-popconfirm
                v-if="canManageMembers && record.role !== 'owner'"
                title="确认移除该成员？"
                ok-text="移除"
                cancel-text="取消"
                ok-type="danger"
                @confirm="handleRemoveMember(record)"
              >
                <a-button type="link" danger size="small">移除</a-button>
              </a-popconfirm>
              <span v-else class="muted">-</span>
            </template>
          </template>
        </a-table>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import {
    addProjectMember,
    getProjectOverview,
    listProjectMembers,
    removeProjectMember,
    updateProjectMember
  } from '@/api/projects'
  import type { ProjectMember, ProjectRole, ResearchProject } from '@/types/projects'

  const route = useRoute()
  const projectId = computed(() => String(route.params.projectId || ''))
  const project = ref<ResearchProject | null>(null)
  const members = ref<ProjectMember[]>([])
  const loading = ref(false)
  const membersLoading = ref(false)
  const saving = ref(false)
  const loadError = ref(false)
  const newMember = reactive<{ username: string; role: Exclude<ProjectRole, 'owner'> }>({
    username: '',
    role: 'viewer'
  })

  const canManageMembers = computed(() =>
    ['owner', 'admin'].includes(project.value?.role ?? '')
  )
  const memberColumns = [
    { title: '成员', key: 'member' },
    { title: '角色', key: 'role', width: 180 },
    { title: '操作', key: 'actions', width: 120 }
  ]

  async function load() {
    if (!projectId.value) return
    loading.value = true
    membersLoading.value = true
    loadError.value = false
    try {
      const [overviewResult, memberResult] = await Promise.all([
        getProjectOverview(projectId.value),
        listProjectMembers(projectId.value)
      ])
      project.value = overviewResult.data.project
      members.value = memberResult.data.items
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
      membersLoading.value = false
    }
  }

  async function handleAddMember() {
    const username = newMember.username.trim()
    if (!username || !canManageMembers.value) return
    saving.value = true
    try {
      // 优先传账号名；后端兼容按 email 匹配的逻辑
      const response = await addProjectMember(projectId.value, { username, role: newMember.role })
      members.value = [...members.value, response.data]
      newMember.username = ''
      newMember.role = 'viewer'
      message.success('项目成员已添加')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '项目成员添加失败')
    } finally {
      saving.value = false
    }
  }

  async function handleUpdateMemberRole(member: ProjectMember, role: ProjectRole) {
    if (role === 'owner' || !canManageMembers.value) return
    try {
      const response = await updateProjectMember(projectId.value, member.id, { role })
      members.value = members.value.map(item => item.id === member.id ? response.data : item)
      message.success('项目成员已更新')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '项目成员更新失败')
    }
  }

  function handleRoleChange(member: ProjectMember, value: unknown) {
    if (typeof value !== 'string') return
    void handleUpdateMemberRole(member, value as ProjectRole)
  }

  async function handleRemoveMember(member: ProjectMember) {
    if (!canManageMembers.value) return
    try {
      await removeProjectMember(projectId.value, member.id)
      members.value = members.value.filter(item => item.id !== member.id)
      message.success('项目成员已移除')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '项目成员移除失败')
    }
  }

  function roleLabel(role: ProjectRole): string {
    return ({ owner: '所有者', editor: '编辑者', runner: '运行者', viewer: '只读' })[role]
  }

  function roleColor(role: ProjectRole): string {
    return ({ owner: 'purple', editor: 'blue', runner: 'green', viewer: 'default' })[role]
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-settings-page {
    max-width: 980px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .settings-alert,
  .settings-section {
    margin-bottom: @spacing-lg;
  }

  .settings-section {
    display: grid;
    gap: @spacing-md;
  }

  .section-heading h2 {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-lg;
  }

  .section-heading span,
  .member-cell span,
  .muted {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .member-form {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) 160px auto;
    gap: @spacing-sm;
    align-items: center;
  }

  .member-cell strong,
  .member-cell span {
    display: block;
  }

  .role-select {
    width: 160px;
  }

  @media (max-width: @screen-sm) {
    .member-form {
      grid-template-columns: 1fr;
    }
  }
</style>
