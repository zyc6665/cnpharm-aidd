<template>
  <div class="tool-detail-page">
    <div class="container">
      <a-spin :spinning="loading">
        <div v-if="tool" class="tool-detail">
          <!-- 左侧：工具信息 + 参数表单 -->
          <div class="tool-main">
            <!-- 工具信息卡片 -->
            <div class="tool-info card">
              <div class="tool-header">
                <div class="tool-icon">
                  <span v-if="tool.icon">{{ tool.icon }}</span>
                  <ToolOutlined v-else />
                </div>
                <div class="tool-meta">
                  <h1 class="tool-name">{{ tool.name }}</h1>
                  <div class="tool-tags">
                    <a-tag v-if="tool.category" color="gold">{{ tool.category }}</a-tag>
                    <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
                      {{ tag.name }}
                    </a-tag>
                  </div>
                </div>
                <div class="tool-actions">
                  <a-button
                    :type="tool.is_favorited ? 'primary' : 'default'"
                    :loading="favoriteLoading"
                    @click="handleFavorite"
                  >
                    <HeartFilled v-if="tool.is_favorited" />
                    <HeartOutlined v-else />
                    {{ tool.is_favorited ? t('tools.unfavorite') : t('tools.favorite') }}
                  </a-button>
                  <a-tag v-if="tool.current_version" color="blue">
                    v{{ tool.current_version.version }}
                  </a-tag>
                </div>
              </div>

              <p class="tool-description">{{ tool.description }}</p>

              <div class="tool-stats">
                <span class="stat-item">
                  <PlayCircleOutlined />
                  {{ t('tools.usageCount') }}: {{ formatNumber(tool.statistics?.usage_count) }}
                </span>
                <span class="stat-item">
                  <EyeOutlined />
                  {{ t('tools.viewCount') }}: {{ formatNumber(tool.statistics?.view_count) }}
                </span>
                <span class="stat-item">
                  <HeartOutlined />
                  {{ t('tools.favoriteCount') }}: {{ formatNumber(tool.statistics?.favorite_count) }}
                </span>
                <span v-if="tool.current_version" class="stat-item">
                  <TagOutlined />
                  {{ t('tools.version') }}: v{{ tool.current_version.version }}
                </span>
              </div>

              <!-- 版本更新日志 -->
              <div v-if="tool.current_version?.changelog" class="tool-changelog">
                <h3>{{ t('tools.changelog') }}</h3>
                <p>{{ tool.current_version.changelog }}</p>
              </div>
            </div>

            <!-- 参数表单 -->
            <div class="tool-form card">
              <h2 class="section-title">{{ t('tools.parameters') }}</h2>

              <!-- 游客警告 -->
              <a-alert
                v-if="userStore.isGuest"
                type="warning"
                show-icon
                style="margin-bottom: 16px"
              >
                <template #message>
                  {{ t('tools.guestWarning') }}
                </template>
              </a-alert>

              <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
                <template v-for="(prop, key) in flattenedSchema?.properties" :key="key">
                  <a-form-item
                    :name="key"
                    :label="prop.title"
                    :rules="getFieldRules(key, prop)"
                    :extra="prop.description"
                  >
                    <!-- 文本输入 -->
                    <a-input
                      v-if="prop.type === 'string' && !prop.format && !prop.enum"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                    />
                    <!-- 文本域 -->
                    <a-textarea
                      v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta' || prop.format === 'pdb')"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                      :rows="prop.format === 'fasta' || prop.format === 'pdb' ? 8 : 4"
                      :class="{ 'code-input': prop.format === 'fasta' || prop.format === 'pdb' }"
                    />
                    <!-- 数字输入 -->
                    <a-input-number
                      v-else-if="prop.type === 'number'"
                      v-model:value="formState[key]"
                      :min="prop.minimum"
                      :max="prop.maximum"
                      style="width: 100%"
                    />
                    <!-- 布尔选择 -->
                    <a-switch
                      v-else-if="prop.type === 'boolean'"
                      v-model:checked="formState[key]"
                    />
                    <!-- 下拉选择 -->
                    <a-select
                      v-else-if="prop.type === 'select' || (prop.enum && prop.type !== 'array')"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                    >
                      <a-select-option v-for="opt in prop.enum" :key="opt" :value="opt">
                        {{ opt }}
                      </a-select-option>
                    </a-select>
                    <!-- 数组多选（enum） -->
                    <a-select
                      v-else-if="prop.type === 'array' && prop.items?.enum"
                      v-model:value="formState[key]"
                      mode="multiple"
                      :placeholder="prop.description"
                    >
                      <a-select-option v-for="opt in prop.items.enum" :key="opt" :value="opt">
                        {{ opt }}
                      </a-select-option>
                    </a-select>
                    <!-- 文件上传 -->
                    <a-upload
                      v-else-if="prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'"
                      v-model:file-list="fileList[key]"
                      :accept="prop.accept"
                      :before-upload="() => false"
                      :max-count="1"
                    >
                      <a-button>
                        <UploadOutlined />
                        {{ t('tools.selectFile') }}
                      </a-button>
                      <template #itemRender="{ file }">
                        <span class="file-item">
                          <FileOutlined />
                          {{ file.name }}
                        </span>
                      </template>
                    </a-upload>
                  </a-form-item>
                </template>

                <a-form-item>
                  <a-space>
                    <a-button
                      type="primary"
                      html-type="submit"
                      size="large"
                      :loading="submitting"
                      :disabled="!canSubmit"
                    >
                      <ThunderboltOutlined />
                      {{ t('tools.runTool') }}
                    </a-button>
                    <a-button size="large" @click="resetForm">
                      {{ t('common.reset') }}
                    </a-button>
                  </a-space>
                </a-form-item>
              </a-form>
            </div>
          </div>

          <!-- 右侧：工具信息 -->
          <div class="tool-sidebar">
            <!-- 工具标签 -->
            <div v-if="tool.tags?.length" class="tags-info card">
              <h3 class="sidebar-title">
                <TagOutlined />
                {{ t('tools.tags') }}
              </h3>
              <div class="tags-list">
                <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
                  {{ tag.name }}
                </a-tag>
              </div>
            </div>

            <!-- 工具状态 -->
            <div class="status-info card">
              <h3 class="sidebar-title">
                <InfoCircleOutlined />
                {{ t('tools.toolInfo') }}
              </h3>
              <div class="info-list">
                <div class="info-item">
                  <span class="info-label">{{ t('tools.status') }}:</span>
                  <a-tag :color="getStatusColor(tool.status)">{{ tool.status }}</a-tag>
                </div>
                <div class="info-item">
                  <span class="info-label">{{ t('common.createdAt') }}:</span>
                  <span>{{ formatDate(tool.created_at) }}</span>
                </div>
                <div v-if="tool.updated_at" class="info-item">
                  <span class="info-label">{{ t('common.updatedAt') }}:</span>
                  <span>{{ formatDate(tool.updated_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <a-empty v-else :description="t('common.noData')" />
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import {
    ToolOutlined,
    HeartOutlined,
    HeartFilled,
    PlayCircleOutlined,
    EyeOutlined,
    TagOutlined,
    UploadOutlined,
    ThunderboltOutlined,
    FileOutlined,
    InfoCircleOutlined
  } from '@ant-design/icons-vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type { SchemaProperty, ToolSchema } from '@/types/models'
  import { uploadFile } from '@/api/files'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const tasksStore = useTasksStore()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)
  const favoriteLoading = ref(false)
  const tool = computed(() => toolsStore.currentTool)
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})

  // 从 current_version.config 中获取 input_schema
  const inputSchema = computed<ToolSchema | undefined>(() => {
    const config = tool.value?.current_version?.config
    if (config && typeof config === 'object' && 'input_schema' in config) {
      return config.input_schema as ToolSchema
    }
    return undefined
  })

  // 扁平化嵌套的schema结构，支持params和input_files
  const flattenedSchema = computed<ToolSchema | undefined>(() => {
    if (!inputSchema.value?.properties) return undefined

    const flattened: Record<string, SchemaProperty> = {}
    const required: string[] = []

    for (const [key, prop] of Object.entries(inputSchema.value.properties)) {
      // 如果是嵌套对象（params、input_files等），展开其子属性
      if (prop.type === 'object' && prop.properties) {
        for (const [subKey, subProp] of Object.entries(prop.properties)) {
          const flatKey = `${key}.${subKey}`
          flattened[flatKey] = {
            ...subProp,
            _parentKey: key,
            _originalKey: subKey
          }
          // 检查是否必填
          if (prop.required?.includes(subKey)) {
            required.push(flatKey)
          }
        }
      } else {
        // 非嵌套属性直接添加
        flattened[key] = prop
        if (inputSchema.value.required?.includes(key)) {
          required.push(key)
        }
      }
    }

    return {
      type: 'object',
      properties: flattened,
      required
    }
  })

  const canSubmit = computed(() => {
    if (!userStore.isAuthenticated) return false
    if (userStore.isGuest) return false
    return true
  })

  const formatNumber = (num?: number | null) => {
    // 处理 undefined/null 的情况
    if (num == null || num === undefined) {
      return '0'
    }
    if (num >= 10000) {
      return (num / 10000).toFixed(1) + 'w'
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString()
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      draft: 'default',
      published: 'success',
      disabled: 'warning',
      deprecated: 'error'
    }
    return colors[status] || 'default'
  }

  const getFieldRules = (key: string, prop: SchemaProperty): Rule[] => {
    const rules: Rule[] = []
    const schema = flattenedSchema.value
    if (schema?.required?.includes(key)) {
      rules.push({ required: true, message: `${prop.title} ${t('common.required')}` })
    }
    if (prop.minLength) {
      rules.push({ min: prop.minLength, message: t('validation.minLength', { min: prop.minLength }) })
    }
    if (prop.maxLength) {
      rules.push({ max: prop.maxLength, message: t('validation.maxLength', { max: prop.maxLength }) })
    }
    return rules
  }

  const handleFavorite = async () => {
    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }
    favoriteLoading.value = true
    try {
      await toolsStore.toggleFavorite(tool.value!.id)
    } finally {
      favoriteLoading.value = false
    }
  }

  const resetForm = () => {
    formRef.value?.resetFields()
    Object.keys(fileList).forEach(key => {
      fileList[key] = []
    })
  }

  const handleSubmit = async () => {
    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }

    if (userStore.isGuest) {
      message.warning(t('auth.guestCannotSubmit'))
      return
    }

    submitting.value = true
    try {
      // 处理文件上传
      const fileIds: string[] = []
      const organizedData: Record<string, any> = {}

      for (const [key, value] of Object.entries(formState)) {
        // 检查是否是文件字段
        if (fileList[key] && fileList[key].length > 0) {
          const fileItem = fileList[key][0]
          if (fileItem && fileItem.originFileObj) {
            const res = await uploadFile(fileItem.originFileObj as File)
            fileIds.push(res.data.id.toString())

            // 将文件URL存储到对应的字段
            const prop = flattenedSchema.value?.properties?.[key]
            if (prop?._parentKey && prop?._originalKey) {
              if (!organizedData[prop._parentKey]) {
                organizedData[prop._parentKey] = {}
              }
              organizedData[prop._parentKey][prop._originalKey] = `/api/v1/files/${res.data.id}/download`
            } else {
              organizedData[key] = `/api/v1/files/${res.data.id}/download`
            }
          }
        } else if (value !== undefined && value !== null && value !== '') {
          // 处理普通字段，重新组织成嵌套结构
          const prop = flattenedSchema.value?.properties?.[key]
          if (prop?._parentKey && prop?._originalKey) {
            if (!organizedData[prop._parentKey]) {
              organizedData[prop._parentKey] = {}
            }
            organizedData[prop._parentKey][prop._originalKey] = value
          } else {
            organizedData[key] = value
          }
        }
      }

      // 创建任务
      const task = await tasksStore.createTask({
        tool_id: tool.value!.id,
        params: organizedData,
        file_ids: fileIds.length > 0 ? fileIds : undefined
      })

      message.success(t('tasks.created'))
      router.push(`/tasks/${task.id}`)
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  onMounted(async () => {
    const id = route.params.id as string
    if (id) {
      loading.value = true
      try {
        await toolsStore.fetchToolDetail(id)

        // 初始化表单默认值
        if (flattenedSchema.value?.properties) {
          for (const [key, prop] of Object.entries(flattenedSchema.value.properties)) {
            if (prop.default !== undefined) {
              formState[key] = prop.default
            }
            // 初始化文件列表
            if (prop.type === 'file') {
              fileList[key] = []
            }
          }
        }
      } finally {
        loading.value = false
      }
    }
  })

  onBeforeUnmount(() => {
    toolsStore.clearCurrentTool()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-detail-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .tool-detail {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: @spacing-xl;

    @media (max-width: @screen-lg) {
      grid-template-columns: 1fr;
    }
  }

  .card {
    background: @bg-light;
    border-radius: @border-radius-lg;
    padding: @spacing-lg;
    box-shadow: @shadow-sm;
  }

  .tool-main {
    display: flex;
    flex-direction: column;
    gap: @spacing-xl;
  }

  .tool-info {
    .tool-header {
      display: flex;
      gap: @spacing-md;
      margin-bottom: @spacing-lg;
      flex-wrap: wrap;
    }

    .tool-icon {
      width: 64px;
      height: 64px;
      border-radius: @border-radius-lg;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      color: @accent-color;
      flex-shrink: 0;
    }

    .tool-meta {
      flex: 1;
      min-width: 200px;
    }

    .tool-name {
      font-size: @font-size-xxl;
      font-weight: @font-weight-bold;
      margin-bottom: @spacing-sm;
    }

    .tool-tags {
      display: flex;
      gap: @spacing-xs;
      flex-wrap: wrap;
    }

    .tool-actions {
      display: flex;
      gap: @spacing-sm;
      flex-shrink: 0;
      align-items: flex-start;
    }

    .tool-description {
      color: @text-color-light-secondary;
      font-size: @font-size-md;
      margin-bottom: @spacing-lg;
      line-height: @line-height-loose;
    }

    .tool-stats {
      display: flex;
      gap: @spacing-lg;
      flex-wrap: wrap;
      margin-bottom: @spacing-lg;
    }

    .stat-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
      color: @text-color-light-tertiary;
    }

    .tool-changelog {
      margin-top: @spacing-lg;
      padding-top: @spacing-lg;
      border-top: 1px solid @border-color-light;

      h3 {
        font-size: @font-size-md;
        font-weight: @font-weight-semibold;
        margin-bottom: @spacing-sm;
      }

      p {
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }
  }

  .tool-form {
    .section-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-lg;
    }

    .code-input {
      font-family: monospace;
    }

    .file-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
    }
  }

  // 右侧栏
  .tool-sidebar {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;

    @media (max-width: @screen-lg) {
      order: -1;
    }
  }

  .sidebar-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-md;
    display: flex;
    align-items: center;
    gap: @spacing-xs;
  }

  .tags-info {
    .tags-list {
      display: flex;
      flex-wrap: wrap;
      gap: @spacing-xs;
    }
  }

  .status-info {
    .info-list {
      display: flex;
      flex-direction: column;
      gap: @spacing-sm;
    }

    .info-item {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      font-size: @font-size-sm;
    }

    .info-label {
      color: @text-color-light-tertiary;
      min-width: 70px;
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
