<template>
  <div class="tool-create-page">
    <div class="container">
      <div class="page-header">
        <a-button @click="goBack">
          <ArrowLeftOutlined />
          {{ t('common.back') }}
        </a-button>
        <h1 class="page-title">{{ isEdit ? t('tools.editTool') : t('tools.createTool') }}</h1>
      </div>

      <a-spin :spinning="loading">
        <a-card class="form-card">
          <a-form
            ref="formRef"
            :model="formState"
            :rules="formRules"
            layout="vertical"
            @finish="handleSubmit"
          >
            <!-- 基本信息 -->
            <a-divider orientation="left">{{ t('tools.basicInfo') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.toolName')" name="name">
                  <a-input
                    v-model:value="formState.name"
                    :placeholder="t('tools.toolNamePlaceholder')"
                    :max-length="100"
                    show-count
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.toolSlug')" name="slug">
                  <a-input
                    v-model:value="formState.slug"
                    :placeholder="t('tools.toolSlugPlaceholder')"
                    :max-length="50"
                    show-count
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.slugHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('common.description')" name="description">
              <a-textarea
                v-model:value="formState.description"
                :placeholder="t('tools.descriptionPlaceholder')"
                :rows="4"
                :max-length="500"
                show-count
              />
            </a-form-item>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.category')" name="category_id">
                  <a-select
                    v-model:value="formState.category_id"
                    :placeholder="t('tools.selectCategory')"
                    allow-clear
                  >
                    <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
                      {{ cat.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.tags')" name="tag_ids">
                  <a-select
                    v-model:value="formState.tag_ids"
                    :placeholder="t('tools.selectTags')"
                    mode="multiple"
                    allow-clear
                  >
                    <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.id">
                      <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.icon')" name="icon">
                  <a-input
                    v-model:value="formState.icon"
                    :placeholder="t('tools.iconPlaceholder')"
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.iconHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.iconUrl')" name="icon_url">
                  <a-input
                    v-model:value="formState.icon_url"
                    :placeholder="t('tools.iconUrlPlaceholder')"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 运行配置 -->
            <a-divider orientation="left">{{ t('tools.runConfig') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.timeoutSec')" name="timeout_sec">
                  <a-input-number
                    v-model:value="formState.timeout_sec"
                    :min="60"
                    :max="86400"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('tools.isPublic')" name="is_public">
              <a-switch v-model:checked="formState.is_public" />
              <span class="switch-label">{{ formState.is_public ? t('tools.publicYes') : t('tools.publicNo') }}</span>
            </a-form-item>

            <!-- 版本信息 -->
            <a-divider orientation="left">版本信息</a-divider>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item label="版本号" name="version">
                  <a-input
                    v-model:value="formState.version"
                    placeholder="例如：1.0.0"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="16">
                <a-form-item label="版本说明" name="notes">
                  <a-input
                    v-model:value="formState.notes"
                    placeholder="简要说明此版本的特点"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="更新日志" name="changelog">
              <a-textarea
                v-model:value="formState.changelog"
                placeholder="详细描述此版本的更新内容"
                :rows="3"
              />
            </a-form-item>

            <!-- 工具类型 -->
            <a-divider orientation="left">工具类型</a-divider>

            <a-form-item label="工具类型" name="tool_type">
              <a-radio-group v-model:value="formState.tool_type">
                <a-radio value="remote_api">远程API</a-radio>
                <a-radio value="docker_image">Docker镜像</a-radio>
                <a-radio value="python_script">Python脚本</a-radio>
              </a-radio-group>
            </a-form-item>

            <!-- API配置 -->
            <template v-if="formState.tool_type === 'remote_api'">
              <a-divider orientation="left">API配置</a-divider>

              <a-form-item label="API地址" name="api_endpoint" :rules="[{ required: true, message: '请输入API地址' }]">
                <a-input
                  v-model:value="formState.api_endpoint"
                  placeholder="https://api.example.com/predict"
                />
              </a-form-item>

              <a-form-item label="请求方法" name="api_method">
                <a-select v-model:value="formState.api_method">
                  <a-select-option value="GET">GET</a-select-option>
                  <a-select-option value="POST">POST</a-select-option>
                  <a-select-option value="PUT">PUT</a-select-option>
                  <a-select-option value="DELETE">DELETE</a-select-option>
                </a-select>
              </a-form-item>

              <a-form-item label="请求头（可选）" name="api_headers">
                <a-textarea
                  v-model:value="apiHeadersText"
                  placeholder='{"Content-Type": "application/json", "Authorization": "Bearer token"}'
                  :rows="3"
                />
                <template #extra>
                  <span class="form-extra">JSON格式的请求头，例如：{"key": "value"}</span>
                </template>
              </a-form-item>
            </template>

            <!-- Docker配置 -->
            <template v-if="formState.tool_type === 'docker_image'">
              <a-divider orientation="left">Docker配置</a-divider>

              <a-form-item label="Docker镜像" name="docker_image" :rules="[{ required: true, message: '请输入Docker镜像名称' }]">
                <a-input
                  v-model:value="formState.docker_image"
                  placeholder="例如：python:3.9-slim"
                />
              </a-form-item>

              <a-form-item label="启动命令（可选）" name="docker_command">
                <a-input
                  v-model:value="formState.docker_command"
                  placeholder="例如：python /app/main.py"
                />
              </a-form-item>

              <a-form-item label="环境变量（可选）" name="docker_env">
                <a-textarea
                  v-model:value="dockerEnvText"
                  placeholder='{"PYTHONPATH": "/app", "MODEL_PATH": "/models"}'
                  :rows="3"
                />
                <template #extra>
                  <span class="form-extra">JSON格式的环境变量，例如：{"key": "value"}</span>
                </template>
              </a-form-item>
            </template>

            <!-- Python脚本配置 -->
            <template v-if="formState.tool_type === 'python_script'">
              <a-divider orientation="left">Python脚本配置</a-divider>

              <a-form-item label="脚本路径" name="python_script" :rules="[{ required: true, message: '请输入Python脚本路径' }]">
                <a-input
                  v-model:value="formState.python_script"
                  placeholder="例如：/app/scripts/predict.py"
                />
              </a-form-item>

              <a-form-item label="脚本参数（可选）" name="python_args">
                <a-input
                  v-model:value="formState.python_args"
                  placeholder="例如：--model-path /models --batch-size 32"
                />
              </a-form-item>
            </template>

            <!-- 参数定义 -->
            <a-divider orientation="left">参数定义</a-divider>

            <a-form-item label="输入参数Schema" name="input_schema">
              <a-textarea
                v-model:value="formState.input_schema"
                placeholder='{"type": "object", "properties": {"input": {"type": "string"}}}'
                :rows="5"
              />
              <template #extra>
                <span class="form-extra">JSON Schema格式，定义工具的输入参数结构</span>
              </template>
            </a-form-item>

            <a-form-item label="输出参数Schema" name="output_schema">
              <a-textarea
                v-model:value="formState.output_schema"
                placeholder='{"type": "object", "properties": {"result": {"type": "string"}}}'
                :rows="5"
              />
              <template #extra>
                <span class="form-extra">JSON Schema格式，定义工具的输出结果结构</span>
              </template>
            </a-form-item>

            <!-- 提交按钮 -->
            <a-form-item class="form-actions">
              <a-space size="middle">
                <a-button size="large" @click="goBack">
                  {{ t('common.cancel') }}
                </a-button>
                <a-button type="primary" size="large" html-type="submit" :loading="submitting">
                  <SaveOutlined />
                  {{ isEdit ? t('common.save') : t('common.create') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    ArrowLeftOutlined,
    SaveOutlined
  } from '@ant-design/icons-vue'
  import { useToolsStore } from '@/stores'
  import { createTool, updateTool, getToolDetail } from '@/api/tools'
  import type { ToolCreateParams } from '@/types/models'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)

  // 判断是编辑还是创建
  const isEdit = computed(() => route.name === 'ToolEdit')
  const toolId = computed(() => route.params.id as string)

  // 扩展的表单状态接口
  interface ExtendedFormState extends ToolCreateParams {
    tag_ids: string[]
    // 版本信息
    version: string
    changelog: string
    notes: string
    // 工具类型
    tool_type: 'remote_api' | 'docker_image' | 'python_script'
    // API配置
    api_endpoint: string
    api_method: 'GET' | 'POST' | 'PUT' | 'DELETE'
    api_headers: Record<string, string>
    // Docker配置
    docker_image: string
    docker_command: string
    docker_env: Record<string, string>
    // Python配置
    python_script: string
    python_args: string
    // 参数定义
    input_schema: string  // JSON字符串
    output_schema: string  // JSON字符串
  }

  // 表单状态
  const formState = reactive<ExtendedFormState>({
    name: '',
    slug: '',
    description: '',
    category_id: '',
    icon: '',
    icon_url: '',
    is_public: true,
    gpu_required: false,
    gpu_memory_mb: undefined,
    timeout_sec: 3600,
    tag_ids: [],
    // 版本信息
    version: '1.0.0',
    changelog: '',
    notes: '',
    // 工具类型
    tool_type: 'remote_api',
    // API配置
    api_endpoint: '',
    api_method: 'POST',
    api_headers: {},
    // Docker配置
    docker_image: '',
    docker_command: '',
    docker_env: {},
    // Python配置
    python_script: '',
    python_args: '',
    // 参数定义
    input_schema: '{}',
    output_schema: '{}'
  })

  // 辅助变量：用于JSON格式的文本输入
  const apiHeadersText = ref('{}')
  const dockerEnvText = ref('{}')

  // 表单验证规则
  const formRules: Record<string, Rule[]> = {
    name: [
      { required: true, message: t('tools.nameRequired'), trigger: 'blur' },
      { min: 2, max: 100, message: t('tools.nameLength'), trigger: 'blur' }
    ],
    slug: [
      { required: true, message: t('tools.slugRequired'), trigger: 'blur' },
      { pattern: /^[a-z0-9-]+$/, message: t('tools.slugFormat'), trigger: 'blur' },
      { min: 2, max: 50, message: t('tools.slugLength'), trigger: 'blur' }
    ],
    description: [
      { max: 500, message: t('tools.descriptionLength'), trigger: 'blur' }
    ]
  }

  // 分类和标签
  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)

  // 加载工具详情（编辑模式）
  const loadToolDetail = async () => {
    if (!isEdit.value || !toolId.value) return

    loading.value = true
    try {
      const res = await getToolDetail(toolId.value)
      const tool = res.data

      // 填充表单
      formState.name = tool.name
      formState.slug = tool.slug
      formState.description = tool.description || ''
      formState.category_id = tool.category_id || ''
      formState.icon = tool.icon || ''
      formState.icon_url = tool.icon_url || ''
      formState.is_public = tool.is_public ?? true
      formState.gpu_required = tool.gpu_required
      formState.gpu_memory_mb = tool.gpu_memory_mb
      formState.timeout_sec = tool.timeout_sec || 3600
      formState.tag_ids = tool.tags?.map(t => t.id) || []
    } catch {
      message.error(t('tools.loadFailed'))
      router.push('/tools')
    } finally {
      loading.value = false
    }
  }

  // 提交表单
  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    submitting.value = true
    try {
      // 解析 JSON 字符串
      let apiHeaders: Record<string, string> = {}
      let dockerEnv: Record<string, string> = {}
      let inputSchema: Record<string, unknown> = {}
      let outputSchema: Record<string, unknown> = {}

      try {
        if (formState.tool_type === 'remote_api' && apiHeadersText.value.trim()) {
          apiHeaders = JSON.parse(apiHeadersText.value)
        }
        if (formState.tool_type === 'docker_image' && dockerEnvText.value.trim()) {
          dockerEnv = JSON.parse(dockerEnvText.value)
        }
        if (formState.input_schema.trim()) {
          inputSchema = JSON.parse(formState.input_schema)
        }
        if (formState.output_schema.trim()) {
          outputSchema = JSON.parse(formState.output_schema)
        }
      } catch (e) {
        message.error('JSON 格式错误，请检查配置')
        submitting.value = false
        return
      }

      // 构建 config 对象
      const config: Record<string, unknown> = {
        type: formState.tool_type,
        input_schema: inputSchema,
        output_schema: outputSchema
      }

      // 根据工具类型添加特定配置
      if (formState.tool_type === 'remote_api') {
        config.endpoint = formState.api_endpoint
        config.method = formState.api_method
        if (Object.keys(apiHeaders).length > 0) {
          config.headers = apiHeaders
        }
      } else if (formState.tool_type === 'docker_image') {
        config.image = formState.docker_image
        if (formState.docker_command) {
          config.command = formState.docker_command
        }
        if (Object.keys(dockerEnv).length > 0) {
          config.env = dockerEnv
        }
      } else if (formState.tool_type === 'python_script') {
        config.script = formState.python_script
        if (formState.python_args) {
          config.args = formState.python_args
        }
      }

      // 构建提交数据
      const data: ToolCreateParams & { initial_version?: unknown } = {
        name: formState.name,
        slug: formState.slug,
        description: formState.description || undefined,
        category_id: formState.category_id,
        icon: formState.icon || undefined,
        icon_url: formState.icon_url || undefined,
        is_public: formState.is_public,
        gpu_required: formState.gpu_required,
        gpu_memory_mb: formState.gpu_required ? formState.gpu_memory_mb : undefined,
        timeout_sec: formState.timeout_sec,
        tag_ids: formState.tag_ids.length > 0 ? formState.tag_ids : undefined
      }

      // 添加版本信息（仅创建模式）
      if (!isEdit.value) {
        data.initial_version = {
          version: formState.version,
          changelog: formState.changelog || undefined,
          notes: formState.notes || undefined,
          config: config,
          is_active: true
        }
      }

      if (isEdit.value) {
        await updateTool(toolId.value, data)
        message.success(t('tools.updateSuccess'))
      } else {
        const res = await createTool(data)
        message.success(t('tools.createSuccess'))
        // 跳转到工具详情页
        router.push(`/tools/${res.data.id}`)
        return
      }

      router.push('/admin/tools')
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  const goBack = () => {
    router.back()
  }

  onMounted(async () => {
    // 加载分类和标签
    await Promise.all([
      toolsStore.fetchCategories(),
      toolsStore.fetchTags()
    ])

    // 编辑模式加载工具详情
    if (isEdit.value) {
      await loadToolDetail()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-create-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .page-header {
    display: flex;
    align-items: center;
    gap: @spacing-lg;
    margin-bottom: @spacing-xl;
  }

  .page-title {
    font-size: @font-size-xxl;
    font-weight: @font-weight-bold;
    margin: 0;
  }

  .form-card {
    max-width: 900px;
    margin: 0 auto;
  }

  .form-extra {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  .switch-label {
    margin-left: @spacing-sm;
    color: @text-color-light-secondary;
  }

  .form-actions {
    margin-top: @spacing-xl;
    padding-top: @spacing-lg;
    border-top: 1px solid @border-color-light;
    text-align: center;
  }

  :deep(.ant-divider-inner-text) {
    font-weight: @font-weight-semibold;
    color: @text-color-light-primary;
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
