<template>
  <div class="admin-workbench-groups">
    <AppPageHeader
      :title="t('admin.workbenchGroups')"
      :subtitle="t('admin.workbenchGroupsSubtitle')"
    />

    <div class="page-grid">
      <a-card class="group-form">
        <template #title>{{ t('admin.workbenchGroups') }}</template>
        <a-form layout="vertical">
          <a-form-item :label="t('admin.categoryName')">
            <a-input v-model:value="groupForm.name" />
          </a-form-item>
          <a-form-item :label="t('admin.categorySlug')">
            <a-input v-model:value="groupForm.slug" />
          </a-form-item>
          <a-form-item :label="t('common.description')">
            <a-textarea v-model:value="groupForm.description" :rows="3" />
          </a-form-item>
          <a-form-item :label="t('common.sort')">
            <a-input-number v-model:value="groupForm.sort_order" :min="1" style="width: 100%" />
          </a-form-item>
          <a-form-item>
            <a-space>
              <a-switch v-model:checked="groupForm.is_enabled" />
              <span>{{ t('admin.active') }}</span>
            </a-space>
          </a-form-item>
          <a-space>
            <a-button type="primary" :loading="savingGroup" @click="submitGroup">
              {{ editingGroupId ? t('common.save') : t('common.create') }}
            </a-button>
            <a-button v-if="editingGroupId" @click="resetGroupForm">
              {{ t('common.cancel') }}
            </a-button>
          </a-space>
        </a-form>

        <a-divider />

        <a-list :data-source="groups" :loading="loading">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-space direction="vertical" size="small">
                <strong>{{ item.name }}</strong>
                <span>{{ item.slug }}</span>
                <a-space>
                  <a-tag>{{ `#${item.sort_order}` }}</a-tag>
                  <a-tag :color="item.is_enabled ? 'green' : 'default'">
                    {{ item.is_enabled ? t('admin.active') : t('admin.disabled') }}
                  </a-tag>
                </a-space>
              </a-space>
              <template #actions>
                <a-button size="small" @click="editGroup(item)">
                  {{ t('common.edit') }}
                </a-button>
                <a-popconfirm
                  :title="t('admin.deleteCategoryConfirm')"
                  :description="t('admin.deleteCategoryConfirmContent', { name: item.name })"
                  @confirm="deleteGroup(item.id)"
                >
                  <a-button size="small" danger>
                    {{ t('common.delete') }}
                  </a-button>
                </a-popconfirm>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-card>

      <a-card class="mapping-form">
        <template #title>{{ t('workflow.columns.groups') }}</template>
        <a-form layout="vertical">
          <a-form-item :label="t('admin.tools')">
            <a-select
              v-model:value="mappingForm.tool_id"
              show-search
              :filter-option="false"
              :loading="toolOptionsLoading"
              @search="searchToolOptions"
            >
              <a-select-option v-for="tool in tools" :key="tool.id" :value="tool.id">
                {{ tool.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item :label="t('admin.workbenchGroups')">
            <a-select v-model:value="mappingForm.group_id">
              <a-select-option v-for="group in groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item :label="t('common.sort')">
            <a-input-number v-model:value="mappingForm.sort_order" :min="1" style="width: 100%" />
          </a-form-item>
          <a-form-item>
            <a-space>
              <a-switch v-model:checked="mappingForm.is_recommended" />
              <span>{{ t('workflow.toolStatus.recommended') }}</span>
            </a-space>
          </a-form-item>
          <a-form-item>
            <a-space>
              <a-switch v-model:checked="mappingForm.is_enabled" />
              <span>{{ t('admin.active') }}</span>
            </a-space>
          </a-form-item>
          <a-space>
            <a-button type="primary" :loading="savingMapping" @click="submitMapping">
              {{ editingMappingId ? t('common.save') : t('common.create') }}
            </a-button>
            <a-button v-if="editingMappingId" @click="resetMappingForm">
              {{ t('common.cancel') }}
            </a-button>
          </a-space>
        </a-form>

        <a-divider />

        <a-list :data-source="mappings" :loading="loading">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-space direction="vertical" size="small">
                <strong>{{ resolveToolName(item.tool_id) }}</strong>
                <span>{{ resolveGroupName(item.group_id) }}</span>
                <a-space>
                  <a-tag>{{ `#${item.sort_order}` }}</a-tag>
                  <a-tag v-if="item.is_recommended" color="gold">
                    {{ t('workflow.toolStatus.recommended') }}
                  </a-tag>
                  <a-tag :color="item.is_enabled ? 'green' : 'default'">
                    {{ item.is_enabled ? t('admin.active') : t('admin.disabled') }}
                  </a-tag>
                </a-space>
              </a-space>
              <template #actions>
                <a-button size="small" @click="editMapping(item)">
                  {{ t('common.edit') }}
                </a-button>
                <a-button size="small" danger @click="deleteMapping(item.id)">
                  {{ t('common.delete') }}
                </a-button>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, reactive, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import { useRemoteToolOptions } from '@/composables/useRemoteToolOptions'
  import type { WorkbenchGroup, WorkbenchGroupMapping } from '@/types/models'
  import {
    adminCreateWorkbenchGroup,
    adminCreateWorkbenchGroupMapping,
    adminDeleteWorkbenchGroup,
    adminDeleteWorkbenchGroupMapping,
    adminGetWorkbenchGroupMappings,
    adminGetWorkbenchGroups,
    adminUpdateWorkbenchGroup,
    adminUpdateWorkbenchGroupMapping
  } from '@/api/tools'

  const { t } = useI18n()
  const loading = ref(false)
  const savingGroup = ref(false)
  const savingMapping = ref(false)
  const editingGroupId = ref<string | null>(null)
  const editingMappingId = ref<string | null>(null)
  const groups = ref<WorkbenchGroup[]>([])
  const mappings = ref<WorkbenchGroupMapping[]>([])
  const {
    fetchToolOptions,
    searchToolOptions,
    toolOptions: tools,
    toolOptionsLoading
  } = useRemoteToolOptions()

  const groupForm = reactive({
    name: '',
    slug: '',
    description: '',
    sort_order: undefined as number | undefined,
    is_enabled: true
  })

  const mappingForm = reactive({
    tool_id: undefined as string | undefined,
    group_id: undefined as string | undefined,
    sort_order: undefined as number | undefined,
    is_recommended: false,
    is_enabled: true
  })

  const normalizeSlug = (value: string) => {
    return value
      .trim()
      .toLowerCase()
      .replace(/[\s_]+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
  }

  const fetchData = async () => {
    loading.value = true
    try {
      const [groupsRes, mappingsRes] = await Promise.all([
        adminGetWorkbenchGroups(),
        adminGetWorkbenchGroupMappings(),
        fetchToolOptions()
      ])
      groups.value = groupsRes.data
      mappings.value = mappingsRes.data
    } catch {
      groups.value = []
      mappings.value = []
      tools.value = []
    } finally {
      loading.value = false
    }
  }

  const resetGroupForm = () => {
    editingGroupId.value = null
    groupForm.name = ''
    groupForm.slug = ''
    groupForm.description = ''
    groupForm.sort_order = undefined
    groupForm.is_enabled = true
  }

  const resetMappingForm = () => {
    editingMappingId.value = null
    mappingForm.tool_id = undefined
    mappingForm.group_id = undefined
    mappingForm.sort_order = undefined
    mappingForm.is_recommended = false
    mappingForm.is_enabled = true
  }

  const submitGroup = async () => {
    const trimmedName = groupForm.name.trim()
    const rawSlug = groupForm.slug.trim()

    if (!trimmedName) {
      message.warning(t('admin.enterCategoryName'))
      return
    }

    const slug = normalizeSlug(rawSlug || trimmedName)
    if (!slug) {
      message.warning(rawSlug ? t('admin.invalidCategorySlug') : t('admin.enterCategorySlug'))
      return
    }

    groupForm.name = trimmedName
    groupForm.slug = slug

    savingGroup.value = true
    try {
      const payload = {
        name: groupForm.name,
        slug,
        description: groupForm.description || undefined,
        sort_order: groupForm.sort_order,
        is_enabled: groupForm.is_enabled
      }

      if (editingGroupId.value) {
        await adminUpdateWorkbenchGroup(editingGroupId.value, payload)
      } else {
        await adminCreateWorkbenchGroup(payload)
      }

      resetGroupForm()
      await fetchData()
      message.success(t('common.success'))
    } finally {
      savingGroup.value = false
    }
  }

  const deleteGroup = async (id: string) => {
    await adminDeleteWorkbenchGroup(id)
    if (editingGroupId.value === id) {
      resetGroupForm()
    }
    await fetchData()
    message.success(t('common.success'))
  }

  const submitMapping = async () => {
    if (!mappingForm.tool_id || !mappingForm.group_id) {
      return
    }

    savingMapping.value = true
    try {
      const payload = {
        tool_id: mappingForm.tool_id,
        group_id: mappingForm.group_id,
        sort_order: mappingForm.sort_order,
        is_recommended: mappingForm.is_recommended,
        is_enabled: mappingForm.is_enabled
      }

      if (editingMappingId.value) {
        await adminUpdateWorkbenchGroupMapping(editingMappingId.value, payload)
      } else {
        await adminCreateWorkbenchGroupMapping(payload)
      }

      resetMappingForm()
      await fetchData()
      message.success(t('common.success'))
    } finally {
      savingMapping.value = false
    }
  }

  const deleteMapping = async (id: string) => {
    await adminDeleteWorkbenchGroupMapping(id)
    await fetchData()
    message.success(t('common.success'))
  }

  const editGroup = (group: WorkbenchGroup) => {
    editingGroupId.value = group.id
    groupForm.name = group.name
    groupForm.slug = group.slug
    groupForm.description = group.description || ''
    groupForm.sort_order = group.sort_order
    groupForm.is_enabled = group.is_enabled !== false
  }

  const editMapping = (mapping: WorkbenchGroupMapping) => {
    editingMappingId.value = mapping.id
    mappingForm.tool_id = mapping.tool_id
    mappingForm.group_id = mapping.group_id
    mappingForm.sort_order = mapping.sort_order
    mappingForm.is_recommended = mapping.is_recommended
    mappingForm.is_enabled = mapping.is_enabled
  }

  const resolveToolName = (toolId: string) => {
    return tools.value.find(tool => tool.id === toolId)?.name ?? toolId
  }

  const resolveGroupName = (groupId: string) => {
    return groups.value.find(group => group.id === groupId)?.name ?? groupId
  }

  onMounted(async () => {
    await fetchData()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .page-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-lg;

    @media (max-width: @screen-lg) {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
