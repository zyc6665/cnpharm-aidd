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
                    <a-tag v-if="tool.category" color="gold">{{ tool.category.name }}</a-tag>
                    <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
                      {{ tag.name }}
                    </a-tag>
                    <a-tag v-if="tool.is_free" color="green">{{ t('tools.free') }}</a-tag>
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
                  <a-dropdown v-if="tool.versions?.length">
                    <a-button>
                      v{{ tool.version }}
                      <DownOutlined />
                    </a-button>
                    <template #overlay>
                      <a-menu @click="handleVersionChange">
                        <a-menu-item v-for="ver in tool.versions" :key="ver">
                          v{{ ver }}
                        </a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </div>
              </div>

              <p class="tool-description">{{ tool.description }}</p>

              <!-- 工具详细介绍 -->
              <div v-if="tool.introduction" class="tool-introduction">
                <h3>{{ t('tools.introduction') }}</h3>
                <p>{{ tool.introduction }}</p>
              </div>

              <!-- 功能特点 -->
              <div v-if="tool.features?.length" class="tool-features">
                <h3>{{ t('tools.features') }}</h3>
                <ul>
                  <li v-for="(feature, idx) in tool.features" :key="idx">
                    <CheckCircleOutlined class="feature-icon" />
                    {{ feature }}
                  </li>
                </ul>
              </div>

              <!-- 使用步骤 -->
              <div v-if="tool.steps?.length" class="tool-steps">
                <h3>{{ t('tools.howToUse') }}</h3>
                <a-steps direction="vertical" size="small">
                  <a-step v-for="(step, idx) in tool.steps" :key="idx" :title="`${t('tools.step')} ${idx + 1}`" :description="step" />
                </a-steps>
              </div>

              <div class="tool-stats">
                <span class="stat-item">
                  <PlayCircleOutlined />
                  {{ t('tools.runCount') }}: {{ formatNumber(tool.run_count) }}
                </span>
                <span class="stat-item">
                  <HeartOutlined />
                  {{ t('tools.favoriteCount') }}: {{ formatNumber(tool.favorite_count) }}
                </span>
                <span class="stat-item">
                  <TagOutlined />
                  {{ t('tools.version') }}: v{{ tool.version }}
                </span>
                <span v-if="tool.avg_duration" class="stat-item">
                  <ClockCircleOutlined />
                  {{ t('tools.avgDuration') }}: {{ formatDuration(tool.avg_duration) }}
                </span>
              </div>

              <!-- 参考文献 -->
              <div v-if="tool.references?.length" class="tool-references">
                <h3>{{ t('tools.references') }}</h3>
                <ul>
                  <li v-for="(ref, idx) in tool.references" :key="idx">
                    <a :href="ref.url" target="_blank" rel="noopener">
                      {{ ref.title }}
                      <span v-if="ref.authors" class="ref-authors"> - {{ ref.authors }}</span>
                      <span v-if="ref.year" class="ref-year">({{ ref.year }})</span>
                    </a>
                  </li>
                </ul>
              </div>

              <!-- 外部链接 -->
              <div class="tool-links">
                <a v-if="tool.github_url" :href="tool.github_url" target="_blank" rel="noopener" class="tool-link">
                  <GithubOutlined /> GitHub
                </a>
                <a v-if="tool.paper_url" :href="tool.paper_url" target="_blank" rel="noopener" class="tool-link">
                  <FileTextOutlined /> {{ t('tools.paper') }}
                </a>
                <a v-if="tool.doc_url" :href="tool.doc_url" target="_blank" rel="noopener" class="tool-link">
                  <BookOutlined /> {{ t('tools.documentation') }}
                </a>
              </div>
            </div>

            <!-- 参数表单 -->
            <div class="tool-form card">
              <h2 class="section-title">{{ t('tools.parameters') }}</h2>

              <!-- 积分消耗提示 -->
              <a-alert
                v-if="!tool.is_free"
                type="info"
                show-icon
                style="margin-bottom: 16px"
              >
                <template #message>
                  {{ t('tools.creditsCost', { credits: tool.credits }) }}
                  <span v-if="userStore.credits < tool.credits" class="insufficient">
                    ({{ t('tools.insufficientCredits') }})
                  </span>
                </template>
              </a-alert>

              <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
                <template v-for="(prop, key) in tool.input_schema?.properties" :key="key">
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
                      v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta')"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                      :rows="prop.format === 'fasta' ? 8 : 4"
                      :class="{ 'fasta-input': prop.format === 'fasta' }"
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
                      v-else-if="prop.type === 'select' || prop.enum"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                    >
                      <a-select-option v-for="opt in prop.enum" :key="opt" :value="opt">
                        {{ opt }}
                      </a-select-option>
                    </a-select>
                    <!-- 文件上传 -->
                    <a-upload
                      v-else-if="prop.type === 'file'"
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

                <!-- 示例参数按钮 -->
                <a-form-item v-if="tool.example_params">
                  <a-button type="link" @click="loadExampleParams">
                    <ExperimentOutlined />
                    {{ t('tools.loadExample') }}
                  </a-button>
                </a-form-item>

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

          <!-- 右侧：同类推荐 -->
          <div class="tool-sidebar">
            <div class="related-tools card">
              <h3 class="sidebar-title">
                <AppstoreOutlined />
                {{ t('tools.relatedTools') }}
              </h3>
              <a-spin :spinning="relatedLoading">
                <div v-if="relatedTools.length" class="related-list">
                  <div
                    v-for="related in relatedTools"
                    :key="related.id"
                    class="related-item"
                    @click="goToTool(related.id)"
                  >
                    <div class="related-icon">
                      <span v-if="related.icon">{{ related.icon }}</span>
                      <ToolOutlined v-else />
                    </div>
                    <div class="related-info">
                      <h4 class="related-name">{{ related.name }}</h4>
                      <p class="related-desc">{{ related.description }}</p>
                      <div class="related-stats">
                        <span>
                          <PlayCircleOutlined />
                          {{ formatNumber(related.run_count) }}
                        </span>
                        <span v-if="related.credits > 0">
                          <ThunderboltOutlined />
                          {{ related.credits }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <a-empty v-else :description="t('tools.noRelatedTools')" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
              </a-spin>
            </div>

            <!-- 输入输出格式说明 -->
            <div v-if="tool.input_formats?.length || tool.output_formats?.length" class="formats-info card">
              <h3 class="sidebar-title">
                <FileTextOutlined />
                {{ t('tools.formatInfo') }}
              </h3>
              <div v-if="tool.input_formats?.length" class="format-section">
                <h4>{{ t('tools.inputFormats') }}</h4>
                <a-tag v-for="fmt in tool.input_formats" :key="fmt" color="blue">{{ fmt }}</a-tag>
              </div>
              <div v-if="tool.output_formats?.length" class="format-section">
                <h4>{{ t('tools.outputFormats') }}</h4>
                <a-tag v-for="fmt in tool.output_formats" :key="fmt" color="green">{{ fmt }}</a-tag>
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
  import { message, Empty } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import {
    ToolOutlined,
    HeartOutlined,
    HeartFilled,
    PlayCircleOutlined,
    TagOutlined,
    UploadOutlined,
    ClockCircleOutlined,
    DownOutlined,
    CheckCircleOutlined,
    GithubOutlined,
    FileTextOutlined,
    BookOutlined,
    ThunderboltOutlined,
    AppstoreOutlined,
    ExperimentOutlined,
    FileOutlined
  } from '@ant-design/icons-vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type { SchemaProperty, RelatedTool } from '@/types/models'
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
  const relatedLoading = ref(false)
  const tool = computed(() => toolsStore.currentTool)
  const relatedTools = ref<RelatedTool[]>([])
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})

  const canSubmit = computed(() => {
    if (!userStore.isAuthenticated) return false
    if (userStore.isGuest) return false
    if (tool.value && !tool.value.is_free && userStore.credits < tool.value.credits) return false
    return true
  })

  const formatNumber = (num: number) => {
    if (num >= 10000) {
      return (num / 10000).toFixed(1) + 'w'
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}min`
  }

  const getFieldRules = (key: string, prop: SchemaProperty): Rule[] => {
    const rules: Rule[] = []
    const schema = tool.value?.input_schema
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

  const handleVersionChange = ({ key }: { key: string }) => {
    // TODO: 切换工具版本
    message.info(t('tools.switchingVersion', { version: key }))
  }

  const loadExampleParams = () => {
    if (tool.value?.example_params) {
      Object.assign(formState, tool.value.example_params)
      message.success(t('tools.exampleLoaded'))
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

    if (tool.value && !tool.value.is_free && userStore.credits < tool.value.credits) {
      message.warning(t('tools.insufficientCredits'))
      return
    }

    submitting.value = true
    try {
      // 处理文件上传
      const fileIds: number[] = []
      for (const [key, files] of Object.entries(fileList)) {
        if (files.length > 0) {
          const fileItem = files[0]
          if (fileItem && fileItem.originFileObj) {
            const res = await uploadFile(fileItem.originFileObj as File)
            fileIds.push(res.data.id)
            formState[key] = res.data.id
          }
        }
      }

      // 创建任务
      const task = await tasksStore.createTask({
        tool_id: tool.value!.id,
        input_params: { ...formState },
        input_file_ids: fileIds.length > 0 ? fileIds : undefined
      })

      // 扣除积分
      if (tool.value && !tool.value.is_free) {
        userStore.consumeCredits(tool.value.credits)
      }

      message.success(t('tasks.created'))
      router.push(`/tasks/${task.id}`)
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  const goToTool = (id: number) => {
    router.push(`/tools/${id}`)
  }

  onMounted(async () => {
    const id = Number(route.params.id)
    if (id) {
      loading.value = true
      relatedLoading.value = true
      try {
        await toolsStore.fetchToolDetail(id)

        // 初始化表单默认值
        if (tool.value?.input_schema?.properties) {
          for (const [key, prop] of Object.entries(tool.value.input_schema.properties)) {
            if (prop.default !== undefined) {
              formState[key] = prop.default
            }
            // 初始化文件列表
            if (prop.type === 'file') {
              fileList[key] = []
            }
          }
        }

        // 获取同类推荐
        const related = await toolsStore.fetchRelatedTools(id, 4)
        relatedTools.value = related
      } finally {
        loading.value = false
        relatedLoading.value = false
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
    }

    .tool-description {
      color: @text-color-light-secondary;
      font-size: @font-size-md;
      margin-bottom: @spacing-lg;
      line-height: @line-height-loose;
    }

    .tool-introduction,
    .tool-features,
    .tool-steps,
    .tool-references {
      margin-bottom: @spacing-lg;

      h3 {
        font-size: @font-size-lg;
        font-weight: @font-weight-semibold;
        margin-bottom: @spacing-md;
      }
    }

    .tool-features ul {
      list-style: none;
      padding: 0;
      margin: 0;

      li {
        display: flex;
        align-items: flex-start;
        gap: @spacing-sm;
        padding: @spacing-xs 0;

        .feature-icon {
          color: @success-color;
          margin-top: 4px;
        }
      }
    }

    .tool-references ul {
      list-style: none;
      padding: 0;
      margin: 0;

      li {
        padding: @spacing-xs 0;

        a {
          color: @accent-color;

          &:hover {
            color: @accent-color-hover;
          }
        }

        .ref-authors,
        .ref-year {
          color: @text-color-light-tertiary;
          font-size: @font-size-sm;
        }
      }
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

    .tool-links {
      display: flex;
      gap: @spacing-md;

      .tool-link {
        display: flex;
        align-items: center;
        gap: @spacing-xs;
        color: @accent-color;
        padding: @spacing-xs @spacing-sm;
        border: 1px solid @accent-color;
        border-radius: @border-radius-sm;
        transition: all 0.3s;

        &:hover {
          background: @accent-color;
          color: @bg-light;
        }
      }
    }
  }

  .tool-form {
    .section-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-lg;
    }

    .insufficient {
      color: @error-color;
    }

    .fasta-input {
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

  .related-tools {
    .related-list {
      display: flex;
      flex-direction: column;
      gap: @spacing-md;
    }

    .related-item {
      display: flex;
      gap: @spacing-sm;
      padding: @spacing-sm;
      border-radius: @border-radius-md;
      cursor: pointer;
      transition: background 0.3s;

      &:hover {
        background: rgba(0, 0, 0, 0.02);
      }
    }

    .related-icon {
      width: 40px;
      height: 40px;
      border-radius: @border-radius-sm;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      color: @accent-color;
      flex-shrink: 0;
    }

    .related-info {
      flex: 1;
      min-width: 0;
    }

    .related-name {
      font-size: @font-size-sm;
      font-weight: @font-weight-medium;
      margin-bottom: 2px;
      .text-ellipsis();
    }

    .related-desc {
      font-size: @font-size-xs;
      color: @text-color-light-tertiary;
      margin-bottom: 4px;
      .text-ellipsis();
    }

    .related-stats {
      display: flex;
      gap: @spacing-sm;
      font-size: @font-size-xs;
      color: @text-color-light-tertiary;

      span {
        display: flex;
        align-items: center;
        gap: 2px;
      }
    }
  }

  .formats-info {
    .format-section {
      margin-bottom: @spacing-md;

      &:last-child {
        margin-bottom: 0;
      }

      h4 {
        font-size: @font-size-sm;
        font-weight: @font-weight-medium;
        margin-bottom: @spacing-xs;
        color: @text-color-light-secondary;
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
